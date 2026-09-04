"""
Command-line interface for CodeMind codebase inspection, chunking, semantic search, and grounded RAG.
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
from .chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from .chunking.models import CodeChunk
from .retrieval.retriever import SemanticRetriever
from .embeddings.factory import get_embedding_provider
from .rag.engine import RAGEngine
from .rag.models import RAGResponse
from .rag.providers.factory import get_llm_provider


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
    print(f" CodeMind - Codebase Inspection Report")
    print(divider)
    print(f"Repository:          {repo.repo_name}")
    print(f"Path:                {repo.repo_path}")
    print(f"Files found:         {repo.summary.total_files}")
    print(f"Python files:        {python_files_count}")
    print(f"Documentation files: {doc_files_count}")
    print(f"Total lines:         {repo.summary.total_lines:,}")
    print(f"Total size:          {repo.summary.total_size_bytes / 1024:.1f} KB")
    print(sub_divider)
    print(f"AST Symbols Extracted:")
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


def chunk_repository(
    repo_path: str,
    as_json: bool = False,
    max_samples: int = 10,
) -> int:
    """Ingest and chunk all codebase files, printing chunk statistics and samples."""
    loader = RepositoryLoader()

    try:
        repo: IngestedRepository = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository: {e}", file=sys.stderr)
        return 1

    all_chunks: List[CodeChunk] = []
    chunk_type_counts: Dict[str, int] = {}

    for source_file in repo.files:
        parsed = GLOBAL_PARSER_FACTORY.parse(source_file)
        file_chunks = GLOBAL_CHUNKER_FACTORY.chunk_file(source_file, parsed)
        all_chunks.extend(file_chunks)
        for c in file_chunks:
            chunk_type_counts[c.chunk_type] = chunk_type_counts.get(c.chunk_type, 0) + 1

    if as_json:
        output_data = {
            "repository": repo.repo_name,
            "total_chunks": len(all_chunks),
            "chunk_type_breakdown": chunk_type_counts,
            "chunks": [c.to_dict() for c in all_chunks],
        }
        print(json.dumps(output_data, indent=2))
        return 0

    divider = "=" * 60
    sub_divider = "-" * 60

    print(divider)
    print(f" CodeMind - Codebase Chunking Report")
    print(divider)
    print(f"Repository:          {repo.repo_name}")
    print(f"Total Chunks:        {len(all_chunks)}")
    print(sub_divider)
    print(f"Chunk Breakdown by Type:")
    for c_type, count in sorted(chunk_type_counts.items(), key=lambda x: -x[1]):
        display_type = c_type.replace("_", " ").title()
        print(f"  - {display_type:<18} {count:>3} chunks")
    print(sub_divider)

    if all_chunks:
        print(f"Sample Chunks (showing up to {max_samples}):")
        for idx, chunk in enumerate(all_chunks[:max_samples], 1):
            type_label = chunk.chunk_type.upper()
            sym_label = chunk.symbol_name or chunk.file_name
            lines_span = f"{chunk.start_line}-{chunk.end_line}"
            print(f"\n  [{idx}] {type_label}: {sym_label}")
            print(f"      File:   {chunk.relative_path}:{lines_span} ({chunk.line_count} lines)")
            if chunk.signature:
                print(f"      Sig:    {chunk.signature}")
            print(f"      ID:     {chunk.chunk_id}")

        if len(all_chunks) > max_samples:
            remaining = len(all_chunks) - max_samples
            print(f"\n  ... and {remaining} more chunks.")

    print(divider)
    return 0


def search_repository(
    repo_path: str,
    query: str,
    top_k: int = 5,
    as_json: bool = False,
) -> int:
    """Index codebase chunks and execute semantic similarity search for a query."""
    loader = RepositoryLoader()

    try:
        repo: IngestedRepository = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository: {e}", file=sys.stderr)
        return 1

    retriever = SemanticRetriever()
    indexed_count = retriever.index_repository(repo)

    if indexed_count == 0:
        print("No indexable chunks found in repository.", file=sys.stderr)
        return 1

    results = retriever.search(query, top_k=top_k)

    if as_json:
        output_data = {
            "query": query,
            "repository": repo.repo_name,
            "total_indexed_chunks": indexed_count,
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(output_data, indent=2))
        return 0

    divider = "=" * 60
    sub_divider = "-" * 60

    print(divider)
    print(f" CodeMind - Semantic Code Search Results")
    print(f" Query: \"{query}\"")
    print(f" Indexed Chunks: {indexed_count} | Embedding: {retriever.embedding_provider.model_name}")
    print(divider)

    if not results:
        print("No matching code chunks found.")
        print(divider)
        return 0

    for res in results:
        chunk = res.chunk
        type_str = chunk.chunk_type.upper()
        sym_str = chunk.symbol_name or "block"
        print(f"\nResult {res.rank} [Score: {res.score:.3f}] - {chunk.relative_path}:{chunk.start_line}-{chunk.end_line}")
        print(f"  Symbol:    {type_str} {sym_str}")
        if chunk.signature:
            print(f"  Signature: {chunk.signature}")

        # Show snippet with line numbers (up to 8 lines)
        raw_lines = chunk.content.splitlines()
        preview_lines = raw_lines[:8]
        print("  Snippet:")
        for offset, line in enumerate(preview_lines):
            line_no = chunk.start_line + offset
            print(f"    {line_no:>4}: {line}")
        if len(raw_lines) > 8:
            print(f"    ... ({len(raw_lines) - 8} more lines)")

    print("\n" + divider)
    return 0


def ask_repository(
    repo_path: str,
    question: str,
    top_k: int = 4,
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """Answer a developer question using Grounded Codebase RAG with citations."""
    loader = RepositoryLoader()

    try:
        repo: IngestedRepository = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository: {e}", file=sys.stderr)
        return 1

    llm_provider = get_llm_provider(provider_type=provider_type, model_name=model_name)
    rag_engine = RAGEngine(llm_provider=llm_provider)

    response: RAGResponse = rag_engine.ask(query=question, repo=repo, top_k=top_k)

    if as_json:
        print(json.dumps(response.to_dict(), indent=2))
        return 0

    divider = "=" * 65
    sub_divider = "-" * 65

    print(divider)
    print(f" CodeMind - Grounded Codebase Q&A (RAG)")
    print(f" Question: \"{question}\"")
    print(f" Model:    {response.model_name} (Latency: {response.latency_ms:.1f}ms)")
    print(divider)

    print("\nAnswer:")
    print(response.answer)

    print("\n" + sub_divider)
    if response.citations:
        print(f"Cited Source References ({len(response.citations)}):")
        for idx, cit in enumerate(response.citations, start=1):
            # Find matching chunk for symbol label
            sym_label = ""
            for s in response.sources:
                if cit in f"{s.chunk.relative_path}:{s.chunk.start_line}-{s.chunk.end_line}":
                    if s.chunk.symbol_name:
                        sym_label = f" ({s.chunk.chunk_type.upper()}: {s.chunk.symbol_name})"
                    break
            print(f"  [{idx}] [{cit}]{sym_label}")
    else:
        if response.is_sufficient:
            print("Sources: Grounded in retrieved repository chunks.")
        else:
            print("No relevant source code citations found.")

    print(divider)
    return 0


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
        description="CodeMind - Agentic Codebase Intelligence & Software Evolution Platform",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. 'inspect' subcommand
    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect a local codebase repository and extract AST symbols"
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

    # 2. 'chunk' subcommand
    chunk_parser = subparsers.add_parser(
        "chunk", help="Chunk codebase files into AST-aware semantic code and doc chunks"
    )
    chunk_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository (default: current directory)",
    )
    chunk_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output chunks as structured JSON",
    )
    chunk_parser.add_argument(
        "--max-samples",
        type=int,
        default=10,
        help="Maximum sample chunks to display (default: 10)",
    )

    # 3. 'search' subcommand
    search_parser = subparsers.add_parser(
        "search", help="Perform semantic vector search over codebase chunks"
    )
    search_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository (default: current directory)",
    )
    search_parser.add_argument(
        "query",
        type=str,
        help="Natural language search query",
    )
    search_parser.add_argument(
        "--top-k",
        "-k",
        type=int,
        default=5,
        help="Number of top search results to return (default: 5)",
    )
    search_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output search results as JSON",
    )

    # 4. 'ask' subcommand (Grounded RAG)
    ask_parser = subparsers.add_parser(
        "ask", help="Ask a question about the repository using Grounded RAG"
    )
    ask_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository (default: current directory)",
    )
    ask_parser.add_argument(
        "question",
        type=str,
        help="Developer question to answer from codebase",
    )
    ask_parser.add_argument(
        "--top-k",
        "-k",
        type=int,
        default=4,
        help="Number of evidence chunks to retrieve (default: 4)",
    )
    ask_parser.add_argument(
        "--mock",
        action="store_true",
        help="Force use Mock LLM provider (offline mode without API key)",
    )
    ask_parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="LLM model name (default: gemini-2.5-flash)",
    )
    ask_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output grounded response as JSON",
    )

    # 5. 'serve' subcommand (Interactive Web UI)
    serve_parser = subparsers.add_parser(
        "serve", help="Launch the interactive Web UI & Visual Code Explorer"
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

    args = parser.parse_args()

    if args.command == "inspect":
        return inspect_repository(
            repo_path=args.path,
            detail=args.detail,
            as_json=args.json,
            max_samples=args.max_samples,
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
    elif args.command == "serve":
        return serve_web(
            host=args.host,
            port=args.port,
        )
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
