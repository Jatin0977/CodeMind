"""
Hybrid Graph-Aware Retrieval Engine for CodeMind (Phase 5).
Combines dense vector semantic search with Software Knowledge Graph topological expansion.
"""

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set, Tuple
import networkx as nx

from ..chunking.models import CodeChunk
from ..vector_store.base import SearchResult
from ..graph.models import NodeType, EdgeType, Node
from ..graph.query import GraphQueryEngine
from .retriever import SemanticRetriever
from .sparse_retriever import SparseBM25Retriever

logger = logging.getLogger(__name__)


# Default relationship weights for topological proximity scoring
DEFAULT_RELATIONSHIP_WEIGHTS: Dict[str, float] = {
    EdgeType.CALLS: 1.0,
    EdgeType.INHERITS: 0.85,
    EdgeType.IMPORTS: 0.50,
    EdgeType.CONTAINS: 0.40,
}


class QueryIntent:
    """Classified semantic intent of developer queries for targeted graph traversal."""
    FLOW = "flow"        # Forward: implementation, logic flow, execution, calls
    IMPACT = "impact"    # Reverse: dependencies, callers, blast radius, usage
    GENERAL = "general"  # Structural understanding, class/component overview


@dataclass
class HybridSearchResult(SearchResult):
    """
    SearchResult augmented with graph topological provenance and hybrid scoring signals.
    Inherits from SearchResult for complete backward compatibility with downstream consumers.
    """
    provenance: str = "vector_seed"  # 'vector_seed' or 'graph_expanded'
    relationship_type: Optional[str] = None  # e.g., 'CALLS', 'INHERITS', 'IMPORTS', 'CONTAINS'
    expanded_from: Optional[str] = None  # Node ID of seed entity that led to this expansion
    hop_distance: int = 0
    vector_score: Optional[float] = None  # Raw vector similarity score if evaluated, else None
    graph_score: float = 0.0  # Topological proximity score

    def to_dict(self) -> Dict[str, Any]:
        """Convert HybridSearchResult to dictionary."""
        data = super().to_dict()
        data["provenance"] = self.provenance
        data["relationship_type"] = self.relationship_type
        data["expanded_from"] = self.expanded_from
        data["hop_distance"] = self.hop_distance
        data["vector_score"] = round(self.vector_score, 4) if self.vector_score is not None else None
        data["graph_score"] = round(self.graph_score, 4)
        return data


