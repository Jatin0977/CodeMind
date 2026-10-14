"""
FastAPI application backend for CodeMind Web UI — Ingestion & Static Code Analysis Dashboard.
Prepared for College Evaluation 1 (Technical Phases 1 and 2).
"""

import os
import time
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
from ..rag.engine import RAGEngine
from ..rag.models import RAGResponse
from ..rag.providers.factory import get_llm_provider
from ..graph.models import NodeType, EdgeType, Node, Edge, GraphSummary
from ..graph.builder import KnowledgeGraphBuilder
from ..graph.query import GraphQueryEngine


class ScanRequest(BaseModel):
    repo_path: str = Field(default=".", description="Local repository path, ZIP file, or Git clone URL to scan")


class AskRequest(BaseModel):
    question: str = Field(..., description="Developer question")
    top_k: int = Field(default=4, ge=1, le=10, description="Top evidence chunks to retrieve")
    mock: bool = Field(default=False, description="Use Mock LLM provider for offline demo")
    model: Optional[str] = Field(default=None, description="Optional LLM model name")


class CodebaseState:
    """Session state holding the currently ingested repository and static analysis results."""

    def __init__(self):
        self.repo: Optional[IngestedRepository] = None
        self.parsed_files: Dict[str, ParsedFile] = {}  # rel_path -> ParsedFile
        self.static_metrics: Dict[str, Any] = {}
        self.chunks: List[CodeChunk] = []
        self.chunk_breakdown: Dict[str, int] = {}
        self.retriever = SemanticRetriever()
        self.graph_builder = KnowledgeGraphBuilder()
        self.graph_query_engine: Optional[GraphQueryEngine] = None

    def scan_and_analyze(self, repo_path: str) -> Dict[str, Any]:
        """
        Load repository (local, ZIP, or Git URL), extract AST symbols, and compute static metrics.
        Runs purely on Technical Phase 1 (Ingestion) and Phase 2 (Static Code Analysis).
        """
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
            "files": files_data,
        }

    # Alias for backwards compatibility
    scan_and_index = scan_and_analyze


# Global session instance
GLOBAL_STATE = CodebaseState()


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
            "evaluation_phase": "Evaluation 2: Technical Phases 1–4",
            "has_gemini_key": has_gemini,
            "embedding_model": GLOBAL_STATE.retriever.embedding_provider.model_name,
            "is_scanned": GLOBAL_STATE.repo is not None,
            "is_indexed": GLOBAL_STATE.repo is not None and len(GLOBAL_STATE.chunks) > 0,
            "has_graph": GLOBAL_STATE.graph_query_engine is not None,
            "total_graph_nodes": len(GLOBAL_STATE.graph_builder.nodes_by_id) if GLOBAL_STATE.graph_builder else 0,
            "total_graph_edges": len(GLOBAL_STATE.graph_builder.edges_list) if GLOBAL_STATE.graph_builder else 0,
            "repo_name": GLOBAL_STATE.repo.repo_name if GLOBAL_STATE.repo else None,
            "total_files": GLOBAL_STATE.repo.summary.total_files if GLOBAL_STATE.repo else 0,
            "total_chunks": len(GLOBAL_STATE.chunks),
        }

    @app.post("/api/scan")
    def scan_repository(request: ScanRequest):
        try:
            summary = GLOBAL_STATE.scan_and_analyze(request.repo_path)
            return summary
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except NotADirectoryError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/ask")
    def ask_question(request: AskRequest):
        if GLOBAL_STATE.repo is None:
            raise HTTPException(
                status_code=400,
                detail="No repository scanned yet. Please scan a repository first.",
            )

        provider_type = "mock" if request.mock else None
        llm_provider = get_llm_provider(provider_type=provider_type, model_name=request.model)
        rag_engine = RAGEngine(retriever=GLOBAL_STATE.retriever, llm_provider=llm_provider)

        response: RAGResponse = rag_engine.ask(
            query=request.question,
            top_k=request.top_k,
        )

        return response.to_dict(include_sources=True)

    @app.get("/api/file")
    def get_file_content(path: str):
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

    return app
