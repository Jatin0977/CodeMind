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

# ============================================================================
# Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
# (Code Chunking, Embeddings, Vector Stores, Semantic Retrieval, and RAG Engine)
# ============================================================================
# from ..chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
# from ..chunking.models import CodeChunk
# from ..retrieval.retriever import SemanticRetriever
# from ..rag.engine import RAGEngine
# from ..rag.models import RAGResponse
# from ..rag.providers.factory import get_llm_provider
# ============================================================================


class ScanRequest(BaseModel):
    repo_path: str = Field(default=".", description="Local repository path, ZIP file, or Git clone URL to scan")


# Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
# class AskRequest(BaseModel):
#     question: str = Field(..., description="Developer question")
#     top_k: int = Field(default=4, ge=1, le=10, description="Top evidence chunks to retrieve")
#     mock: bool = Field(default=False, description="Use Mock LLM provider for offline demo")
#     model: Optional[str] = Field(default=None, description="Optional LLM model name")


class CodebaseState:
    """Session state holding the currently ingested repository and static analysis results."""

    def __init__(self):
        self.repo: Optional[IngestedRepository] = None
        self.parsed_files: Dict[str, ParsedFile] = {}  # rel_path -> ParsedFile
        self.static_metrics: Dict[str, Any] = {}

        # ============================================================================
        # Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
        # ============================================================================
        # self.chunks: List[CodeChunk] = []
        # self.chunk_breakdown: Dict[str, int] = {}
        # self.retriever = SemanticRetriever()
        # self.rag_engine = RAGEngine(retriever=self.retriever)
        # ============================================================================

    def scan_and_analyze(self, repo_path: str) -> Dict[str, Any]:
        """
        Load repository (local, ZIP, or Git URL), extract AST symbols, and compute static metrics.
        Runs purely on Technical Phase 1 (Ingestion) and Phase 2 (Static Code Analysis).
        """
        loader = RepositoryLoader()
        self.repo = loader.load_repository(repo_path)
        self.parsed_files.clear()

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

        self.static_metrics = {
            "classes": total_classes,
            "functions": total_functions,
            "methods": total_methods,
            "imports": total_imports,
            "docstrings": total_docstrings,
            "syntax_errors": syntax_errors,
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
            "files": files_data,
        }


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
        return {
            "status": "healthy",
            "version": "0.1.0",
            "evaluation_phase": "Evaluation 1: Technical Phases 1 & 2 (Ingestion & Static Analysis)",
            "is_scanned": GLOBAL_STATE.repo is not None,
            "repo_name": GLOBAL_STATE.repo.repo_name if GLOBAL_STATE.repo else None,
            "total_files": GLOBAL_STATE.repo.summary.total_files if GLOBAL_STATE.repo else 0,
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

    # ============================================================================
    # Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
    # ============================================================================
    # @app.post("/api/ask")
    # def ask_question(request: AskRequest):
    #     if GLOBAL_STATE.repo is None:
    #         raise HTTPException(
    #             status_code=400,
    #             detail="No repository scanned yet. Please scan a repository first.",
    #         )
    #
    #     provider_type = "mock" if request.mock else None
    #     llm_provider = get_llm_provider(provider_type=provider_type, model_name=request.model)
    #     rag_engine = RAGEngine(retriever=GLOBAL_STATE.retriever, llm_provider=llm_provider)
    #
    #     response: RAGResponse = rag_engine.ask(
    #         query=request.question,
    #         top_k=request.top_k,
    #     )
    #
    #     return response.to_dict(include_sources=True)
    # ============================================================================

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

    return app
