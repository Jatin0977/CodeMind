"""
Core Change Impact Engine for CodeMind Phase 8.
Performs reverse dependency blast-radius analysis, relationship-specific traversal,
hierarchical granularity lifting, strictly 1-hop temporal co-change expansion,
and graph centrality metrics over an isolated code dependency subgraph.
"""

from collections import deque
from typing import Dict, Any, Optional, List, Set, Tuple, Union
import networkx as nx

from .models import (
    ChangeTarget,
    BlastRadiusNode,
    BlastRadiusEdge,
    BlastRadiusReport,
    CentralityMetrics,
    ImpactAnalysisConfig,
)
from ..graph.models import NodeType, EdgeType


class ChangeImpactEngine:
    """
    Analyzes reverse structural blast radius and graph centrality.
    Strictly decouples code dependencies from temporal and container edges.
    """

    def __init__(
        self,
        graph: nx.DiGraph,
        config: Optional[ImpactAnalysisConfig] = None,
        coupling_analyzer: Optional[Any] = None,
    ):
        self.graph = graph
        self.config = config or ImpactAnalysisConfig()
        self.coupling_analyzer = coupling_analyzer
        self._code_subgraph: Optional[nx.DiGraph] = None
        self._pagerank_cache: Optional[Dict[str, float]] = None
        self._max_pagerank: float = 1.0

    @property
    def code_subgraph(self) -> nx.DiGraph:
        """
        Pure Directed Code Dependency Subgraph G_code = (V_code, E_dep).
        Contains strictly code entities (file, class, function, method) and
        dependency edges (CALLS, INHERITS, IMPORTS).
        Excludes temporal edges (CO_CHANGED_WITH, CHANGED_IN) and commits.
        """
        if self._code_subgraph is None:
            self._code_subgraph = self._build_code_subgraph()
        return self._code_subgraph

    def _build_code_subgraph(self) -> nx.DiGraph:
        """Extract isolated directed code dependency graph."""
        g = nx.DiGraph()
        allowed_node_types = {NodeType.FILE, NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD, NodeType.MODULE}
        allowed_edge_types = {EdgeType.CALLS, EdgeType.INHERITS, EdgeType.IMPORTS}

        for n, d in self.graph.nodes(data=True):
            if d.get("node_type") in allowed_node_types:
                g.add_node(n, **d)

        for u, v, d in self.graph.edges(data=True):
            if u in g and v in g:
                if d.get("edge_type") in allowed_edge_types:
                    g.add_edge(u, v, **d)

        return g

    def compute_centrality(self, node_id: str) -> CentralityMetrics:
        """
        Compute In-Degree Centrality and PageRank on the isolated code subgraph.
        Betweenness is excluded from composite centrality and computed only diagnostically.
        """
        g = self.code_subgraph
        n_nodes = g.number_of_nodes()

        if n_nodes <= 1 or node_id not in g:
            return CentralityMetrics(
                in_degree_centrality=0.0,
                pagerank=0.0,
                composite_centrality=0.0,
                betweenness_centrality=None,
            )

        # In-degree centrality (fraction of code nodes with outgoing edges into node_id)
        in_degree = g.in_degree(node_id)
        norm_in_degree = in_degree / (n_nodes - 1) if n_nodes > 1 else 0.0

        # PageRank with damping
        if self._pagerank_cache is None:
            try:
                pr = nx.pagerank(g, alpha=self.config.damping_factor, max_iter=200)
                self._pagerank_cache = pr
                self._max_pagerank = max(pr.values()) if pr else 1.0
            except Exception:
                self._pagerank_cache = {n: 1.0 / n_nodes for n in g.nodes}
                self._max_pagerank = 1.0 / n_nodes if n_nodes else 1.0

        raw_pr = self._pagerank_cache.get(node_id, 0.0)
        norm_pr = raw_pr / self._max_pagerank if self._max_pagerank > 0 else 0.0
        norm_pr = min(1.0, max(0.0, norm_pr))

        # Composite centrality score
        composite = (
            self.config.w_in_degree * norm_in_degree +
            self.config.w_pagerank * norm_pr
        )
        composite = min(1.0, max(0.0, composite))

        return CentralityMetrics(
            in_degree_centrality=round(norm_in_degree, 4),
            pagerank=round(norm_pr, 4),
            composite_centrality=round(composite, 4),
            betweenness_centrality=None,
        )

    def compute_diagnostic_betweenness(self, node_id: str, max_subgraph_nodes: int = 500) -> float:
        """
        Diagnostic-only Betweenness Centrality calculation.
        Computes betweenness on a localized k-hop ego-graph if the graph is large.
        """
        g = self.code_subgraph
        if node_id not in g:
            return 0.0

        n_nodes = g.number_of_nodes()
        if n_nodes <= 1:
            return 0.0

        if n_nodes > max_subgraph_nodes:
            # Use ego-graph of radius 2 to bound computational cost
            sub = nx.ego_graph(g.to_undirected(), node_id, radius=2)
            directed_sub = g.subgraph(sub.nodes())
            b_dict = nx.betweenness_centrality(directed_sub)
        else:
            b_dict = nx.betweenness_centrality(g)

        return round(b_dict.get(node_id, 0.0), 4)

    def analyze_blast_radius(
        self,
        target: ChangeTarget,
        max_depth: Optional[int] = None,
        include_temporal: bool = True,
    ) -> BlastRadiusReport:
        """
        Trace the full multi-tier reverse dependency blast radius.

        Args:
            target: Resolved ChangeTarget.
            max_depth: Maximum traversal depth (defaults to config.default_max_depth = 3).
            include_temporal: Whether to add strictly 1-hop logical co-change coupling.

        Returns:
            BlastRadiusReport containing impacted nodes, edges, and statistics.
        """
        depth_limit = max_depth if max_depth is not None else self.config.default_max_depth
        target_id = target.node_id

        if target_id not in self.graph:
            return BlastRadiusReport(
                target=target,
                max_depth=depth_limit,
                total_impacted=0,
                impacted_nodes=[],
                impacted_edges=[],
                counts_by_type={},
                counts_by_depth={},
                counts_by_tag={},
            )

        impacted_nodes: Dict[str, BlastRadiusNode] = {}
        impacted_edges: List[BlastRadiusEdge] = []
        visited_nodes: Set[str] = {target_id}

        # Queue elements: (curr_node_id, depth, path, relationship, tag)
        queue: deque = deque()

        # Step 1: Initial Seed Expansion for Containers (FILE or CLASS)
        initial_seeds = self._expand_contained_members(target)
        for seed_id, seed_data in initial_seeds.items():
            if seed_id not in visited_nodes:
                visited_nodes.add(seed_id)
                impacted_nodes[seed_id] = BlastRadiusNode(
                    node_id=seed_id,
                    name=seed_data.get("name", seed_id),
                    entity_type=seed_data.get("node_type", "unknown"),
                    file_path=seed_data.get("file_path") or seed_data.get("relative_path"),
                    depth=1,
                    direct_relationship=EdgeType.CONTAINS,
                    path=[target_id, seed_id],
                    tags=["CONTAINED_MEMBER"],
                    metadata=dict(seed_data.get("metadata", {})),
                )
                impacted_edges.append(BlastRadiusEdge(
                    source=target_id,
                    target=seed_id,
                    edge_type=EdgeType.CONTAINS,
                    metadata={"propagation": "downward_container"},
                ))
                queue.append((seed_id, 1, [target_id, seed_id]))

        # Target itself is also a root for reverse traversal
        queue.append((target_id, 0, [target_id]))

        # Step 2: Reverse Dependency BFS Traversal
        while queue:
            curr_id, curr_depth, path = queue.popleft()

            if curr_depth >= depth_limit:
                continue

            next_depth = curr_depth + 1

            # A. Traverse incoming dependency edges: CALLS, INHERITS, IMPORTS
            for pred_id in self.graph.predecessors(curr_id):
                edge_data = self.graph.get_edge_data(pred_id, curr_id) or {}
                edge_type = edge_data.get("edge_type")

                if edge_type not in (EdgeType.CALLS, EdgeType.INHERITS, EdgeType.IMPORTS):
                    continue

                if pred_id in visited_nodes:
                    # Still record the edge if it's within the blast radius
                    impacted_edges.append(BlastRadiusEdge(
                        source=pred_id,
                        target=curr_id,
                        edge_type=edge_type,
                        metadata=dict(edge_data.get("metadata", {})),
                    ))
                    continue

                visited_nodes.add(pred_id)
                pred_data = self.graph.nodes[pred_id]
                pred_type = pred_data.get("node_type", "unknown")

                # Derive descriptive tags based on relationship
                tags = []
                if edge_type == EdgeType.CALLS:
                    tags.append("DIRECT_CALLER" if next_depth == 1 else "TRANSITIVE_CALLER")
                elif edge_type == EdgeType.INHERITS:
                    tags.append("SUBCLASS")
                elif edge_type == EdgeType.IMPORTS:
                    tags.append("COARSE_FILE_DEPENDENT")

                impacted_nodes[pred_id] = BlastRadiusNode(
                    node_id=pred_id,
                    name=pred_data.get("name", pred_id),
                    entity_type=pred_type,
                    file_path=pred_data.get("file_path") or pred_data.get("relative_path"),
                    depth=next_depth,
                    direct_relationship=edge_type,
                    path=path + [pred_id],
                    tags=tags,
                    metadata=dict(pred_data.get("metadata", {})),
                )

                impacted_edges.append(BlastRadiusEdge(
                    source=pred_id,
                    target=curr_id,
                    edge_type=edge_type,
                    metadata=dict(edge_data.get("metadata", {})),
                ))

                queue.append((pred_id, next_depth, path + [pred_id]))

            # B. Hierarchical Granularity Lifting for Symbols (function, class, method)
            curr_data = self.graph.nodes.get(curr_id, {})
            curr_node_type = curr_data.get("node_type")
            if curr_node_type in (NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS):
                parent_file_id = self._find_parent_file_id(curr_id, curr_data)
                if parent_file_id and parent_file_id in self.graph:
                    # Check incoming IMPORTS to parent file
                    for file_importer_id in self.graph.predecessors(parent_file_id):
                        import_edge = self.graph.get_edge_data(file_importer_id, parent_file_id) or {}
                        if import_edge.get("edge_type") == EdgeType.IMPORTS:
                            if file_importer_id not in visited_nodes:
                                visited_nodes.add(file_importer_id)
                                imp_data = self.graph.nodes[file_importer_id]
                                impacted_nodes[file_importer_id] = BlastRadiusNode(
                                    node_id=file_importer_id,
                                    name=imp_data.get("name", file_importer_id),
                                    entity_type=imp_data.get("node_type", "file"),
                                    file_path=imp_data.get("file_path") or imp_data.get("relative_path"),
                                    depth=next_depth,
                                    direct_relationship=EdgeType.IMPORTS,
                                    path=path + [parent_file_id, file_importer_id],
                                    tags=["COARSE_FILE_DEPENDENT"],
                                    metadata=dict(imp_data.get("metadata", {})),
                                )
                                impacted_edges.append(BlastRadiusEdge(
                                    source=file_importer_id,
                                    target=parent_file_id,
                                    edge_type=EdgeType.IMPORTS,
                                    metadata={"granularity_lifting": True, "target_symbol": curr_id},
                                ))
                                queue.append((file_importer_id, next_depth, path + [file_importer_id]))

        # Step 3: Strictly 1-Hop Temporal Co-Change Expansion
        if include_temporal:
            self._expand_temporal_coupling(target, impacted_nodes, impacted_edges, visited_nodes)

        # Build summary statistics
        nodes_list = list(impacted_nodes.values())
        nodes_list.sort(key=lambda n: (n.depth, n.name))

        counts_by_type: Dict[str, int] = {}
        counts_by_depth: Dict[int, int] = {}
        counts_by_tag: Dict[str, int] = {}

        for n in nodes_list:
            counts_by_type[n.entity_type] = counts_by_type.get(n.entity_type, 0) + 1
            counts_by_depth[n.depth] = counts_by_depth.get(n.depth, 0) + 1
            for tag in n.tags:
                counts_by_tag[tag] = counts_by_tag.get(tag, 0) + 1

        return BlastRadiusReport(
            target=target,
            max_depth=depth_limit,
            total_impacted=len(nodes_list),
            impacted_nodes=nodes_list,
            impacted_edges=impacted_edges,
            counts_by_type=counts_by_type,
            counts_by_depth=counts_by_depth,
            counts_by_tag=counts_by_tag,
        )

    def _expand_contained_members(self, target: ChangeTarget) -> Dict[str, Dict[str, Any]]:
        """
        Discover contained members when target is a FILE or CLASS.
        Traverses outgoing CONTAINS edges downwards.
        """
        members: Dict[str, Dict[str, Any]] = {}
        target_id = target.node_id

        if target.entity_type in (NodeType.FILE, NodeType.CLASS):
            for succ_id in self.graph.successors(target_id):
                edge_data = self.graph.get_edge_data(target_id, succ_id) or {}
                if edge_data.get("edge_type") == EdgeType.CONTAINS:
                    members[succ_id] = self.graph.nodes[succ_id]
                    # If target is file, and succ is class, also expand class methods
                    if target.entity_type == NodeType.FILE and self.graph.nodes[succ_id].get("node_type") == NodeType.CLASS:
                        for class_child in self.graph.successors(succ_id):
                            c_edge = self.graph.get_edge_data(succ_id, class_child) or {}
                            if c_edge.get("edge_type") == EdgeType.CONTAINS:
                                members[class_child] = self.graph.nodes[class_child]
        return members

    def _find_parent_file_id(self, node_id: str, data: Dict[str, Any]) -> Optional[str]:
        """Find the containing File node ID for a symbol."""
        # 1. Check incoming CONTAINS edge to a file node
        for pred in self.graph.predecessors(node_id):
            edge = self.graph.get_edge_data(pred, node_id) or {}
            if edge.get("edge_type") == EdgeType.CONTAINS:
                if self.graph.nodes[pred].get("node_type") == NodeType.FILE:
                    return pred
                # If parent is a class, check class's parent file
                for grandparent in self.graph.predecessors(pred):
                    gp_edge = self.graph.get_edge_data(grandparent, pred) or {}
                    if gp_edge.get("edge_type") == EdgeType.CONTAINS:
                        if self.graph.nodes[grandparent].get("node_type") == NodeType.FILE:
                            return grandparent

        # 2. Check relative_path property
        rel_path = data.get("relative_path")
        if rel_path:
            norm_path = rel_path.replace("\\", "/").strip("/")
            file_id = f"file:{norm_path}"
            if file_id in self.graph:
                return file_id

        return None

    def _expand_temporal_coupling(
        self,
        target: ChangeTarget,
        impacted_nodes: Dict[str, BlastRadiusNode],
        impacted_edges: List[BlastRadiusEdge],
        visited_nodes: Set[str],
    ) -> None:
        """
        Add strictly 1-hop logical co-change coupling.
        Never traverses CO_CHANGED_WITH transitively.
        """
        from pathlib import Path
        target_file_id: Optional[str] = None
        if target.entity_type == NodeType.FILE:
            target_file_id = target.node_id
        else:
            target_file_id = self._find_parent_file_id(target.node_id, self.graph.nodes.get(target.node_id, {}))

        norm_target_file = target.relative_path or target.file_path or ""
        if isinstance(norm_target_file, str):
            norm_target_file = norm_target_file.replace("\\", "/").strip("/")
            while norm_target_file.startswith("./"):
                norm_target_file = norm_target_file[2:]
        else:
            norm_target_file = ""

        if not target_file_id and norm_target_file:
            cand_id = f"file:{norm_target_file}"
            if cand_id in self.graph:
                target_file_id = cand_id

        # Collect 1-hop coupled partners and metadata
        coupled_candidates: List[Tuple[str, str, Dict[str, Any]]] = []

        # 1. Discover via graph edges (both successors and predecessors for bidirectional completeness)
        if target_file_id and target_file_id in self.graph:
            for succ in self.graph.successors(target_file_id):
                ed = self.graph.get_edge_data(target_file_id, succ) or {}
                if ed.get("edge_type") == EdgeType.CO_CHANGED_WITH:
                    p_path = (self.graph.nodes[succ].get("file_path") or self.graph.nodes[succ].get("relative_path") or "").replace("\\", "/")
                    if not p_path and succ.startswith("file:"):
                        p_path = succ[5:]
                    coupled_candidates.append((p_path, succ, ed))

            for pred in self.graph.predecessors(target_file_id):
                ed = self.graph.get_edge_data(pred, target_file_id) or {}
                if ed.get("edge_type") == EdgeType.CO_CHANGED_WITH:
                    p_path = (self.graph.nodes[pred].get("file_path") or self.graph.nodes[pred].get("relative_path") or "").replace("\\", "/")
                    if not p_path and pred.startswith("file:"):
                        p_path = pred[5:]
                    coupled_candidates.append((p_path, pred, ed))

        # 2. Discover via coupling_analyzer if available
        if self.coupling_analyzer and norm_target_file:
            norm_target_lower = norm_target_file.lower()
            couplings = getattr(self.coupling_analyzer, "couplings", [])
            if isinstance(couplings, (list, tuple, set)):
                for c in couplings:
                    raw_a = getattr(c, "canonical_file_a", None)
                    if not isinstance(raw_a, str):
                        raw_a = getattr(c, "file_a", "")
                    raw_b = getattr(c, "canonical_file_b", None)
                    if not isinstance(raw_b, str):
                        raw_b = getattr(c, "file_b", "")

                    file_a = raw_a.replace("\\", "/").strip("/") if isinstance(raw_a, str) else ""
                    file_b = raw_b.replace("\\", "/").strip("/") if isinstance(raw_b, str) else ""
                    while file_a.startswith("./"):
                        file_a = file_a[2:]
                    while file_b.startswith("./"):
                        file_b = file_b[2:]

                    if norm_target_lower in (file_a.lower(), file_b.lower()):
                        partner_file = file_b if norm_target_lower == file_a.lower() else file_a
                        partner_node_id = f"file:{partner_file}"
                        meta = {
                            "canonical_file_a": file_a,
                            "canonical_file_b": file_b,
                            "support_count": getattr(c, "support_count", 0),
                            "jaccard_similarity": getattr(c, "jaccard_similarity", 0.0),
                            "confidence_a_to_b": getattr(c, "confidence_a_to_b", 0.0),
                            "confidence_b_to_a": getattr(c, "confidence_b_to_a", 0.0),
                            "last_co_change_date": getattr(c, "last_co_change_date", None),
                            "is_temporal": True,
                        }
                        coupled_candidates.append((partner_file, partner_node_id, meta))

        # 3. Add to blast radius deterministically without duplicates
        for partner_file, partner_node_id, meta in coupled_candidates:
            if not partner_file or partner_node_id in visited_nodes:
                continue

            visited_nodes.add(partner_node_id)
            n_data = self.graph.nodes.get(partner_node_id, {})
            display_name = n_data.get("name") or Path(partner_file).name

            impacted_nodes[partner_node_id] = BlastRadiusNode(
                node_id=partner_node_id,
                name=display_name,
                entity_type=n_data.get("node_type", NodeType.FILE),
                file_path=partner_file,
                depth=1,  # Strictly 1-hop
                direct_relationship=EdgeType.CO_CHANGED_WITH,
                path=[target.node_id, partner_node_id],
                tags=["TEMPORAL_CO_CHANGE"],
                metadata=dict(meta),
            )
            impacted_edges.append(BlastRadiusEdge(
                source=target_file_id or target.node_id,
                target=partner_node_id,
                edge_type=EdgeType.CO_CHANGED_WITH,
                metadata=dict(meta),
            ))
            # IMPORTANT: Not added to queue! Strictly 1-hop!
