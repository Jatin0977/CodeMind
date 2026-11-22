"""
FastAPI application backend for CodeMind Web UI — Ingestion & Static Code Analysis Dashboard.
Prepared for College Evaluation 1 (Technical Phases 1 and 2).
"""

import os
import time
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from ..ingestion.repo_loader import RepositoryLoader
from ..ingestion.models import IngestedRepository, SourceFile
from ..parsing.parser_factory import GLOBAL_PARSER_FACTORY
from ..parsing.base_parser import ParsedFile

from ..chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from ..chunking.models import CodeChunk
from ..retrieval.retriever import SemanticRetriever
from ..retrieval.hybrid_retriever import HybridGraphRetriever
from ..rag.engine import RAGEngine
from ..rag.models import RAGResponse
from ..rag.providers.factory import get_llm_provider
from ..graph.models import NodeType, EdgeType, Node, Edge, GraphSummary
from ..graph.builder import KnowledgeGraphBuilder
from ..graph.query import GraphQueryEngine
from ..investigation.engine import InvestigationEngine
from ..investigation.models import InvestigationResult
from ..impact.models import (
    AmbiguousTargetError,
    TargetNotFoundError,
    TargetResolutionError,
    ImpactAnalysisConfig,
)
from ..impact.resolver import ChangeTargetResolver
from ..impact.engine import ChangeImpactEngine
from ..impact.scorer import MultiSignalImpactScorer
from ..impact.test_intelligence import TestIntelligenceEngine


class ScanRequest(BaseModel):
    repo_path: str = Field(default=".", description="Local repository path, ZIP file, or Git clone URL to scan")


class AskRequest(BaseModel):
    question: str = Field(..., description="Developer question")
    top_k: int = Field(default=4, ge=1, le=10, description="Top evidence chunks to retrieve")
    mock: bool = Field(default=False, description="Use Mock LLM provider for offline demo")
    model: Optional[str] = Field(default=None, description="Optional LLM model name")
    use_graph: bool = Field(default=True, description="Enable hybrid graph-aware retrieval")


class InvestigateRequest(BaseModel):
    query: str = Field(..., description="Developer investigation query")
    mock: bool = Field(default=False, description="Use Mock LLM provider for offline demo")
    model: Optional[str] = Field(default=None, description="Optional LLM model name")


class ImpactAnalyzeRequest(BaseModel):
    target: str = Field(..., description="Target entity: canonical node ID, file path, or symbol name")
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum traversal depth for blast radius")
    include_temporal: bool = Field(default=True, description="Include strictly 1-hop logical co-change coupling")


class ImpactTestsRequest(BaseModel):
    target: str = Field(..., description="Target entity: canonical node ID, file path, or symbol name")
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum traversal depth for blast radius")


