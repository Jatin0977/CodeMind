"""
Command-line interface for CodeMind codebase inspection and static analysis.
Prepared for College Evaluation 1 (Technical Phases 1 and 2).
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure safe console output across Windows terminals with different default charmaps
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .ingestion.repo_loader import RepositoryLoader
from .ingestion.models import IngestedRepository, SourceFile
from .parsing.parser_factory import GLOBAL_PARSER_FACTORY
from .parsing.base_parser import ParsedFile, Symbol

# ============================================================================
# Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
# (Chunking, Semantic Search Embeddings, Vector Store, and Grounded RAG)
# ============================================================================
# from .chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
# from .chunking.models import CodeChunk
# from .retrieval.retriever import SemanticRetriever
# from .embeddings.factory import get_embedding_provider
# from .rag.engine import RAGEngine
# from .rag.models import RAGResponse
# from .rag.providers.factory import get_llm_provider
# ============================================================================


def inspect_repository(
    repo_path: str,
    detail: bool = False,
    as_json: bool = False,
    max_samples: int = 10,
) -> int:
    """Scan and inspect a repository, parsing its code and printing a structured summary."""
    loader = RepositoryLoader()

    try:
        repo: IngestedRepository = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository: {e}", file=sys.stderr)
        return 1

    parsed_files: List[ParsedFile] = []
    total_classes = 0
    total_functions = 0
    total_methods = 0
    total_imports = 0
    total_errors = 0

    for source_file in repo.files:
        parsed: ParsedFile = GLOBAL_PARSER_FACTORY.parse(source_file)
        if parsed:
            parsed_files.append(parsed)
            if parsed.is_valid:
                total_classes += len(parsed.classes)
                total_functions += len(parsed.functions)
                total_methods += sum(len(c.methods) for c in parsed.classes)
                total_imports += len(parsed.imports)
            else:
                total_errors += 1

    python_files_count = len(repo.get_python_files())
    doc_files_count = len(repo.get_doc_files())

    if as_json:
        output_data: Dict[str, Any] = {
            "repository": repo.repo_name,
            "repo_path": repo.repo_path,
            "summary": {
                "total_files": repo.summary.total_files,
                "python_files": python_files_count,
                "documentation_files": doc_files_count,
                "total_lines": repo.summary.total_lines,
                "total_size_bytes": repo.summary.total_size_bytes,
                "classes": total_classes,
                "functions": total_functions,
                "methods": total_methods,
                "imports": total_imports,
                "syntax_errors": total_errors,
                "languages": repo.summary.language_breakdown,
            },
            "parsed_files": [pf.to_dict() for pf in parsed_files],
        }
        print(json.dumps(output_data, indent=2))
        return 0

    divider = "=" * 60
    sub_divider = "-" * 60

    print(divider)
    print(f" CodeMind - Codebase Inspection Report (Evaluation 1)")
    print(divider)
    print(f"Repository:          {repo.repo_name}")
    print(f"Path:                {repo.repo_path}")
    print(f"Files found:         {repo.summary.total_files}")
    print(f"Python files:        {python_files_count}")
    print(f"Documentation files: {doc_files_count}")
    print(f"Total lines:         {repo.summary.total_lines:,}")
    print(f"Total size:          {repo.summary.total_size_bytes / 1024:.1f} KB")
    print(sub_divider)
    print(f"AST Symbols Extracted (Static Code Analysis):")
    print(f"  Classes:           {total_classes}")
    print(f"  Functions (top):   {total_functions}")
    print(f"  Methods:           {total_methods}")
    print(f"  Imports:           {total_imports}")
    if total_errors > 0:
        print(f"  Syntax Errors:     {total_errors} (handled gracefully)")
    print(sub_divider)

    if repo.summary.language_breakdown:
        print("Languages detected:")
        for lang, count in sorted(repo.summary.language_breakdown.items(), key=lambda x: -x[1]):
            print(f"  - {lang.capitalize():<16} {count:>3} files")
        print(sub_divider)

    all_symbols_with_file: List[tuple[str, Symbol]] = []
    for pf in parsed_files:
        if pf.is_valid:
            for sym in pf.symbols:
                all_symbols_with_file.append((pf.relative_path, sym))

    if all_symbols_with_file:
        print(f"Sample Parsed Symbols (showing up to {max_samples}):")
        for idx, (rel_path, sym) in enumerate(all_symbols_with_file[:max_samples], 1):
            sym_kind = sym.symbol_type.upper()
            async_tag = "async " if sym.is_async else ""
            parent_tag = f"{sym.parent_name}." if sym.parent_name else ""
            args_str = f"({', '.join(sym.args)})" if sym.args else "()"
            ret_str = f" -> {sym.returns}" if sym.returns else ""

            print(f"\n  [{idx}] {sym_kind}: {async_tag}{parent_tag}{sym.name}{args_str}{ret_str}")
            print(f"      File:   {rel_path}:{sym.start_line}-{sym.end_line}")

            if sym.bases:
                print(f"      Bases:  {', '.join(sym.bases)}")
            if sym.decorators:
                print(f"      Decorators: {', '.join(sym.decorators)}")
            if sym.calls:
                calls_preview = ", ".join(sym.calls[:5]) + ("..." if len(sym.calls) > 5 else "")
                print(f"      Calls:  {calls_preview}")
            if sym.docstring:
                first_line = sym.docstring.strip().splitlines()[0]
                doc_preview = (first_line[:65] + "...") if len(first_line) > 65 else first_line
                print(f"      Doc:    \"{doc_preview}\"")

        if len(all_symbols_with_file) > max_samples:
            remaining = len(all_symbols_with_file) - max_samples
            print(f"\n  ... and {remaining} more symbols.")

    if detail:
        print("\n" + sub_divider)
        print("Detailed File Inspection:")
        for pf in parsed_files:
            status = "[OK]" if pf.is_valid else f"[ERROR: {pf.error}]"
            print(f"\nFile: {pf.relative_path} {status}")
            if pf.is_valid:
                print(f"  Imports ({len(pf.imports)}): {', '.join(str(i) for i in pf.imports[:6])}")
                print(f"  Classes ({len(pf.classes)}): {', '.join(c.name for c in pf.classes)}")
                print(f"  Functions ({len(pf.functions)}): {', '.join(f.name for f in pf.functions)}")

    print(divider)
    return 0


# ============================================================================
# Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
# (Chunking, Semantic Search, and Grounded RAG Subcommands)
# ============================================================================
def chunk_repository(repo_path: str, as_json: bool = False, max_samples: int = 10) -> int:
    """[Temporarily disabled for College Evaluation 1]"""
    print(
        "[College Evaluation 1 Notice] The 'chunk' feature is temporarily disabled for College Evaluation 1 "
        "(Technical Phases 1 and 2 only). Please use 'inspect' or 'serve'.",
        file=sys.stderr,
    )
    return 0


def search_repository(repo_path: str, query: str, top_k: int = 5, as_json: bool = False) -> int:
    """[Temporarily disabled for College Evaluation 1]"""
    print(
        "[College Evaluation 1 Notice] The 'search' feature (Semantic Vector Search) is temporarily disabled "
        "for College Evaluation 1 (Technical Phases 1 and 2 only). Please use 'inspect' or 'serve'.",
        file=sys.stderr,
    )
    return 0


def ask_repository(
    repo_path: str,
    question: str,
    top_k: int = 4,
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """[Temporarily disabled for College Evaluation 1]"""
    print(
        "[College Evaluation 1 Notice] The 'ask' feature (Grounded RAG / LLM) is temporarily disabled "
        "for College Evaluation 1 (Technical Phases 1 and 2 only). Please use 'inspect' or 'serve'.",
        file=sys.stderr,
    )
    return 0
# ============================================================================


def serve_web(host: str = "127.0.0.1", port: int = 8000) -> int:
    """Launch the CodeMind Visual Code Explorer and Interactive Web UI."""
    try:
        import uvicorn
        from .web.app import create_app
    except ImportError as e:
        print(f"Error: Missing web server dependencies ({e}).", file=sys.stderr)
        print("Please install fastapi and uvicorn: pip install fastapi uvicorn", file=sys.stderr)
        return 1

    divider = "=" * 60
    print(divider)
    print(" CodeMind - Interactive Web UI & Visual Code Explorer")
    print(" College Evaluation 1: Technical Phases 1 & 2")
    print(divider)
    print(f" Server running at: http://{host}:{port}")
    print(" Open the URL above in your web browser to access the dashboard.")
    print(" Press CTRL+C to stop the server.")
    print(divider)

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="python -m codemind.cli",
        description="CodeMind - Repository Ingestion & Static Code Analysis (Evaluation 1)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. 'inspect' subcommand (Active - Phases 1 & 2)
    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect a codebase repository (Local path, ZIP, or Git URL) and extract AST symbols"
    )
    inspect_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the repository to inspect (default: current directory)",
    )
    inspect_parser.add_argument(
        "--detail",
        "-d",
        action="store_true",
        help="Show detailed listing of symbols and imports per file",
    )
    inspect_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output results as structured JSON",
    )
    inspect_parser.add_argument(
        "--max-samples",
        type=int,
        default=10,
        help="Maximum sample symbols to display in summary (default: 10)",
    )

    # 2. 'serve' subcommand (Active - Interactive Web UI)
    serve_parser = subparsers.add_parser(
        "serve", help="Launch the interactive Web UI for Ingestion & Static Code Analysis"
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind the server to (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port number to listen on (default: 8000)",
    )

    # ============================================================================
    # Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
    # ============================================================================
    chunk_parser = subparsers.add_parser(
        "chunk", help="[Disabled in Eval 1] Chunk codebase into semantic units"
    )
    chunk_parser.add_argument("path", nargs="?", default=".")
    chunk_parser.add_argument("--json", "-j", action="store_true")
    chunk_parser.add_argument("--max-samples", type=int, default=10)

    search_parser = subparsers.add_parser(
        "search", help="[Disabled in Eval 1] Semantic vector search"
    )
    search_parser.add_argument("path", nargs="?", default=".")
    search_parser.add_argument("query", type=str, nargs="?", default="")
    search_parser.add_argument("--top-k", "-k", type=int, default=5)
    search_parser.add_argument("--json", "-j", action="store_true")

    ask_parser = subparsers.add_parser(
        "ask", help="[Disabled in Eval 1] Grounded RAG Q&A"
    )
    ask_parser.add_argument("path", nargs="?", default=".")
    ask_parser.add_argument("question", type=str, nargs="?", default="")
    ask_parser.add_argument("--top-k", "-k", type=int, default=4)
    ask_parser.add_argument("--mock", action="store_true")
    ask_parser.add_argument("--model", "-m", type=str, default=None)
    ask_parser.add_argument("--json", "-j", action="store_true")
    # ============================================================================

    args = parser.parse_args()

    if args.command == "inspect":
        return inspect_repository(
            repo_path=args.path,
            detail=args.detail,
            as_json=args.json,
            max_samples=args.max_samples,
        )
    elif args.command == "serve":
        return serve_web(
            host=args.host,
            port=args.port,
        )
    elif args.command == "chunk":
        return chunk_repository(
            repo_path=args.path,
            as_json=args.json,
            max_samples=args.max_samples,
        )
    elif args.command == "search":
        return search_repository(
            repo_path=args.path,
            query=args.query,
            top_k=args.top_k,
            as_json=args.json,
        )
    elif args.command == "ask":
        provider_type = "mock" if args.mock else None
        return ask_repository(
            repo_path=args.path,
            question=args.question,
            top_k=args.top_k,
            provider_type=provider_type,
            model_name=args.model,
            as_json=args.json,
        )
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
