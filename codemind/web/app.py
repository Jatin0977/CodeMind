"""
FastAPI application backend for CodeMind Web UI and Visual Code Explorer.
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


class ScanRequest(BaseModel):
    repo_path: str = Field(default=".", description="Local repository path to scan")


class AskRequest(BaseModel):
    question: str = Field(..., description="Developer question")
    top_k: int = Field(default=4, ge=1, le=10, description="Top evidence chunks to retrieve")
    mock: bool = Field(default=False, description="Use Mock LLM provider for offline demo")
    model: Optional[str] = Field(default=None, description="Optional LLM model name")


class CodebaseState:
    """Session state holding the currently ingested repository and retrieval engine."""

    def __init__(self):
        self.repo: Optional[IngestedRepository] = None
        self.parsed_files: Dict[str, ParsedFile] = {}  # rel_path -> ParsedFile
        self.chunks: List[CodeChunk] = []
        self.chunk_breakdown: Dict[str, int] = {}
        self.retriever = SemanticRetriever()
        self.rag_engine = RAGEngine(retriever=self.retriever)

    def scan_and_index(self, repo_path: str) -> Dict[str, Any]:
        """Load repository, extract AST symbols, generate chunks, and build vector index."""
        loader = RepositoryLoader()
        self.repo = loader.load_repository(repo_path)
        self.parsed_files.clear()
        self.chunks.clear()
        self.chunk_breakdown.clear()

        total_classes = 0
        total_functions = 0
        total_methods = 0
        total_imports = 0

        for sf in self.repo.files:
            parsed = GLOBAL_PARSER_FACTORY.parse(sf)
            if parsed:
                self.parsed_files[sf.relative_path] = parsed
                if parsed.is_valid:
                    total_classes += len(parsed.classes)
                    total_functions += len(parsed.functions)
                    total_methods += sum(len(c.methods) for c in parsed.classes)
                    total_imports += len(parsed.imports)

            file_chunks = GLOBAL_CHUNKER_FACTORY.chunk_file(sf, parsed)
            self.chunks.extend(file_chunks)
            for c in file_chunks:
                self.chunk_breakdown[c.chunk_type] = self.chunk_breakdown.get(c.chunk_type, 0) + 1

        # Index in vector store
        indexed_chunks_count = self.retriever.index_chunks(self.chunks)

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
            "ast_metrics": {
                "classes": total_classes,
                "functions": total_functions,
                "methods": total_methods,
                "imports": total_imports,
            },
            "total_chunks": len(self.chunks),
            "chunk_breakdown": self.chunk_breakdown,
            "indexed_chunks": indexed_chunks_count,
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
        title="CodeMind — Visual Code Explorer & Grounded RAG",
        description="Agentic Codebase Intelligence & Software Evolution Platform",
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
            "has_gemini_key": has_gemini,
            "embedding_model": GLOBAL_STATE.retriever.embedding_provider.model_name,
            "is_indexed": GLOBAL_STATE.repo is not None,
            "repo_name": GLOBAL_STATE.repo.repo_name if GLOBAL_STATE.repo else None,
        }

    @app.post("/api/scan")
    def scan_repository(request: ScanRequest):
        try:
            summary = GLOBAL_STATE.scan_and_index(request.repo_path)
            return summary
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
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

    return app