class CodebaseState:
    """
    Session state holding the currently ingested repository and static analysis results.

    DEPLOYMENT CONCURRENCY MODEL:
    In-process synchronization (threading.RLock) provides strict thread-safety and serialized
    access to mutable repository models within a SINGLE operating system process (e.g. uvicorn --workers 1).
    Process-local locks do NOT protect shared state across multiple OS worker processes (uvicorn --workers N).
    Multi-worker horizontal scaling requires centralized external state (e.g. Redis or database-backed state).
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.repo: Optional[IngestedRepository] = None
        self.parsed_files: Dict[str, ParsedFile] = {}  # rel_path -> ParsedFile
        self.static_metrics: Dict[str, Any] = {}
        self.chunks: List[CodeChunk] = []
        self.chunk_breakdown: Dict[str, int] = {}
        self.retriever = SemanticRetriever()
        self.hybrid_retriever: Optional[HybridGraphRetriever] = None
        self.graph_builder = KnowledgeGraphBuilder()
        self.graph_query_engine: Optional[GraphQueryEngine] = None
        self.git_client: Optional[Any] = None
        self.git_miner: Optional[Any] = None
        self.git_churn_analyzer: Optional[Any] = None
        self.git_coupling_analyzer: Optional[Any] = None
        self.git_status: Optional[Dict[str, Any]] = None
        self.git_commits: List[Any] = []
        self.git_churn_summary: Optional[Dict[str, Any]] = None
        self.git_couplings: List[Any] = []
        self.impact_engine: Optional[ChangeImpactEngine] = None
        self.impact_scorer: Optional[MultiSignalImpactScorer] = None
        self.test_engine: Optional[TestIntelligenceEngine] = None
        self.architecture_discovery: Optional[Any] = None
        self.architecture_conformance: Optional[Any] = None
        self.hotspot_detector: Optional[Any] = None
        self.architecture_modules: Optional[Any] = None
        self.architecture_layers: Optional[Any] = None
        self.quotient_graph: Optional[Any] = None

    def scan_and_analyze(self, repo_path: str) -> Dict[str, Any]:
        """
        Load repository (local, ZIP, or Git URL), extract AST symbols, and compute static metrics.
        Thread-safe under single-process concurrency.
        """
        with self._lock:
            return self._scan_and_analyze_impl(repo_path)

    def _scan_and_analyze_impl(self, repo_path: str) -> Dict[str, Any]:
        # Reset Git temporal intelligence state to prevent stale state bleed across scans
        self.git_client = None
        self.git_miner = None
        self.git_churn_analyzer = None
        self.git_coupling_analyzer = None
        self.git_status = None
        self.git_commits = []
        self.git_churn_summary = None
        self.git_couplings = []

        # Reset Phase 8 Impact state
        self.impact_engine = None
        self.impact_scorer = None
        self.test_engine = None

        loader = RepositoryLoader()
        self.repo = loader.load_repository(repo_path)
        self.parsed_files.clear()
        self.chunks.clear()
        self.chunk_breakdown.clear()

        total_classes = 0
        total_functions = 0
        total_methods = 0
        total_imports = 0
        total_docstrings = 0
        syntax_errors = 0
        file_analysis_list: List[Dict[str, Any]] = []

        for sf in self.repo.files:
            parsed = GLOBAL_PARSER_FACTORY.parse(sf)
            file_meta = {
                "relative_path": sf.relative_path,
                "file_name": sf.file_name,
                "language": sf.language,
                "line_count": sf.line_count,
                "file_size": sf.file_size,
                "is_python": sf.is_python,
                "is_doc": sf.is_documentation,
                "classes_count": 0,
                "functions_count": 0,
                "methods_count": 0,
                "imports_count": 0,
                "has_docstring": False,
                "is_valid": True,
                "error": None,
            }

            if parsed:
                self.parsed_files[sf.relative_path] = parsed
                file_meta["is_valid"] = parsed.is_valid
                file_meta["error"] = parsed.error

                if parsed.is_valid:
                    c_count = len(parsed.classes)
                    f_count = len(parsed.functions)
                    m_count = sum(len(c.methods) for c in parsed.classes)
                    i_count = len(parsed.imports)
                    has_doc = bool(parsed.docstring)

                    total_classes += c_count
                    total_functions += f_count
                    total_methods += m_count
                    total_imports += i_count
                    if has_doc:
                        total_docstrings += 1

                    file_meta["classes_count"] = c_count
                    file_meta["functions_count"] = f_count
                    file_meta["methods_count"] = m_count
                    file_meta["imports_count"] = i_count
                    file_meta["has_docstring"] = has_doc
                else:
                    syntax_errors += 1

            file_analysis_list.append(file_meta)

            # Chunk file into semantic units (Phase 3)
            file_chunks = GLOBAL_CHUNKER_FACTORY.chunk_file(sf, parsed)
            self.chunks.extend(file_chunks)
            for c in file_chunks:
                self.chunk_breakdown[c.chunk_type] = self.chunk_breakdown.get(c.chunk_type, 0) + 1

        self.static_metrics = {
            "classes": total_classes,
            "functions": total_functions,
            "methods": total_methods,
            "imports": total_imports,
            "docstrings": total_docstrings,
            "syntax_errors": syntax_errors,
        }

        # Index in vector store (Phase 3)
        indexed_chunks_count = self.retriever.index_chunks(self.chunks)

        # Construct Software Knowledge Graph (Phase 4)
        nx_graph = self.graph_builder.build(self.repo, self.parsed_files)
        self.graph_query_engine = GraphQueryEngine(nx_graph, self.graph_builder.nodes_by_id)
        graph_summary = self.graph_builder.get_summary().to_dict()

        # Initialize Hybrid Graph-Aware Retriever (Phase 5)
        self.hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=nx_graph,
            query_engine=self.graph_query_engine,
        )
        self.hybrid_retriever.index(self.chunks, nx_graph)

        # Git Temporal Intelligence (Phase 7)
        try:
            from ..git.client import GitClient
            from ..git.miner import GitMiner
            from ..git.churn import CodeChurnAnalyzer
            from ..git.coupling import LogicalCouplingAnalyzer

            client = GitClient(self.repo.repo_path)
            status = client.get_status()
            self.git_status = status.to_dict()
            if status.is_git_repo and not status.is_empty:
                self.git_client = client
                self.git_miner = GitMiner(client)
                self.git_commits = self.git_miner.mine_commits(max_commits=1000)

                self.git_churn_analyzer = CodeChurnAnalyzer()
                churn_res = self.git_churn_analyzer.analyze(self.git_commits)
                self.git_churn_summary = churn_res.to_dict()

                self.git_coupling_analyzer = LogicalCouplingAnalyzer(min_support=3, min_confidence=0.5)
                coupling_res = self.git_coupling_analyzer.analyze(self.git_commits)
                self.git_couplings = coupling_res.couplings

                # Materialize temporal knowledge graph into nx_graph
                self.graph_builder.materialize_temporal_graph(
                    self.git_commits,
                    self.git_couplings,
                    max_materialize_commits=100,
                )
                graph_summary = self.graph_builder.get_summary().to_dict()
        except Exception as e:
            self.git_status = {"is_git_repo": False, "error": str(e)}

        # Initialize Phase 8: Change Impact and Test Intelligence
        try:
            if self.graph_builder and self.graph_builder.graph:
                has_tests = any(
                    "test" in (f.relative_path or "").lower() for f in self.repo.files
                ) if self.repo else False
                commits_count = len(self.git_commits) if self.git_commits else 0

                self.impact_engine = ChangeImpactEngine(
                    graph=self.graph_builder.graph,
                    coupling_analyzer=self.git_coupling_analyzer,
                )
                self.impact_scorer = MultiSignalImpactScorer(
                    churn_analyzer=self.git_churn_analyzer,
                    coupling_analyzer=self.git_coupling_analyzer,
                    has_git=bool(self.git_client and getattr(self.git_client, "is_git_repository", False)),
                    total_repo_commits=commits_count,
                    has_tests=has_tests,
                )
                self.test_engine = TestIntelligenceEngine(
                    graph=self.graph_builder.graph,
                    coupling_analyzer=self.git_coupling_analyzer,
                    repo=self.repo,
                )
        except Exception:
            self.impact_engine = None
            self.impact_scorer = None
            self.test_engine = None

        # Initialize Phase 9: Architecture Intelligence
        try:
            from ..architecture import ArchitectureDiscoveryEngine, ArchitectureConformanceEngine, MaintenanceHotspotDetector
            self.architecture_discovery = ArchitectureDiscoveryEngine(repo_root=self.repo.repo_path)
            self.architecture_modules = self.architecture_discovery.discover_modules(
                files=self.repo.files,
                parsed_files=self.parsed_files,
            )
            self.quotient_graph, _ = self.architecture_discovery.build_quotient_graph(
                modules_map=self.architecture_modules,
                parsed_files=self.parsed_files,
            )
            self.architecture_layers = self.architecture_discovery.layers
            self.architecture_conformance = ArchitectureConformanceEngine(
                layers=self.architecture_layers,
                modules_map=self.architecture_modules,
                quotient_graph=self.quotient_graph,
            )
            self.hotspot_detector = MaintenanceHotspotDetector()
        except Exception:
            self.architecture_discovery = None
            self.architecture_conformance = None
            self.hotspot_detector = None
            self.architecture_modules = None
            self.architecture_layers = None
            self.quotient_graph = None

        # Update hybrid retriever with domain intelligence context
        if self.hybrid_retriever:
            self.hybrid_retriever.domain_context = {
                "git_churn_summary": self.git_churn_summary,
                "architecture_conformance": self.architecture_conformance,
                "architecture_modules": self.architecture_modules,
                "hotspot_detector": self.hotspot_detector,
            }

        # Prepare file tree items
        files_data = [
            {
                "file_path": f.file_path,
                "relative_path": f.relative_path,
                "file_name": f.file_name,
                "language": f.language,
                "file_size": f.file_size,
                "line_count": f.line_count,
                "is_python": f.is_python,
                "is_doc": f.is_documentation,
            }
            for f in self.repo.files
        ]

        return {
            "repository": self.repo.repo_name,
            "repo_path": self.repo.repo_path,
            "total_files": self.repo.summary.total_files,
            "total_lines": self.repo.summary.total_lines,
            "total_size_bytes": self.repo.summary.total_size_bytes,
            "languages": self.repo.summary.language_breakdown,
            "skipped_count": self.repo.summary.skipped_count,
            "skipped_files": self.repo.summary.skipped_files[:10],
            "ast_metrics": self.static_metrics,
            "file_analysis": file_analysis_list,
            "total_chunks": len(self.chunks),
            "chunk_breakdown": self.chunk_breakdown,
            "indexed_chunks": indexed_chunks_count,
            "graph_summary": graph_summary,
            "git_status": self.git_status,
            "git_commits_count": len(self.git_commits),
            "git_churn_summary": self.git_churn_summary,
            "git_couplings_count": len(self.git_couplings),
            "files": files_data,
        }

    # Alias for backwards compatibility
    scan_and_index = scan_and_analyze


# Global session instance
GLOBAL_STATE = CodebaseState()
_STATE_ASYNC_LOCK: Optional[asyncio.Lock] = None


def get_state_async_lock() -> asyncio.Lock:
    global _STATE_ASYNC_LOCK
    if _STATE_ASYNC_LOCK is None:
        _STATE_ASYNC_LOCK = asyncio.Lock()
    return _STATE_ASYNC_LOCK


def create_app():
    """Create and configure the FastAPI web application."""
    from fastapi import FastAPI, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="CodeMind — Repository Ingestion & Static Code Analysis",
        description="College Evaluation 1: Technical Phases 1 & 2 Platform",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return HTMLResponse("<h1>CodeMind UI Initializing...</h1>")

    @app.get("/api/health")
    def health_check():
        has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        return {
            "status": "healthy",
            "version": "0.1.0",
            "evaluation_phase": "Evaluation 3: Technical Phases 1–5",
            "has_gemini_key": has_gemini,
            "embedding_model": GLOBAL_STATE.retriever.embedding_provider.model_name,
            "is_scanned": GLOBAL_STATE.repo is not None,
            "is_indexed": GLOBAL_STATE.repo is not None and len(GLOBAL_STATE.chunks) > 0,
            "has_graph": GLOBAL_STATE.graph_query_engine is not None,
            "has_hybrid_retriever": GLOBAL_STATE.hybrid_retriever is not None,
            "total_graph_nodes": len(GLOBAL_STATE.graph_builder.nodes_by_id) if GLOBAL_STATE.graph_builder else 0,
            "total_graph_edges": len(GLOBAL_STATE.graph_builder.edges_list) if GLOBAL_STATE.graph_builder else 0,
            "repo_name": GLOBAL_STATE.repo.repo_name if GLOBAL_STATE.repo else None,
            "total_files": GLOBAL_STATE.repo.summary.total_files if GLOBAL_STATE.repo else 0,
            "total_chunks": len(GLOBAL_STATE.chunks),
        }

    @app.post("/api/scan")
    async def scan_repository(request: ScanRequest):
        if not request.repo_path or not request.repo_path.strip():
            raise HTTPException(status_code=400, detail="Repository path cannot be empty.")
        clean_path = request.repo_path.strip()
        if not (clean_path.startswith("http://") or clean_path.startswith("https://") or clean_path.endswith(".zip")):
            p = Path(clean_path).resolve()
            if not p.exists():
                raise HTTPException(status_code=404, detail=f"Repository path does not exist: {clean_path}")

        async with get_state_async_lock():
            try:
                summary = GLOBAL_STATE.scan_and_analyze(clean_path)
                return summary
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except NotADirectoryError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/ask")
    def ask_question(request: AskRequest):
        if not request.question or not request.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty.")
        if GLOBAL_STATE.repo is None:
            raise HTTPException(
                status_code=400,
                detail="No repository scanned yet. Please scan a repository first.",
            )

        provider_type = "mock" if request.mock else None
        llm_provider = get_llm_provider(provider_type=provider_type, model_name=request.model)
        rag_engine = RAGEngine(
            retriever=GLOBAL_STATE.retriever,
            hybrid_retriever=GLOBAL_STATE.hybrid_retriever,
            llm_provider=llm_provider,
        )

        response: RAGResponse = rag_engine.ask(
            query=request.question,
            top_k=request.top_k,
            use_graph=request.use_graph,
        )

        data = response.to_dict(include_sources=True)

        # Augment with hybrid retrieval metadata
        is_hybrid = request.use_graph and GLOBAL_STATE.hybrid_retriever is not None
        data["retrieval_mode"] = "hybrid" if is_hybrid else "vector_only"
        seed_count = sum(1 for s in response.sources if getattr(s, "provenance", "vector_seed") == "vector_seed")
        expanded_count = sum(1 for s in response.sources if getattr(s, "provenance", None) == "graph_expanded")
        rels_used = list({getattr(s, "relationship_type", None) for s in response.sources if getattr(s, "relationship_type", None)})

        data["retrieval_metadata"] = {
            "retrieval_mode": data["retrieval_mode"],
            "final_evidence_count": len(response.sources),
            "seed_chunks_count": seed_count,
            "expanded_chunks_count": expanded_count,
            "relationship_types_used": rels_used,
        }

        return data

    @app.post("/api/investigate")
    def investigate_codebase(request: InvestigateRequest):
        """
        Execute an agentic investigation for a developer query (Phase 6).
        Classifies intent, builds a dynamic plan, executes tools deterministically,
        and returns a grounded developer answer with citations.
        """
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Query cannot be empty.",
            )

        if GLOBAL_STATE.repo is None:
            raise HTTPException(
                status_code=400,
                detail="No repository scanned yet. Please scan a repository first.",
            )

        provider_type = "mock" if request.mock else None
        llm_provider = get_llm_provider(provider_type=provider_type, model_name=request.model)

        # Fresh investigation engine instantiated with currently scanned repository components
        engine = InvestigationEngine(
            repo=GLOBAL_STATE.repo,
            query_engine=GLOBAL_STATE.graph_query_engine,
            retriever=GLOBAL_STATE.retriever,
            hybrid_retriever=GLOBAL_STATE.hybrid_retriever,
            git_miner=GLOBAL_STATE.git_miner,
            git_client=GLOBAL_STATE.git_client,
            git_churn_analyzer=GLOBAL_STATE.git_churn_analyzer,
            git_coupling_analyzer=GLOBAL_STATE.git_coupling_analyzer,
            impact_engine=GLOBAL_STATE.impact_engine,
            impact_scorer=GLOBAL_STATE.impact_scorer,
            test_engine=GLOBAL_STATE.test_engine,
            enable_impact=bool(GLOBAL_STATE.impact_engine is not None),
            discovery_engine=getattr(GLOBAL_STATE, "architecture_discovery", None),
            conformance_engine=getattr(GLOBAL_STATE, "architecture_conformance", None),
            hotspot_detector=getattr(GLOBAL_STATE, "hotspot_detector", None),
            enable_architecture=bool(getattr(GLOBAL_STATE, "architecture_discovery", None) is not None),
            modules=getattr(GLOBAL_STATE, "architecture_modules", None),
            layers=getattr(GLOBAL_STATE, "architecture_layers", None),
            quotient_graph=getattr(GLOBAL_STATE, "quotient_graph", None),
            parsed_files=GLOBAL_STATE.parsed_files,
            llm_provider=llm_provider,
        )

        result: InvestigationResult = engine.investigate(request.query)

        intent_val = (
            result.intent.value
            if hasattr(result.intent, "value")
            else str(result.intent) if result.intent else None
        )
        status_val = (
            result.overall_status.value
            if hasattr(result.overall_status, "value")
            else str(result.overall_status)
        )
        classification_data = result.metadata.get("engine", {}).get("classification", {})
        entities_data = classification_data.get("extracted_entities", {})
        raw_entities = entities_data.get("raw_entities", []) if isinstance(entities_data, dict) else []

        return {
            "query": result.query,
            "intent": intent_val,
            "confidence": classification_data.get("confidence", 0.0),
            "confidence_category": classification_data.get("confidence_category", "LOW"),
            "extracted_entities": raw_entities,
            "entities_detail": entities_data,
            "status": status_val,
            "overall_status": status_val,
            "plan": result.plan.to_dict() if result.plan else None,
            "step_results": [r.to_dict() for r in result.step_results],
            "answer": result.final_answer,
            "final_answer": result.final_answer,
            "evidence": result.evidence,
            "citations": result.metadata.get("citations", []),
            "metadata": result.metadata,
        }

    @app.get("/api/file")
    def get_file_content(path: str):
        if not path or not path.strip():
            raise HTTPException(status_code=400, detail="File path cannot be empty.")
        if ".." in path or path.startswith("/") or path.startswith("\\"):
            raise HTTPException(status_code=400, detail="Path traversal ('..') is strictly prohibited.")
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")

        sf: Optional[SourceFile] = GLOBAL_STATE.repo.get_file_by_relative_path(path)
        if not sf:
            raise HTTPException(status_code=404, detail=f"File not found in repository: {path}")

        parsed: Optional[ParsedFile] = GLOBAL_STATE.parsed_files.get(sf.relative_path)
        symbols_data = parsed.to_dict() if parsed else None

        return {
            "relative_path": sf.relative_path,
            "file_name": sf.file_name,
            "language": sf.language,
            "line_count": sf.line_count,
            "file_size": sf.file_size,
            "content": sf.content,
            "symbols": symbols_data,
        }

    @app.get("/api/symbols")
    def get_symbols(path: str):
        if not path or not path.strip():
            raise HTTPException(status_code=400, detail="File path cannot be empty.")
        if ".." in path or path.startswith("/") or path.startswith("\\"):
            raise HTTPException(status_code=400, detail="Path traversal ('..') is strictly prohibited.")
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")

        parsed: Optional[ParsedFile] = GLOBAL_STATE.parsed_files.get(path.replace("\\", "/"))
        if not parsed:
            raise HTTPException(status_code=404, detail=f"No parsed symbols found for: {path}")

        return parsed.to_dict()

    @app.get("/api/graph")
    def get_knowledge_graph(
        node_type: Optional[str] = None,
        query: Optional[str] = None,
        max_nodes: int = 500,
    ):
        """
        Return the software knowledge graph nodes and edges.
        Supports filtering by node_type and search query substring.
        """
        if GLOBAL_STATE.repo is None or GLOBAL_STATE.graph_query_engine is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")

        summary = GLOBAL_STATE.graph_builder.get_summary().to_dict()
        nodes = [n.to_dict() for n in GLOBAL_STATE.graph_builder.nodes_by_id.values()]

        if node_type:
            nodes = [n for n in nodes if n.get("node_type") == node_type]

        if query:
            q = query.lower().strip()
            nodes = [
                n for n in nodes
                if q in n.get("name", "").lower()
                or q in n.get("relative_path", "").lower()
                or q in n.get("id", "").lower()
            ]

        if len(nodes) > max_nodes:
            nodes = nodes[:max_nodes]

        node_id_set = {n["id"] for n in nodes}
        edges = [
            e.to_dict() for e in GLOBAL_STATE.graph_builder.edges_list
            if e.source in node_id_set and e.target in node_id_set
        ]

        return {
            "summary": summary,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

    @app.get("/api/graph/impact")
    def get_graph_impact(node_id: str, max_depth: int = 3):
        """
        Return structural reachability impact analysis for a given node.
        Traces reverse dependencies (incoming CALLS, INHERITS, IMPORTS) up to max_depth.
        """
        if GLOBAL_STATE.repo is None or GLOBAL_STATE.graph_query_engine is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")

        result = GLOBAL_STATE.graph_query_engine.trace_impact(node_id, max_depth=max_depth)
        if not result.get("found"):
            raise HTTPException(status_code=404, detail=result.get("error", f"Node '{node_id}' not found"))

        return result

    @app.get("/api/graph/node")
    def get_graph_node_details(node_id: str):
        """
        Return detailed query information for a specific node:
        Callers, callees, dependencies, dependents, and dependency depth.
        """
        if GLOBAL_STATE.repo is None or GLOBAL_STATE.graph_query_engine is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")

        node = GLOBAL_STATE.graph_query_engine.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

        return {
            "node": node,
            "callers": GLOBAL_STATE.graph_query_engine.get_callers(node_id),
            "callees": GLOBAL_STATE.graph_query_engine.get_callees(node_id),
            "dependencies": GLOBAL_STATE.graph_query_engine.get_dependencies(node_id),
            "dependents": GLOBAL_STATE.graph_query_engine.get_dependents(node_id),
            "dependency_depth": GLOBAL_STATE.graph_query_engine.get_dependency_depth(node_id),
        }

    @app.get("/api/graph/cycles")
    def get_graph_cycles():
        """Return circular dependencies detected in the software knowledge graph."""
        if GLOBAL_STATE.repo is None or GLOBAL_STATE.graph_query_engine is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")

        cycles = GLOBAL_STATE.graph_query_engine.detect_cycles()
        return {
            "has_cycles": len(cycles) > 0,
            "cycle_count": len(cycles),
            "cycles": cycles,
        }

    # =========================================================================
    # Git Temporal Intelligence Endpoints (Phase 7)
    # =========================================================================

    @app.get("/api/git/status")
    def get_git_status():
        """Return Git repository status summary."""
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        if GLOBAL_STATE.git_status:
            return GLOBAL_STATE.git_status
        if GLOBAL_STATE.git_client:
            return GLOBAL_STATE.git_client.get_status().to_dict()
        return {"is_git_repo": False, "error": "Not a Git repository"}

    @app.get("/api/git/history")
    def get_git_history(
        path: Optional[str] = None,
        limit: int = 50,
        since: Optional[str] = None,
        author: Optional[str] = None,
    ):
        """Retrieve mined Git commit history with file change diffs."""
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        if not GLOBAL_STATE.git_miner:
            if GLOBAL_STATE.graph_query_engine and path:
                commits = GLOBAL_STATE.graph_query_engine.get_file_commits(path, limit=limit)
                return {"commits": commits, "total_commits": len(commits), "filtered_path": path}
            raise HTTPException(status_code=400, detail="Git repository history is not available.")

        try:
            commits = GLOBAL_STATE.git_miner.mine_commits(
                max_commits=limit,
                path=path,
                since=since,
                author=author,
            )
            serialized = [c.to_dict() for c in commits]
            return {"commits": serialized, "total_commits": len(serialized), "filtered_path": path}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error mining commit history: {str(e)}")

    @app.get("/api/git/churn")
    def get_git_churn(
        limit: int = 50,
        sort_by: str = "commits",
        path: Optional[str] = None,
    ):
        """Retrieve code churn metrics and revision hotspots."""
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        if not GLOBAL_STATE.git_churn_analyzer:
            raise HTTPException(status_code=400, detail="Git code churn is not available.")

        try:
            hotspots = GLOBAL_STATE.git_churn_analyzer.get_top_churn_files(
                limit=limit if not path else 1000,
                sort_by=sort_by,
            )
            if path:
                norm_p = path.replace("\\", "/").lower()
                hotspots = [h for h in hotspots if norm_p in h.path.lower()][:limit]

            summary = GLOBAL_STATE.git_churn_analyzer.summary.to_dict() if GLOBAL_STATE.git_churn_analyzer.summary else {}
            return {
                "summary": summary,
                "hotspots": [h.to_dict() for h in hotspots],
                "total_returned": len(hotspots),
                "filtered_path": path,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error retrieving churn: {str(e)}")

    @app.get("/api/git/coupling")
    def get_git_coupling(
        file_path: Optional[str] = None,
        min_support: int = 3,
        min_confidence: float = 0.5,
        limit: int = 50,
    ):
        """Retrieve logical couplings discovered from commit co-change history."""
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        if not GLOBAL_STATE.git_coupling_analyzer:
            if GLOBAL_STATE.graph_query_engine and file_path:
                couplings = GLOBAL_STATE.graph_query_engine.get_logically_coupled_files(file_path, limit=limit)
                return {"focal_file": file_path, "couplings": couplings, "total_couplings": len(couplings)}
            raise HTTPException(status_code=400, detail="Git logical coupling is not available.")

        try:
            analyzer = GLOBAL_STATE.git_coupling_analyzer
            if min_support != analyzer.min_support or min_confidence != analyzer.min_confidence:
                if GLOBAL_STATE.git_commits:
                    res = analyzer.analyze(
                        GLOBAL_STATE.git_commits,
                        min_support=min_support,
                        min_confidence=min_confidence,
                    )
            if file_path:
                oriented = analyzer.get_couplings_for_file(
                    file_path,
                    min_support=min_support,
                    min_confidence=min_confidence,
                )[:limit]
                return {
                    "focal_file": file_path,
                    "couplings": oriented,
                    "total_couplings": len(oriented),
                }
            else:
                top = analyzer.get_top_couplings(limit=limit)
                return {
                    "focal_file": None,
                    "couplings": [c.to_dict() for c in top],
                    "total_couplings": len(top),
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error retrieving coupling: {str(e)}")

    # =========================================================================
    # Change Impact and Test Intelligence Endpoints (Phase 8)
    # =========================================================================

    def _handle_impact_analysis(target: str, max_depth: int, include_temporal: bool):
        if GLOBAL_STATE.repo is None or GLOBAL_STATE.graph_builder is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        if not target or not target.strip():
            raise HTTPException(status_code=400, detail="Target cannot be empty.")

        g = GLOBAL_STATE.graph_builder.graph
        if not g or g.number_of_nodes() == 0:
            raise HTTPException(status_code=400, detail="Knowledge graph is empty or uninitialized.")

        resolver = ChangeTargetResolver(g)
        try:
            resolved_target = resolver.resolve(target)
        except AmbiguousTargetError as err:
            raise HTTPException(
                status_code=400,
                detail=err.to_dict(),
            )
        except TargetNotFoundError as err:
            raise HTTPException(
                status_code=404,
                detail=err.to_dict(),
            )
        except Exception as ex:
            raise HTTPException(status_code=400, detail=f"Target resolution error: {str(ex)}")

        impact_engine = GLOBAL_STATE.impact_engine or ChangeImpactEngine(
            graph=g,
            coupling_analyzer=GLOBAL_STATE.git_coupling_analyzer,
        )
        test_engine = GLOBAL_STATE.test_engine or TestIntelligenceEngine(
            graph=g,
            coupling_analyzer=GLOBAL_STATE.git_coupling_analyzer,
            repo=GLOBAL_STATE.repo,
        )
        has_tests = any("test" in (f.relative_path or "").lower() for f in GLOBAL_STATE.repo.files) if GLOBAL_STATE.repo else False
        commits_count = len(GLOBAL_STATE.git_commits) if GLOBAL_STATE.git_commits else 0

        scorer = GLOBAL_STATE.impact_scorer or MultiSignalImpactScorer(
            churn_analyzer=GLOBAL_STATE.git_churn_analyzer,
            coupling_analyzer=GLOBAL_STATE.git_coupling_analyzer,
            has_git=bool(GLOBAL_STATE.git_client and getattr(GLOBAL_STATE.git_client, "is_git_repository", False)),
            total_repo_commits=commits_count,
            has_tests=has_tests,
        )

        blast_radius = impact_engine.analyze_blast_radius(
            target=resolved_target,
            max_depth=max_depth,
            include_temporal=include_temporal,
        )
        centrality = impact_engine.compute_centrality(resolved_target.node_id)
        test_report = test_engine.analyze_tests(resolved_target, blast_radius)

        report = scorer.compute_impact(
            target=resolved_target,
            blast_radius=blast_radius,
            centrality=centrality,
            test_report=test_report,
        )
        return report.to_dict()

    @app.post("/api/impact/analyze")
    def analyze_change_impact_post(request: ImpactAnalyzeRequest):
        """Analyze multi-signal change impact and blast radius for target entity (POST)."""
        return _handle_impact_analysis(
            target=request.target,
            max_depth=request.max_depth,
            include_temporal=request.include_temporal,
        )

    @app.get("/api/impact/analyze")
    def analyze_change_impact_get(
        target: str,
        max_depth: int = 3,
        include_temporal: bool = True,
    ):
        """Analyze multi-signal change impact and blast radius for target entity (GET)."""
        return _handle_impact_analysis(
            target=target,
            max_depth=max_depth,
            include_temporal=include_temporal,
        )

    def _handle_impact_tests(target: str, max_depth: int):
        if GLOBAL_STATE.repo is None or GLOBAL_STATE.graph_builder is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        if not target or not target.strip():
            raise HTTPException(status_code=400, detail="Target cannot be empty.")

        g = GLOBAL_STATE.graph_builder.graph
        if not g or g.number_of_nodes() == 0:
            raise HTTPException(status_code=400, detail="Knowledge graph is empty or uninitialized.")

        resolver = ChangeTargetResolver(g)
        try:
            resolved_target = resolver.resolve(target)
        except AmbiguousTargetError as err:
            raise HTTPException(status_code=400, detail=err.to_dict())
        except TargetNotFoundError as err:
            raise HTTPException(status_code=404, detail=err.to_dict())
        except Exception as ex:
            raise HTTPException(status_code=400, detail=f"Target resolution error: {str(ex)}")

        impact_engine = GLOBAL_STATE.impact_engine or ChangeImpactEngine(
            graph=g,
            coupling_analyzer=GLOBAL_STATE.git_coupling_analyzer,
        )
        test_engine = GLOBAL_STATE.test_engine or TestIntelligenceEngine(
            graph=g,
            coupling_analyzer=GLOBAL_STATE.git_coupling_analyzer,
            repo=GLOBAL_STATE.repo,
        )

        blast_radius = impact_engine.analyze_blast_radius(
            target=resolved_target,
            max_depth=max_depth,
        )
        test_report = test_engine.analyze_tests(resolved_target, blast_radius)
        return test_report.to_dict()

    @app.post("/api/impact/tests")
    def analyze_impact_tests_post(request: ImpactTestsRequest):
        """Discover and rank candidate regression tests across blast radius (POST)."""
        return _handle_impact_tests(target=request.target, max_depth=request.max_depth)

    @app.get("/api/impact/tests")
    def analyze_impact_tests_get(target: str, max_depth: int = 3):
        """Discover and rank candidate regression tests across blast radius (GET)."""
        return _handle_impact_tests(target=target, max_depth=max_depth)

    # -------------------------------------------------------------------------
    # Architecture Intelligence Endpoints (Phase 9 REST Activation)
    # -------------------------------------------------------------------------

    @app.get("/api/architecture/overview")
    def get_architecture_overview():
        """Retrieve architectural module hierarchy, layers, and quotient graph."""
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        if not GLOBAL_STATE.architecture_discovery:
            raise HTTPException(status_code=400, detail="Architecture discovery not initialized.")

        modules_data = {
            k: (v.to_dict() if hasattr(v, "to_dict") else v)
            for k, v in (GLOBAL_STATE.architecture_modules or {}).items()
        }
        layers_data = [
            (l.to_dict() if hasattr(l, "to_dict") else l)
            for l in (GLOBAL_STATE.architecture_layers or [])
        ]
        import networkx as nx
        if isinstance(GLOBAL_STATE.quotient_graph, nx.DiGraph):
            quotient_graph_data = {
                "nodes": list(GLOBAL_STATE.quotient_graph.nodes()),
                "edges": [{"source": u, "target": v, **d} for u, v, d in GLOBAL_STATE.quotient_graph.edges(data=True)],
                "node_count": GLOBAL_STATE.quotient_graph.number_of_nodes(),
                "edge_count": GLOBAL_STATE.quotient_graph.number_of_edges(),
            }
        elif hasattr(GLOBAL_STATE.quotient_graph, "to_dict"):
            quotient_graph_data = GLOBAL_STATE.quotient_graph.to_dict()
        else:
            quotient_graph_data = GLOBAL_STATE.quotient_graph or {}

        return {
            "modules": modules_data,
            "layers": layers_data,
            "quotient_graph": quotient_graph_data,
        }

    @app.get("/api/architecture/conformance")
    def get_architecture_conformance(strict_layering: bool = False):
        """Evaluate architectural rule conformance and compute the Architecture Conformance Index (ACI)."""
        if GLOBAL_STATE.repo is None or not GLOBAL_STATE.architecture_conformance:
            raise HTTPException(status_code=400, detail="No repository scanned yet or architecture engine uninitialized.")
        report = GLOBAL_STATE.architecture_conformance.evaluate(
            parsed_files=GLOBAL_STATE.parsed_files,
            strict_layering=strict_layering,
        )
        return report.to_dict()

    @app.get("/api/architecture/cycles")
    def get_architecture_cycles():
        """Detect package-level dependency cycles using Tarjan's SCC algorithm on quotient graph."""
        if GLOBAL_STATE.repo is None or not GLOBAL_STATE.architecture_conformance:
            raise HTTPException(status_code=400, detail="No repository scanned yet or architecture engine uninitialized.")
        cycles = GLOBAL_STATE.architecture_conformance.detect_package_cycles()
        sccs = GLOBAL_STATE.architecture_conformance.detect_package_sccs()
        return {
            "has_cycles": len(cycles) > 0,
            "cycles": cycles,
            "package_sccs": sccs,
            "cycle_count": len(cycles),
        }

    @app.get("/api/architecture/hotspots")
    def get_architecture_hotspots():
        """Compute repository-level risk scores, maintenance debt archetypes, and hotspot metrics."""
        if GLOBAL_STATE.repo is None:
            raise HTTPException(status_code=400, detail="No repository scanned yet.")
        hotspot_detector = GLOBAL_STATE.hotspot_detector
        if not hotspot_detector:
            from ..architecture.hotspots import MaintenanceHotspotDetector
            hotspot_detector = MaintenanceHotspotDetector()

        valid_ast_count = len([f for f in GLOBAL_STATE.repo.files if f.is_python])
        report = hotspot_detector.detect_hotspots(
            modules=GLOBAL_STATE.architecture_modules or {},
            quotient_graph=GLOBAL_STATE.quotient_graph,
            commits=GLOBAL_STATE.git_commits,
            churn_summary=GLOBAL_STATE.git_churn_summary,
            temporal_couplings=GLOBAL_STATE.git_couplings,
            total_source_files=len(GLOBAL_STATE.repo.files),
            valid_ast_files=valid_ast_count,
        )
        data = report.to_dict()
        data["repository_risk_score"] = report.top_hotspot_mean
        return data

    return app