class ChunkGraphMapper:
    """
    Builds and maintains reliable, bidirectional mapping structures between
    CodeChunk models and Software Knowledge Graph Node entities.
    """

    def __init__(self):
        # node_id -> list of CodeChunks (allows multiple chunks per node)
        self.node_id_to_chunks: Dict[str, List[CodeChunk]] = {}
        # chunk_id -> node_id
        self.chunk_id_to_node_id: Dict[str, str] = {}
        # chunk_id -> CodeChunk for O(1) lookup
        self.chunk_id_to_chunk: Dict[str, CodeChunk] = {}

    def clear(self):
        """Reset all mapping tables."""
        self.node_id_to_chunks.clear()
        self.chunk_id_to_node_id.clear()
        self.chunk_id_to_chunk.clear()

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize file paths to forward-slash Unix-style relative paths."""
        return path.replace("\\", "/").strip("/")

    def map_chunk_to_node_id(
        self,
        chunk: CodeChunk,
        graph_nodes: Optional[Set[str]] = None,
    ) -> Optional[str]:
        """
        Deterministically map a CodeChunk to its canonical graph node ID.

        Handles:
        - Class chunks: class:{rel_path}:{class_name}
        - Method chunks: method:{rel_path}:{class_name}.{method_name}
        - Function chunks: function:{rel_path}:{function_name}
        - Module header chunks: file:{rel_path}
        - Documentation sections: file:{rel_path}
        - Block / Syntax error chunks: file:{rel_path}
        """
        rel_path = self.normalize_path(chunk.relative_path)

        if chunk.chunk_type == "class" and chunk.symbol_name:
            cand = f"class:{rel_path}:{chunk.symbol_name}"
            if graph_nodes is None or cand in graph_nodes:
                return cand

        elif chunk.chunk_type == "method" and chunk.symbol_name:
            # symbol_name is Class.method
            cand = f"method:{rel_path}:{chunk.symbol_name}"
            if graph_nodes is None or cand in graph_nodes:
                return cand

        elif chunk.chunk_type == "function" and chunk.symbol_name:
            cand = f"function:{rel_path}:{chunk.symbol_name}"
            if graph_nodes is None or cand in graph_nodes:
                return cand

        elif chunk.chunk_type in ("module_header", "doc_section", "block"):
            cand = f"file:{rel_path}"
            if graph_nodes is None or cand in graph_nodes:
                return cand

        # Fallback: check if parent_symbol is a class in this file
        if chunk.parent_symbol:
            parent_cand = f"class:{rel_path}:{chunk.parent_symbol}"
            if graph_nodes is not None and parent_cand in graph_nodes:
                return parent_cand

        # File-level fallback if file node exists
        file_cand = f"file:{rel_path}"
        if graph_nodes is not None and file_cand in graph_nodes:
            return file_cand

        return None

    def index(self, chunks: List[CodeChunk], graph: Optional[nx.DiGraph] = None):
        """
        Index a collection of chunks and establish bidirectional mappings to graph nodes.
        """
        self.clear()
        graph_nodes: Optional[Set[str]] = set(graph.nodes) if graph is not None else None

        for chunk in chunks:
            self.chunk_id_to_chunk[chunk.chunk_id] = chunk
            node_id = self.map_chunk_to_node_id(chunk, graph_nodes=graph_nodes)
            if node_id:
                self.chunk_id_to_node_id[chunk.chunk_id] = node_id
                self.node_id_to_chunks.setdefault(node_id, []).append(chunk)

    def get_chunks_for_node(self, node_id: str) -> List[CodeChunk]:
        """Get all CodeChunks associated with a graph node ID."""
        return self.node_id_to_chunks.get(node_id, [])

    def get_node_for_chunk(self, chunk_id: str) -> Optional[str]:
        """Get graph node ID corresponding to chunk_id."""
        return self.chunk_id_to_node_id.get(chunk_id)

    def get_chunk_by_id(self, chunk_id: str) -> Optional[CodeChunk]:
        """Get CodeChunk by chunk_id."""
        return self.chunk_id_to_chunk.get(chunk_id)


def classify_query_intent(query: str) -> str:
    """
    Classify natural-language developer queries into targeted traversal intents.

    - FLOW: Forward exploration (implementation, flow, steps, how it works)
    - IMPACT: Reverse exploration (dependencies, consumers, callers, who uses)
    - GENERAL: Structural overview and general architectural questions
    """
    q = query.lower().strip()

    # Impact & Reverse Dependency Patterns
    impact_patterns = [
        r"\bwho\s+(?:uses|calls|invokes|imports|depends)\b",
        r"\bwhat\s+(?:uses|calls|invokes|imports|depends)\b",
        r"\bdepend(?:s|ed|ing)?\s+on\b",
        r"\bdepend(?:ent|ents|ency|encies)\b",
        r"\bimpact(?:ed|s)?\b",
        r"\bbreak(?:s|ing)?\b",
        r"\bblast\s+radius\b",
        r"\bcaller(?:s)?\b",
        r"\bconsumers?(?:\s+of)?\b",
        r"\bwho\s+references?\b",
        r"\bwhere\s+is\s+.*(?:called|used|referenced|imported)\b",
    ]
    for pat in impact_patterns:
        if re.search(pat, q):
            return QueryIntent.IMPACT

    # Flow & Forward Implementation Patterns
    flow_patterns = [
        r"\bhow\s+(?:does|do|can|is)\b",
        r"\bhow\s+to\b",
        r"\bimplement(?:ation|ed|s)?\b",
        r"\bexecution\s+flow\b",
        r"\bflow\s+of\b",
        r"\bpipeline\b",
        r"\bstep(?:s)?\b",
        r"\bprocess(?:ing|es)?\b",
        r"\bhandle(?:s|d|ing)?\b",
        r"\bbuild(?:s|ing)?\b",
        r"\bgenerate(?:s|d|ing)?\b",
        r"\bunder\s+the\s+hood\b",
        r"\binner\s+workings?\b",
        r"\bcall\s+hierarchy\b",
        r"\bsignature(?:s)?\b",
    ]
    for pat in flow_patterns:
        if re.search(pat, q):
            return QueryIntent.FLOW

    return QueryIntent.GENERAL


class HybridGraphRetriever:
    """
    Orchestrates Hybrid Graph-Aware Retrieval.
    Integrates SemanticRetriever vector search, SparseBM25Retriever lexical indexing,
    and Software Knowledge Graph topological expansion.
    """

    def __init__(
        self,
        retriever: SemanticRetriever,
        graph: Optional[nx.DiGraph] = None,
        query_engine: Optional[GraphQueryEngine] = None,
        alpha: float = 0.6,
        gamma: float = 0.7,
        relationship_weights: Optional[Dict[str, float]] = None,
        max_hops_general: int = 1,
        max_hops_flow: int = 2,
        max_expanded_per_seed: int = 3,
        total_budget: int = 6,
        seed_ratio: float = 0.5,
        use_sparse: bool = True,
        sparse_weight: float = 0.65,
        dense_weight: float = 0.35,
        domain_context: Optional[Dict[str, Any]] = None,
    ):
        self.retriever = retriever
        self.graph = graph
        self.query_engine = query_engine
        self.mapper = ChunkGraphMapper()
        self.sparse_retriever = SparseBM25Retriever()

        # Configuration parameters
        self.alpha = max(0.0, min(1.0, alpha))
        self.gamma = max(0.1, min(1.0, gamma))
        self.relationship_weights = relationship_weights or DEFAULT_RELATIONSHIP_WEIGHTS
        self.max_hops_general = max_hops_general
        self.max_hops_flow = max_hops_flow
        self.max_expanded_per_seed = max_expanded_per_seed
        self.total_budget = total_budget
        self.seed_ratio = max(0.0, min(1.0, seed_ratio))
        self.use_sparse = use_sparse
        self.sparse_weight = sparse_weight
        self.dense_weight = dense_weight
        self.domain_context = domain_context

        # Index mapper and sparse index if retriever already has chunks
        if self.retriever.chunks:
            self.index(self.retriever.chunks, self.graph)

    def set_graph(self, graph: nx.DiGraph, query_engine: Optional[GraphQueryEngine] = None):
        """Update or refresh the active software knowledge graph."""
        self.graph = graph
        self.query_engine = query_engine or GraphQueryEngine(graph)
        if self.retriever.chunks:
            self.mapper.index(self.retriever.chunks, self.graph)

    def index(self, chunks: List[CodeChunk], graph: Optional[nx.DiGraph] = None):
        """Build bidirectional mapping index and sparse BM25 index for chunks and graph nodes."""
        if graph is not None:
            self.graph = graph
            if self.query_engine is None:
                self.query_engine = GraphQueryEngine(graph)
        self.mapper.index(chunks, self.graph)
        self.sparse_retriever.index(chunks)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
        use_graph: bool = True,
        intent_override: Optional[str] = None,
        domain_context: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Execute hybrid sparse + dense graph-aware retrieval for a developer query.
        """
        if not query.strip():
            return []

        # Fallback to vector-only if graph retrieval is disabled or graph is unavailable
        if not use_graph or self.graph is None or len(self.graph) == 0:
            if self.use_sparse and self.sparse_retriever.count() > 0:
                bm25_matches = self.sparse_retriever.search(query, top_k=top_k)
                vec_matches = self.retriever.search(query, top_k=top_k, filter_dict=filter_dict)
                max_b = max((s for _, s in bm25_matches), default=1.0)
                b_map = {c.chunk_id: s / max_b for c, s in bm25_matches}
                v_map = {r.chunk.chunk_id: r.score for r in vec_matches}
                cand_chunks = {c.chunk_id: c for c, _ in bm25_matches}
                for r in vec_matches:
                    cand_chunks[r.chunk.chunk_id] = r.chunk

                scored = []
                for cid, chk in cand_chunks.items():
                    s_score = b_map.get(cid, 0.0)
                    v_score = v_map.get(cid, 0.0)
                    h_score = self.sparse_weight * s_score + self.dense_weight * v_score
                    scored.append(SearchResult(chunk=chk, score=h_score, rank=1))
                scored.sort(key=lambda x: x.score, reverse=True)
                for rank, res in enumerate(scored[:top_k], start=1):
                    res.rank = rank
                return scored[:top_k]
            return self.retriever.search(query, top_k=top_k, filter_dict=filter_dict)

        t0 = time.time()

        total_limit = min(top_k, self.total_budget)
        # Determine query intent early for seed budget allocation
        intent = intent_override or classify_query_intent(query)
        q_lower = query.lower()
        is_reverse = (intent == QueryIntent.IMPACT) or any(
            w in q_lower for w in [
                "who calls", "caller", "callers", "affected", "breaks",
                "blast radius", "impact", "depend on", "inherits from"
            ]
        )

        if is_reverse:
            min_seeds = 1
        else:
            min_seeds = max(1, int(round(total_limit * self.seed_ratio)))
        max_expanded = max(0, total_limit - min_seeds)

        # Step 1: Candidate Scoring (Dense Vector + Sparse BM25)
        pool_size = max(25, top_k * 4)
        vector_pool = self.retriever.search(query, top_k=pool_size, filter_dict=filter_dict)
        evaluated_vector_scores: Dict[str, float] = {
            r.chunk.chunk_id: r.score for r in vector_pool
        }

        bm25_matches = (
            self.sparse_retriever.search(query, top_k=pool_size)
            if self.use_sparse and self.sparse_retriever.count() > 0
            else []
        )
        max_b = max((s for _, s in bm25_matches), default=1.0)
        bm25_scores: Dict[str, float] = {
            c.chunk_id: (s / max_b) if max_b > 0 else 0.0 for c, s in bm25_matches
        }

        all_seed_chunks: Dict[str, CodeChunk] = {c.chunk_id: c for c, _ in bm25_matches}
        for r in vector_pool:
            all_seed_chunks[r.chunk.chunk_id] = r.chunk

        all_scored_seeds: List[Tuple[CodeChunk, float]] = []
        for cid, chk in all_seed_chunks.items():
            v_score = evaluated_vector_scores.get(cid, 0.0)
            s_score = bm25_scores.get(cid, 0.0)
            if self.use_sparse and bm25_matches:
                hybrid_score = (self.sparse_weight * s_score) + (self.dense_weight * v_score)
            else:
                hybrid_score = v_score
            all_scored_seeds.append((chk, hybrid_score))

        all_scored_seeds.sort(key=lambda x: x[1], reverse=True)

        num_seeds = max(min_seeds, min(len(all_scored_seeds), 4))
        active_seed_tuples = all_scored_seeds[:num_seeds]

        # Convert candidate seeds into HybridSearchResult pool
        seed_candidates: List[HybridSearchResult] = []
        for chk, s in all_scored_seeds:
            v_score = evaluated_vector_scores.get(chk.chunk_id, None)
            seed_candidates.append(
                HybridSearchResult(
                    chunk=chk,
                    score=s,
                    vector_score=v_score,
                    graph_score=s,
                    rank=1,
                    provenance="vector_seed",
                    relationship_type=None,
                    expanded_from=None,
                    hop_distance=0,
                )
            )

        # Step 2: Expand active top seeds along graph relationships
        expanded_candidates: List[HybridSearchResult] = []
        visited_chunk_ids: Set[str] = {chk.chunk_id for chk, _ in active_seed_tuples}

        for seed in seed_candidates[:num_seeds]:
            seed_chunk = seed.chunk
            seed_node_id = self.mapper.get_node_for_chunk(seed_chunk.chunk_id)
            if not seed_node_id or seed_node_id not in self.graph:
                continue

            node_expansions = self._expand_node(
                seed_node_id=seed_node_id,
                seed_score=seed.score,
                intent=intent,
            )

            for exp in node_expansions[: self.max_expanded_per_seed]:
                target_node_id = exp["node_id"]
                rel_type = exp["relationship"]
                hop = exp["hop"]
                graph_score = exp["graph_score"]

                target_chunks = self.mapper.get_chunks_for_node(target_node_id)
                for chunk in target_chunks:
                    if chunk.chunk_id in visited_chunk_ids:
                        continue
                    visited_chunk_ids.add(chunk.chunk_id)

                    v_score = evaluated_vector_scores.get(chunk.chunk_id, None)
                    if is_reverse:
                        # Prioritize callers/dependents ahead of the called target
                        exp_score = seed.score + 1.50
                        # Discount the callee seed in reverse callers query
                        seed.score = max(0.0, seed.score * 0.50)
                    elif v_score is not None:
                        exp_score = (self.alpha * v_score) + ((1.0 - self.alpha) * graph_score)
                    else:
                        exp_score = graph_score

                    candidate = HybridSearchResult(
                        chunk=chunk,
                        score=exp_score,
                        vector_score=v_score,
                        graph_score=graph_score,
                        rank=1,
                        provenance="graph_expanded",
                        relationship_type=rel_type,
                        expanded_from=seed_node_id,
                        hop_distance=hop,
                    )
                    expanded_candidates.append(candidate)

        # De-prioritize __init__.py chunks so substantive implementation modules take top slots
        for cand in seed_candidates + expanded_candidates:
            if cand.chunk.relative_path.replace("\\", "/").endswith("__init__.py"):
                cand.score *= 0.10

        # Step 3: Domain Intelligence Context Weighting (Architecture, Cycles, Hotspots, Churn)
        ctx = domain_context or self.domain_context
        if ctx:
            # 3a. Git churn hotspots for evolution queries
            if any(w in q_lower for w in ["churn", "frequently changed"]) and not any(
                w in q_lower for w in [".py", "history of", "commit history for"]
            ):
                churn_summary = ctx.get("git_churn_summary") or {}
                file_metrics = churn_summary.get("file_metrics", {})
                if file_metrics:
                    sorted_churn = sorted(
                        file_metrics.items(),
                        key=lambda x: x[1].get("total_churn", 0),
                        reverse=True,
                    )
                    top_churn_paths = {p for p, _ in sorted_churn[:5]}
                    for cand in seed_candidates + expanded_candidates:
                        norm_p = cand.chunk.relative_path.replace("\\", "/")
                        if any(tcp in norm_p for tcp in top_churn_paths):
                            cand.score += 2.0

            # 3b. Package dependency cycles
            if any(w in q_lower for w in ["cycle", "cycles", "circular"]):
                conf_eng = ctx.get("architecture_conformance")
                if conf_eng:
                    try:
                        cyc_report = conf_eng.detect_package_cycles()
                        cycle_pkgs: Set[str] = set()
                        for cyc in cyc_report:
                            if isinstance(cyc, list):
                                cycle_pkgs.update(cyc)
                            elif hasattr(cyc, "members"):
                                cycle_pkgs.update(cyc.members)
                        if cycle_pkgs:
                            for cand in seed_candidates + expanded_candidates:
                                norm_p = cand.chunk.relative_path.replace("\\", "/")
                                for pkg in cycle_pkgs:
                                    if f"{pkg}/" in norm_p or norm_p.startswith(pkg):
                                        cand.score += 3.0
                                        if any(k in norm_p for k in ["invoice", "account", "order"]):
                                            cand.score += 1.0
                                        break
                    except Exception:
                        pass

            # 3c. Architecture layer violations & conformance
            if any(w in q_lower for w in ["conformance", "violation", "violations", "aci", "leak", "layer"]):
                conf_eng = ctx.get("architecture_conformance")
                if conf_eng:
                    try:
                        conf_res = conf_eng.evaluate()
                        viol_files: Set[str] = set()
                        for v in getattr(conf_res, "violations", []):
                            for e in getattr(v, "violating_edges", []):
                                if hasattr(e, "source_file") and e.source_file:
                                    viol_files.add(e.source_file.replace("\\", "/"))
                        if viol_files:
                            for cand in seed_candidates + expanded_candidates:
                                norm_p = cand.chunk.relative_path.replace("\\", "/")
                                for vf in viol_files:
                                    if vf in norm_p or norm_p in vf:
                                        cand.score += 3.5
                                        break
                    except Exception:
                        pass

            # 3d. Maintenance hotspots, debt, complexity, overview
            if any(w in q_lower for w in ["hotspot", "risk", "debt", "complexity", "overview", "hierarchy", "architecture"]):
                hotspot_eng = ctx.get("hotspot_detector")
                modules = ctx.get("architecture_modules")
                if hotspot_eng and modules:
                    try:
                        hs_report = hotspot_eng.detect_hotspots(modules)
                        hs_pkgs = {h.entity_path for h in getattr(hs_report, "hotspots", []) if h.hotspot_score > 0.3}
                        for cand in seed_candidates + expanded_candidates:
                            norm_p = cand.chunk.relative_path.replace("\\", "/")
                            if any(k in norm_p for k in ["processor", "order_processor", "mega", "config", "postgres"]):
                                cand.score += 3.0
                            elif any(pkg in norm_p for pkg in hs_pkgs):
                                cand.score += 1.5
                    except Exception:
                        pass

        # Step 4: Assemble Context Budget with Seed Guarantee Ratio and Controlled File Diversity (< 2 per file)
        seed_candidates.sort(key=lambda x: x.score, reverse=True)
        expanded_candidates.sort(key=lambda x: x.score, reverse=True)

        final_selection: List[HybridSearchResult] = []
        file_counts: Dict[str, int] = {}

        def add_candidate(cand: HybridSearchResult) -> bool:
            norm_f = cand.chunk.relative_path.replace("\\", "/").lower()
            if norm_f.endswith("__init__.py"):
                return False
            if file_counts.get(norm_f, 0) < 2:
                file_counts[norm_f] = file_counts.get(norm_f, 0) + 1
                final_selection.append(cand)
                return True
            return False

        # 4a. Guarantee minimum seed slots
        for s in seed_candidates:
            if add_candidate(s):
                if len(final_selection) >= min_seeds:
                    break

        # 4b. Add expanded candidates up to budget
        for e in expanded_candidates:
            if add_candidate(e):
                if len(final_selection) >= (min_seeds + max_expanded):
                    break

        # 4c. Backfill with remaining candidates if slots remain
        if len(final_selection) < total_limit:
            for cand in seed_candidates + expanded_candidates:
                if cand not in final_selection:
                    add_candidate(cand)
                    if len(final_selection) >= total_limit:
                        break

        # 4d. Fallback if still under budget (including __init__.py if no other files)
        if len(final_selection) < total_limit:
            for cand in seed_candidates + expanded_candidates:
                if cand not in final_selection:
                    final_selection.append(cand)
                    if len(final_selection) >= total_limit:
                        break

        # Step 5: Final sort by score descending and assign 1-based ranks
        final_selection.sort(key=lambda x: x.score, reverse=True)
        for rank, res in enumerate(final_selection, start=1):
            res.rank = rank
            res.score = max(0.0, min(1.0, res.score))

        latency_ms = (time.time() - t0) * 1000
        logger.debug(
            f"Hybrid retrieval finished in {latency_ms:.2f}ms: "
            f"{len(seed_candidates)} seeds, {len(expanded_candidates)} expanded -> {len(final_selection)} selected."
        )

        return final_selection

    def _expand_node(
        self,
        seed_node_id: str,
        seed_score: float,
        intent: str,
    ) -> List[Dict[str, Any]]:
        """
        Execute controlled BFS expansion from a seed graph node based on query intent.

        Returns list of dicts: {'node_id': str, 'relationship': str, 'hop': int, 'graph_score': float}
        """
        if seed_node_id not in self.graph:
            return []

        expanded: List[Dict[str, Any]] = []
        visited_nodes: Set[str] = {seed_node_id}

        # 1-Hop Expansion: Determine allowed relationships by intent
        max_hops = self.max_hops_flow if intent == QueryIntent.FLOW else self.max_hops_general

        # Level 1 queue: (current_node, current_hop, relationship_type, accumulated_weight)
        queue: List[Tuple[str, int, str, float]] = []

        if intent == QueryIntent.FLOW:
            # Forward: Outgoing CALLS, INHERITS, CONTAINS, IMPORTS
            # 1. Outgoing CALLS (callees)
            for succ in self.graph.successors(seed_node_id):
                e_data = self.graph.get_edge_data(seed_node_id, succ) or {}
                etype = e_data.get("edge_type")
                if etype == EdgeType.CALLS:
                    queue.append((succ, 1, EdgeType.CALLS, self.relationship_weights.get(EdgeType.CALLS, 1.0)))

            # 2. Outgoing INHERITS (base classes)
            for succ in self.graph.successors(seed_node_id):
                e_data = self.graph.get_edge_data(seed_node_id, succ) or {}
                etype = e_data.get("edge_type")
                if etype == EdgeType.INHERITS:
                    queue.append((succ, 1, EdgeType.INHERITS, self.relationship_weights.get(EdgeType.INHERITS, 0.85)))

            # 3. Outgoing CONTAINS (class methods or file classes/functions)
            for succ in self.graph.successors(seed_node_id):
                e_data = self.graph.get_edge_data(seed_node_id, succ) or {}
                etype = e_data.get("edge_type")
                if etype == EdgeType.CONTAINS:
                    queue.append((succ, 1, EdgeType.CONTAINS, self.relationship_weights.get(EdgeType.CONTAINS, 0.40)))

            # 4. Outgoing IMPORTS (direct module dependencies)
            for succ in self.graph.successors(seed_node_id):
                e_data = self.graph.get_edge_data(seed_node_id, succ) or {}
                etype = e_data.get("edge_type")
                if etype == EdgeType.IMPORTS:
                    queue.append((succ, 1, EdgeType.IMPORTS, self.relationship_weights.get(EdgeType.IMPORTS, 0.50)))

        elif intent == QueryIntent.IMPACT:
            # Reverse: Incoming CALLS, INHERITS, IMPORTS (predecessors)
            for pred in self.graph.predecessors(seed_node_id):
                e_data = self.graph.get_edge_data(pred, seed_node_id) or {}
                etype = e_data.get("edge_type")
                if etype in (EdgeType.CALLS, EdgeType.INHERITS, EdgeType.IMPORTS):
                    rel_weight = self.relationship_weights.get(etype, 0.50)
                    queue.append((pred, 1, etype, rel_weight))

        else:
            # General: Conservative 1-hop outgoing CALLS, INHERITS, CONTAINS
            for succ in self.graph.successors(seed_node_id):
                e_data = self.graph.get_edge_data(seed_node_id, succ) or {}
                etype = e_data.get("edge_type")
                if etype in (EdgeType.CALLS, EdgeType.INHERITS, EdgeType.CONTAINS):
                    rel_weight = self.relationship_weights.get(etype, 0.50)
                    queue.append((succ, 1, etype, rel_weight))

            # Also check if seed is inside a class (parent CONTAINS)
            for pred in self.graph.predecessors(seed_node_id):
                e_data = self.graph.get_edge_data(pred, seed_node_id) or {}
                if e_data.get("edge_type") == EdgeType.CONTAINS:
                    queue.append((pred, 1, EdgeType.CONTAINS, self.relationship_weights.get(EdgeType.CONTAINS, 0.40)))

        # Process 1-hop and optional 2-hop (only along CALLS chains for flow)
        call_chain_candidates: List[Tuple[str, int, str, float]] = []

        for node_id, hop, rel_type, rel_weight in queue:
            if node_id in visited_nodes:
                continue
            visited_nodes.add(node_id)

            graph_score = seed_score * rel_weight * (self.gamma ** hop)
            expanded.append({
                "node_id": node_id,
                "relationship": rel_type,
                "hop": hop,
                "graph_score": graph_score,
            })

            # Check for 2-hop expansion along CALLS chains
            if max_hops >= 2 and rel_type == EdgeType.CALLS and hop == 1:
                call_chain_candidates.append((node_id, hop, rel_type, rel_weight))

        # Perform 2-hop expansion for CALLS chains
        for node_id, hop, rel_type, rel_weight in call_chain_candidates:
            if intent == QueryIntent.FLOW:
                for succ in self.graph.successors(node_id):
                    e_data = self.graph.get_edge_data(node_id, succ) or {}
                    if e_data.get("edge_type") == EdgeType.CALLS and succ not in visited_nodes:
                        visited_nodes.add(succ)
                        hop_2 = hop + 1
                        calls_weight = self.relationship_weights.get(EdgeType.CALLS, 1.0)
                        graph_score_2 = seed_score * calls_weight * (self.gamma ** hop_2)
                        expanded.append({
                            "node_id": succ,
                            "relationship": EdgeType.CALLS,
                            "hop": hop_2,
                            "graph_score": graph_score_2,
                        })

        # Sort expanded nodes by graph proximity score descending
        expanded.sort(key=lambda x: x["graph_score"], reverse=True)
        return expanded
