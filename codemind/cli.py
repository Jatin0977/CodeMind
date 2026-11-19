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

from .chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from .chunking.models import CodeChunk
from .retrieval.retriever import SemanticRetriever
from .retrieval.hybrid_retriever import HybridGraphRetriever
from .embeddings.factory import get_embedding_provider
from .rag.engine import RAGEngine
from .rag.models import RAGResponse
from .rag.providers.factory import get_llm_provider
from .graph import KnowledgeGraphBuilder, GraphQueryEngine, NodeType, EdgeType
from .investigation import InvestigationEngine, InvestigationResult, InvestigationStatus


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
            sym_label = chunk.symbol_name or Path(chunk.relative_path).name
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
    use_graph: bool = True,
    as_json: bool = False,
) -> int:
    """Index codebase chunks and execute semantic or hybrid graph-aware search for a query."""
    loader = RepositoryLoader()

    try:
        repo: IngestedRepository = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository: {e}", file=sys.stderr)
        return 1

    embed_provider = get_embedding_provider(provider_type="mock" if "--mock" in sys.argv else None)
    retriever = SemanticRetriever(embedding_provider=embed_provider)
    indexed_count = retriever.index_repository(repo)

    if indexed_count == 0:
        print("No indexable chunks found in repository.", file=sys.stderr)
        return 1

    if use_graph:
        parsed_files = {}
        for sf in repo.files:
            pf = GLOBAL_PARSER_FACTORY.parse(sf)
            if pf:
                parsed_files[sf.relative_path] = pf
        builder = KnowledgeGraphBuilder()
        nx_graph = builder.build(repo, parsed_files)
        query_engine = GraphQueryEngine(nx_graph, builder.nodes_by_id)
        hybrid_retriever = HybridGraphRetriever(
            retriever=retriever,
            graph=nx_graph,
            query_engine=query_engine,
        )
        results = hybrid_retriever.search(query, top_k=top_k, use_graph=True)
        mode_label = "Hybrid Graph-Aware Search"
    else:
        results = retriever.search(query, top_k=top_k)
        mode_label = "Vector-Only Semantic Search"

    if as_json:
        output_data = {
            "query": query,
            "repository": repo.repo_name,
            "mode": "hybrid" if use_graph else "vector_only",
            "total_indexed_chunks": indexed_count,
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(output_data, indent=2))
        return 0

    divider = "=" * 65
    sub_divider = "-" * 65

    print(divider)
    print(f" CodeMind - {mode_label}")
    print(f" Query: \"{query}\"")
    print(divider)
    print(f"Repository:     {repo.repo_name}")
    print(f"Indexed Chunks: {indexed_count}")
    print(f"Retrieval Mode: {'Hybrid (Graph Expansion)' if use_graph else 'Vector-Only'}")
    print(f"Model:          {retriever.embedding_provider.model_name}")
    print(sub_divider)

    if not results:
        print("No relevant matching chunks found.")
    else:
        for res in results:
            chunk = res.chunk
            sym_tag = f" ({chunk.chunk_type.upper()}: {chunk.symbol_name})" if chunk.symbol_name else ""
            prov_tag = ""
            if getattr(res, "provenance", None) == "graph_expanded":
                prov_tag = f" [Graph: {getattr(res, 'relationship_type', 'EXPANDED')}]"
            elif getattr(res, "provenance", None) == "vector_seed":
                prov_tag = " [Vector Seed]"

            print(f"\n[Rank {res.rank}] Score: {res.score:.4f}{prov_tag} - {chunk.relative_path}:{chunk.start_line}-{chunk.end_line}{sym_tag}")
            if chunk.signature:
                print(f"  Signature: {chunk.signature}")
            first_line = chunk.content.strip().splitlines()[0] if chunk.content.strip() else ""
            preview = (first_line[:75] + "...") if len(first_line) > 75 else first_line
            print(f"  Snippet:   {preview}")

    print(divider)
    return 0


def ask_repository(
    repo_path: str,
    question: str,
    top_k: int = 4,
    use_graph: bool = True,
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

    embed_provider = get_embedding_provider(provider_type=provider_type)
    retriever = SemanticRetriever(embedding_provider=embed_provider)
    retriever.index_repository(repo)

    hybrid_retriever = None
    if use_graph:
        parsed_files = {}
        for sf in repo.files:
            pf = GLOBAL_PARSER_FACTORY.parse(sf)
            if pf:
                parsed_files[sf.relative_path] = pf
        builder = KnowledgeGraphBuilder()
        nx_graph = builder.build(repo, parsed_files)
        query_engine = GraphQueryEngine(nx_graph, builder.nodes_by_id)
        hybrid_retriever = HybridGraphRetriever(
            retriever=retriever,
            graph=nx_graph,
            query_engine=query_engine,
        )

    llm_provider = get_llm_provider(provider_type=provider_type, model_name=model_name)
    rag_engine = RAGEngine(
        retriever=retriever,
        hybrid_retriever=hybrid_retriever,
        llm_provider=llm_provider,
    )

    response: RAGResponse = rag_engine.ask(query=question, top_k=top_k, use_graph=use_graph)

    if as_json:
        data = response.to_dict(include_sources=True)
        data["retrieval_mode"] = "hybrid" if (use_graph and hybrid_retriever) else "vector_only"
        print(json.dumps(data, indent=2))
        return 0

    divider = "=" * 65
    sub_divider = "-" * 65

    print(divider)
    mode_text = "Hybrid Graph-Aware RAG" if (use_graph and hybrid_retriever) else "Vector-Only RAG"
    print(f" CodeMind - Grounded Codebase Q&A ({mode_text})")
    print(f" Question: \"{question}\"")
    print(f" Model:    {response.model_name} (Latency: {response.latency_ms:.1f}ms)")
    print(f" Mode:     {mode_text}")
    print(divider)

    print("\nAnswer:")
    print(response.answer)

    print("\n" + sub_divider)
    if response.citations:
        print(f"Cited Source References ({len(response.citations)}):")
        for idx, cit in enumerate(response.citations, start=1):
            # Find matching chunk for symbol label & provenance
            sym_label = ""
            for s in response.sources:
                if cit in f"{s.chunk.relative_path}:{s.chunk.start_line}-{s.chunk.end_line}":
                    if s.chunk.symbol_name:
                        prov_tag = f" [{s.relationship_type}]" if getattr(s, "provenance", None) == "graph_expanded" and getattr(s, "relationship_type", None) else ""
                        sym_label = f" ({s.chunk.chunk_type.upper()}: {s.chunk.symbol_name}){prov_tag}"
                    break
            print(f"  [{idx}] [{cit}]{sym_label}")
    else:
        if response.is_sufficient:
            print("Sources: Grounded in retrieved repository chunks.")
        else:
            print("No relevant source code citations found.")

    print(divider)
    return 0


def graph_repository(
    repo_path: str,
    impact_node: Optional[str] = None,
    cycles_only: bool = False,
    max_depth: int = 3,
    as_json: bool = False,
) -> int:
    """Build and query the Software Knowledge Graph from the CLI."""
    loader = RepositoryLoader()
    try:
        repo: IngestedRepository = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository: {e}", file=sys.stderr)
        return 1

    parsed_files = {}
    for sf in repo.files:
        parsed = GLOBAL_PARSER_FACTORY.parse(sf)
        if parsed:
            parsed_files[sf.relative_path] = parsed

    builder = KnowledgeGraphBuilder()
    nx_graph = builder.build(repo, parsed_files)
    engine = GraphQueryEngine(nx_graph, builder.nodes_by_id)
    summary = builder.get_summary()

    if impact_node:
        impact = engine.trace_impact(impact_node, max_depth=max_depth)
        if as_json:
            print(json.dumps(impact, indent=2))
            return 0

        divider = "=" * 60
        print(divider)
        print(" CodeMind - Structural Reachability Impact Analysis (Phase 4)")
        print(divider)
        print(f"Target Node:         {impact_node}")
        print(f"Analysis Type:       {impact.get('analysis_type', 'Structural Reachability')}")
        print(f"Disclaimer:          {impact.get('disclaimer')}")
        print(f"Total Impacted:      {impact.get('total_impacted', 0)}")
        print(f"Impact Breakdown:    {impact.get('impact_by_type', {})}")
        print("-" * 60)
        for idx, item in enumerate(impact.get("impacted_entities", []), 1):
            n = item["node"]
            print(f"  [{idx}] (Depth {item['depth']}) [{n.get('node_type', '').upper()}] {n.get('name')} ({n.get('relative_path')})")
            print(f"       Rel: {item.get('relationship')} | Path: {' -> '.join(item.get('path', []))}")
        print(divider)
        return 0

    if cycles_only:
        cycles = engine.detect_cycles()
        if as_json:
            print(json.dumps({"has_cycles": len(cycles) > 0, "cycle_count": len(cycles), "cycles": cycles}, indent=2))
            return 0

        divider = "=" * 60
        print(divider)
        print(" CodeMind - Circular Dependency Detection (Phase 4)")
        print(divider)
        print(f"Cycles Detected:     {len(cycles)}")
        for idx, cycle in enumerate(cycles, 1):
            print(f"  Cycle {idx}: {' -> '.join(cycle)} -> {cycle[0]}")
        print(divider)
        return 0

    if as_json:
        print(json.dumps(builder.to_dict(), indent=2))
        return 0

    divider = "=" * 60
    print(divider)
    print(" CodeMind - Software Knowledge Graph Summary (Phase 4)")
    print(divider)
    print(f"Repository:          {repo.repo_name}")
    print(f"Total Graph Nodes:   {summary.total_nodes}")
    print(f"Total Graph Edges:   {summary.total_edges}")
    print(f"Node Type Breakdown: {summary.node_type_counts}")
    print(f"Edge Type Breakdown: {summary.edge_type_counts}")
    print(f"Circular Cycles:     {summary.cycle_count}")
    print(divider)
    return 0


def investigate_repository(
    repo_path: str,
    query: str,
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    as_json: bool = False,
    mock: bool = False,
) -> int:
    """Execute an agentic investigation for a query across the codebase (Phase 6)."""
    if mock:
        provider_type = "mock"
    if not query or not query.strip():
        print("Error: Investigation query cannot be empty.", file=sys.stderr)
        return 1

    loader = RepositoryLoader()
    try:
        repo: IngestedRepository = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository: {e}", file=sys.stderr)
        return 1

    embed_provider = get_embedding_provider(provider_type=provider_type)
    retriever = SemanticRetriever(embedding_provider=embed_provider)
    retriever.index_repository(repo)

    parsed_files = {}
    for sf in repo.files:
        pf = GLOBAL_PARSER_FACTORY.parse(sf)
        if pf:
            parsed_files[sf.relative_path] = pf

    builder = KnowledgeGraphBuilder()
    nx_graph = builder.build(repo, parsed_files)
    query_engine = GraphQueryEngine(nx_graph, builder.nodes_by_id)

    chunks = []
    for sf in repo.files:
        pf = parsed_files.get(sf.relative_path)
        chunks.extend(GLOBAL_CHUNKER_FACTORY.chunk_file(sf, pf))

    hybrid_retriever = HybridGraphRetriever(
        retriever=retriever,
        graph=nx_graph,
        query_engine=query_engine,
    )
    hybrid_retriever.index(chunks, nx_graph)

    llm_provider = get_llm_provider(provider_type=provider_type, model_name=model_name)

    # Detect and mine Git temporal intelligence (Phase 7)
    git_client = None
    git_miner = None
    git_churn_analyzer = None
    git_coupling_analyzer = None
    try:
        from .git.client import GitClient
        from .git.miner import GitMiner
        from .git.churn import CodeChurnAnalyzer
        from .git.coupling import LogicalCouplingAnalyzer

        client = GitClient(repo.repo_path)
        status = client.get_status()
        if status.is_git_repo and not status.is_empty:
            git_client = client
            git_miner = GitMiner(client)
            git_commits = git_miner.mine_commits(max_commits=1000)
            git_churn_analyzer = CodeChurnAnalyzer()
            git_churn_analyzer.analyze(git_commits)
            git_coupling_analyzer = LogicalCouplingAnalyzer(min_support=3, min_confidence=0.5)
            coupling_res = git_coupling_analyzer.analyze(git_commits)
            builder.materialize_temporal_graph(git_commits, coupling_res.couplings, max_materialize_commits=100)
    except Exception:
        pass

    engine = InvestigationEngine(
        repo=repo,
        query_engine=query_engine,
        retriever=retriever,
        hybrid_retriever=hybrid_retriever,
        git_miner=git_miner,
        git_client=git_client,
        git_churn_analyzer=git_churn_analyzer,
        git_coupling_analyzer=git_coupling_analyzer,
        llm_provider=llm_provider,
    )

    result: InvestigationResult = engine.investigate(query)

    if as_json:
        data = result.to_dict()
        status_val = (
            result.overall_status.value
            if hasattr(result.overall_status, "value")
            else str(result.overall_status)
        )
        data["status"] = status_val
        data["overall_status"] = status_val
        data["intent"] = (
            result.intent.value
            if hasattr(result.intent, "value")
            else str(result.intent) if result.intent else None
        )
        raw_citations = result.metadata.get("citations", [])
        data["citations"] = [
            c.get("tag", "") if isinstance(c, dict) else str(c)
            for c in raw_citations
        ]
        print(json.dumps(data, indent=2))
        return 0 if result.overall_status in (InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS, InvestigationStatus.DEFERRED) else 1

    divider = "=" * 65
    sub_divider = "-" * 65

    intent_str = (
        result.intent.value.upper()
        if hasattr(result.intent, "value")
        else str(result.intent).upper() if result.intent else "UNKNOWN"
    )
    status_str = (
        result.overall_status.value
        if hasattr(result.overall_status, "value")
        else str(result.overall_status)
    )
    classification = result.metadata.get("engine", {}).get("classification", {})
    confidence_cat = classification.get("confidence_category", "N/A")
    duration_ms = result.metadata.get("engine", {}).get("total_duration_ms", 0.0)

    print(divider)
    print(" CodeMind - Agentic Investigation Engine (Phase 6)")
    print(f" Query:    \"{query}\"")
    print(f" Intent:   {intent_str} (Confidence: {confidence_cat})")
    print(f" Status:   {status_str} (Duration: {duration_ms:.1f}ms)")
    print(divider)

    print("\nAnswer:")
    print(result.final_answer or "No answer synthesized.")

    # Execution plan & step traces
    if result.step_results:
        print("\n" + sub_divider)
        print(f"Execution Plan & Steps ({len(result.step_results)}):")
        for idx, sr in enumerate(result.step_results, start=1):
            timing = sr.execution_timing.get("latency_ms", 0.0) if sr.execution_timing else 0.0
            st = sr.status.value if hasattr(sr.status, "value") else str(sr.status)
            warn_str = f" - Warning: {sr.warning}" if sr.warning else ""
            err_str = f" - Error: {sr.error_message}" if sr.error_message else ""
            print(f"  [{idx}] {sr.tool_name:<24} [{st:<10}] {timing:>5.1f}ms{warn_str}{err_str}")

    # Citations
    citations = result.metadata.get("citations", [])
    if citations:
        print("\n" + sub_divider)
        print(f"Cited Evidence ({len(citations)}):")
        for idx, cit in enumerate(citations, start=1):
            tag = cit.get("tag", "")
            cat = cit.get("category", "")
            src_tool = cit.get("source_tool", "")
            print(f"  [{idx}] {tag:<40} [{cat} / {src_tool}]")

    # Deferred capabilities
    deferred = result.metadata.get("deferred_capabilities", [])
    if deferred:
        print("\n" + sub_divider)
        print(f"Deferred Capabilities Disclosed ({len(deferred)}):")
        for d in deferred:
            tool = d.get("tool_name", "unknown")
            phase = d.get("target_phase", "future phase")
            print(f"  - {tool}: Scheduled for {phase} (not executed)")

    print(divider)
    return 0 if result.overall_status in (InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS, InvestigationStatus.DEFERRED) else 1


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


def git_history_cli(
    repo_path: str = ".",
    path: Optional[str] = None,
    limit: int = 50,
    since: Optional[str] = None,
    author: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """CLI handler for mining commit history."""
    from .git.client import GitClient
    from .git.miner import GitMiner

    client = GitClient(repo_path)
    status = client.get_status()
    if not status.is_git_repo:
        print(f"Error: '{repo_path}' is not a Git repository.", file=sys.stderr)
        return 1

    miner = GitMiner(client)
    try:
        commits = miner.mine_commits(max_commits=limit, path=path, since=since, author=author)
    except Exception as e:
        print(f"Error mining commit history: {e}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps([c.to_dict() for c in commits], indent=2))
        return 0

    divider = "=" * 65
    print(divider)
    print(f" CodeMind - Git Commit History ({len(commits)} commits)")
    if path:
        print(f" Filter path: {path}")
    print(divider)
    for c in commits:
        date_str = c.author_date.strftime("%Y-%m-%d %H:%M") if hasattr(c.author_date, "strftime") else str(c.author_date)
        print(f"[{c.short_hash}] {date_str} | {c.author_name}: {c.subject}")
        for fc in c.files_changed[:5]:
            print(f"    {fc.status} {fc.path} (+{fc.additions}/-{fc.deletions})")
        if len(c.files_changed) > 5:
            print(f"    ... and {len(c.files_changed) - 5} more files")
    print(divider)
    return 0


def git_churn_cli(
    repo_path: str = ".",
    limit: int = 20,
    sort_by: str = "commits",
    path: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """CLI handler for computing code churn hotspots."""
    from .git.client import GitClient
    from .git.miner import GitMiner
    from .git.churn import CodeChurnAnalyzer

    client = GitClient(repo_path)
    status = client.get_status()
    if not status.is_git_repo:
        print(f"Error: '{repo_path}' is not a Git repository.", file=sys.stderr)
        return 1

    miner = GitMiner(client)
    try:
        commits = miner.mine_commits(max_commits=1000)
        analyzer = CodeChurnAnalyzer()
        res = analyzer.analyze(commits)
    except Exception as e:
        print(f"Error analyzing code churn: {e}", file=sys.stderr)
        return 1

    hotspots = analyzer.get_top_churn_files(limit=limit if not path else 1000, sort_by=sort_by)
    if path:
        norm_p = path.replace("\\", "/").lower()
        hotspots = [h for h in hotspots if norm_p in h.path.lower()][:limit]

    if as_json:
        out = {
            "summary": res.to_dict(),
            "hotspots": [h.to_dict() for h in hotspots],
        }
        print(json.dumps(out, indent=2))
        return 0

    divider = "=" * 65
    print(divider)
    print(f" CodeMind - Code Churn Hotspots (Ranked by: {sort_by})")
    print(f" Total commits analyzed: {res.total_commits_analyzed} | Files tracked: {res.total_files_analyzed}")
    print(f" Total lines added: +{res.total_additions} | Total deleted: -{res.total_deletions}")
    print(divider)
    print(f"{'Path':<40} {'Commits':>8} {'+Lines':>8} {'-Lines':>8} {'Authors':>8}")
    print("-" * 65)
    for h in hotspots:
        p_disp = h.path if len(h.path) <= 39 else "..." + h.path[-36:]
        print(f"{p_disp:<40} {h.commits_count:>8} {h.additions:>8} {h.deletions:>8} {h.unique_authors:>8}")
    print(divider)
    return 0


def git_coupling_cli(
    repo_path: str = ".",
    file_path: Optional[str] = None,
    min_support: int = 3,
    min_confidence: float = 0.5,
    limit: int = 20,
    as_json: bool = False,
) -> int:
    """CLI handler for discovering logical couplings."""
    from .git.client import GitClient
    from .git.miner import GitMiner
    from .git.coupling import LogicalCouplingAnalyzer

    client = GitClient(repo_path)
    status = client.get_status()
    if not status.is_git_repo:
        print(f"Error: '{repo_path}' is not a Git repository.", file=sys.stderr)
        return 1

    miner = GitMiner(client)
    try:
        commits = miner.mine_commits(max_commits=1000)
        analyzer = LogicalCouplingAnalyzer(min_support=min_support, min_confidence=min_confidence)
        analyzer.analyze(commits)
    except Exception as e:
        print(f"Error analyzing logical coupling: {e}", file=sys.stderr)
        return 1

    if file_path:
        couplings = analyzer.get_couplings_for_file(file_path, min_support=min_support, min_confidence=min_confidence)[:limit]
    else:
        top = analyzer.get_top_couplings(limit=limit)
        couplings = [c.to_dict() for c in top]

    if as_json:
        print(json.dumps(couplings, indent=2))
        return 0

    divider = "=" * 65
    print(divider)
    print(f" CodeMind - Logical Coupling Discovery (min_support={min_support}, min_confidence={min_confidence})")
    if file_path:
        print(f" Focal file: {file_path}")
    print(divider)
    if file_path:
        print(f"{'Target File':<40} {'Support':>8} {'Jaccard':>8} {'Confidence':>10}")
        print("-" * 65)
        for c in couplings:
            tf = c['target_file']
            if len(tf) > 39: tf = "..." + tf[-36:]
            print(f"{tf:<40} {c['support_count']:>8} {c['jaccard_similarity']:>8.2f} {c['confidence_to_target']:>10.2f}")
    else:
        print(f"{'File A':<26} {'File B':<26} {'Supp':>5} {'Jacc':>5}")
        print("-" * 65)
        for c in couplings:
            fa = c.get('canonical_file_a', '')
            fb = c.get('canonical_file_b', '')
            if len(fa) > 25: fa = '...' + fa[-22:]
            if len(fb) > 25: fb = '...' + fb[-22:]
            print(f"{fa:<26} {fb:<26} {c.get('support_count', 0):>5} {c.get('jaccard_similarity', 0):>5.2f}")
    print(divider)
    return 0


def impact_cli(
    target: str,
    repo_path: str = ".",
    max_depth: int = 3,
    include_temporal: bool = True,
    show_tests: bool = True,
    as_json: bool = False,
) -> int:
    """CLI handler for Phase 8 Change Impact & Test Intelligence."""
    from .ingestion.repo_loader import RepositoryLoader
    from .parsing.parser_factory import GLOBAL_PARSER_FACTORY
    from .graph.builder import KnowledgeGraphBuilder
    from .git.client import GitClient
    from .git.miner import GitMiner
    from .git.churn import CodeChurnAnalyzer
    from .git.coupling import LogicalCouplingAnalyzer
    from .impact.resolver import ChangeTargetResolver
    from .impact.engine import ChangeImpactEngine
    from .impact.scorer import MultiSignalImpactScorer
    from .impact.test_intelligence import TestIntelligenceEngine
    from .impact.models import AmbiguousTargetError, TargetNotFoundError

    loader = RepositoryLoader()
    try:
        repo = loader.load_repository(repo_path)
    except Exception as e:
        print(f"Error loading repository '{repo_path}': {e}", file=sys.stderr)
        return 1

    builder = KnowledgeGraphBuilder()
    parsed_files = {}
    for sf in repo.files:
        if sf.is_python:
            try:
                parsed = GLOBAL_PARSER_FACTORY.parse(sf)
                if parsed:
                    parsed_files[sf.relative_path] = parsed
            except Exception:
                pass
    builder.build(repo, parsed_files)

    git_client = GitClient(repo_path)
    churn_analyzer = None
    coupling_analyzer = None
    commits = []
    has_git = False

    try:
        if git_client.is_git_repository:
            has_git = True
            miner = GitMiner(git_client)
            commits = miner.mine_commits(max_commits=500)
            if commits:
                churn_analyzer = CodeChurnAnalyzer()
                churn_analyzer.analyze(commits)
                coupling_analyzer = LogicalCouplingAnalyzer(min_support=3, min_confidence=0.5)
                c_res = coupling_analyzer.analyze(commits)
                builder.materialize_temporal_graph(commits, c_res.couplings, max_materialize_commits=100)
    except Exception:
        has_git = False

    resolver = ChangeTargetResolver(builder.graph)
    try:
        resolved_target = resolver.resolve(target)
    except AmbiguousTargetError as err:
        print(f"Error: Symbol '{target}' is ambiguous ({len(err.candidates)} candidates found):", file=sys.stderr)
        for c in err.candidates:
            print(f"  - {c['node_id']} (in {c['file_path']}:{c.get('start_line') or 1})", file=sys.stderr)
        print("Please specify qualified path: '<file>::<symbol>'", file=sys.stderr)
        return 1
    except TargetNotFoundError as err:
        print(f"Error: Target '{target}' could not be resolved.", file=sys.stderr)
        if err.suggestions:
            print(f"Did you mean: {', '.join(err.suggestions)}?", file=sys.stderr)
        return 1

    has_tests = any("test" in (f.relative_path or "").lower() for f in repo.files)
    impact_engine = ChangeImpactEngine(builder.graph, coupling_analyzer=coupling_analyzer)
    test_engine = TestIntelligenceEngine(builder.graph, coupling_analyzer=coupling_analyzer, repo=repo)
    scorer = MultiSignalImpactScorer(
        churn_analyzer=churn_analyzer,
        coupling_analyzer=coupling_analyzer,
        has_git=has_git,
        total_repo_commits=len(commits),
        has_tests=has_tests,
    )

    blast_radius = impact_engine.analyze_blast_radius(resolved_target, max_depth=max_depth, include_temporal=include_temporal)
    centrality = impact_engine.compute_centrality(resolved_target.node_id)
    test_report = test_engine.analyze_tests(resolved_target, blast_radius)
    impact_report = scorer.compute_impact(resolved_target, blast_radius, centrality, test_report)

    if as_json:
        print(json.dumps(impact_report.to_dict(), indent=2))
        return 0

    divider = "=" * 75
    print(divider)
    print(" CodeMind - Change Impact & Test Intelligence (Phase 8)")
    print(divider)
    print(f" Target: {resolved_target.name} (Type: {resolved_target.entity_type}, File: {resolved_target.relative_path or resolved_target.file_path})")
    print(f" Composite Impact Score: {impact_report.composite_score:.2f} | Risk Level: {impact_report.risk_level}")
    print(f" Confidence: {impact_report.confidence:.2f} ({impact_report.confidence_level}) | Blast Radius: {blast_radius.total_impacted} dependents")
    print(divider)

    print("\n--- Multi-Signal Score Breakdown ---")
    print(f"{'Signal Name':<28} {'Raw Val':>8} {'Score':>8} {'Weight':>8} {'Available':>10}")
    print("-" * 75)
    for sig in impact_report.signals.values():
        avail_str = "Yes" if sig.available else "No"
        print(f"{sig.name:<28} {sig.raw_value:>8.1f} {sig.normalized_score:>8.2f} {sig.effective_weight:>8.2f} {avail_str:>10}")

    print("\n--- Blast Radius Distribution ---")
    depth_str = ", ".join(f"Depth {d}: {cnt}" for d, cnt in sorted(blast_radius.counts_by_depth.items()))
    type_str = ", ".join(f"{t}: {cnt}" for t, cnt in sorted(blast_radius.counts_by_type.items()))
    print(f" Total Reachable Dependents: {blast_radius.total_impacted} (max_depth={max_depth})")
    if depth_str:
        print(f" By Depth: {depth_str}")
    if type_str:
        print(f" By Entity Type: {type_str}")

    if show_tests and test_report.total_tests > 0:
        print(f"\n--- Prioritized Regression Test Recommendations ({test_report.total_tests} candidate(s)) ---")
        print(f"{'Rank':<5} {'Tier':<5} {'Evidence Type':<22} {'Score':>6}  {'Test Target':<22} {'Test File'}")
        print("-" * 75)
        for idx, rec in enumerate(test_report.recommendations[:15], start=1):
            tf = rec.test_file
            if len(tf) > 28: tf = "..." + tf[-25:]
            tt = rec.test_target
            if len(tt) > 21: tt = tt[:18] + "..."
            print(f"{idx:<5} {rec.tier:<5} {rec.evidence_type:<22} {rec.rank_score:>6.2f}  {tt:<22} {tf}")

    print(f"\nNotice: {impact_report.blast_radius.disclaimer}")
    print(divider)
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

    # 3. 'chunk' subcommand
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

    # 4. 'search' subcommand
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
        "--hybrid",
        action="store_true",
        default=True,
        help="Use hybrid graph-aware retrieval (default: True)",
    )
    search_parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Disable graph expansion and force vector-only retrieval",
    )
    search_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output search results as JSON",
    )

    # 5. 'ask' subcommand (Grounded RAG)
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
        "--hybrid",
        action="store_true",
        default=True,
        help="Use hybrid graph-aware retrieval (default: True)",
    )
    ask_parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Disable graph expansion and force vector-only retrieval",
    )
    ask_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output grounded response as JSON",
    )

    # 6. 'graph' subcommand (Software Knowledge Graph)
    graph_parser = subparsers.add_parser(
        "graph", help="Construct and query the Software Knowledge Graph (Phase 4)"
    )
    graph_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository (default: current directory)",
    )
    graph_parser.add_argument(
        "--impact",
        type=str,
        default=None,
        help="Target node ID for structural reachability impact analysis",
    )
    graph_parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum depth for impact tracing (default: 3)",
    )
    graph_parser.add_argument(
        "--cycles",
        action="store_true",
        help="Detect and print circular dependency cycles",
    )
    graph_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output graph data or query as JSON",
    )

    # 7. 'investigate' subcommand (Agentic Investigation Engine - Phase 6)
    investigate_parser = subparsers.add_parser(
        "investigate", help="Investigate a question across the codebase using the Agentic Engine (Phase 6)"
    )
    investigate_parser.add_argument(
        "target",
        type=str,
        help="Developer investigation query, or repository path if query is passed as second argument",
    )
    investigate_parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional developer investigation query (when first argument is path)",
    )
    investigate_parser.add_argument(
        "--mock",
        action="store_true",
        help="Force use Mock LLM provider (offline mode without API key)",
    )
    investigate_parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="LLM model name (default: gemini-2.5-flash)",
    )
    investigate_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output investigation result as JSON",
    )

    # 8. 'git-history' subcommand (Git Temporal Intelligence - Phase 7)
    git_history_parser = subparsers.add_parser(
        "git-history", help="Mine Git commit log to analyze chronological evolution (Phase 7)"
    )
    git_history_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository (default: current directory)",
    )
    git_history_parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Filter commit history by file path",
    )
    git_history_parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=50,
        help="Maximum commits to retrieve (default: 50)",
    )
    git_history_parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Filter commits since date (ISO format or git date)",
    )
    git_history_parser.add_argument(
        "--author",
        type=str,
        default=None,
        help="Filter commits by author name or email",
    )
    git_history_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output commits as JSON",
    )

    # 9. 'git-churn' subcommand (Code Churn Analytics - Phase 7)
    git_churn_parser = subparsers.add_parser(
        "git-churn", help="Calculate historical file code churn hotspots (Phase 7)"
    )
    git_churn_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository (default: current directory)",
    )
    git_churn_parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Filter churn to a specific file or directory prefix",
    )
    git_churn_parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=20,
        help="Maximum hotspot files to display (default: 20)",
    )
    git_churn_parser.add_argument(
        "--sort-by",
        "-s",
        type=str,
        choices=["commits", "additions", "deletions", "total_churn", "authors"],
        default="commits",
        help="Metric to rank churn hotspots (default: commits)",
    )
    git_churn_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output churn metrics as JSON",
    )

    # 10. 'git-coupling' subcommand (Logical Coupling Discovery - Phase 7)
    git_coupling_parser = subparsers.add_parser(
        "git-coupling", help="Discover hidden architectural dependencies via commit co-changes (Phase 7)"
    )
    git_coupling_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to repository (default: current directory)",
    )
    git_coupling_parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Focal file to inspect co-change couplings for",
    )
    git_coupling_parser.add_argument(
        "--min-support",
        type=int,
        default=3,
        help="Minimum co-change commits required (default: 3)",
    )
    git_coupling_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Minimum directional confidence threshold (default: 0.5)",
    )
    git_coupling_parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=20,
        help="Maximum couplings to display (default: 20)",
    )
    git_coupling_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output couplings as JSON",
    )

    # 11. 'impact' subcommand (Change Impact & Test Intelligence - Phase 8)
    impact_parser = subparsers.add_parser(
        "impact", help="Analyze reverse dependency blast radius and test intelligence (Phase 8)"
    )
    impact_parser.add_argument(
        "target",
        type=str,
        help="Target entity: canonical node ID, file path, or symbol name (e.g. 'verify_token' or 'auth.py')",
    )
    impact_parser.add_argument(
        "--path",
        "-p",
        default=".",
        help="Path to repository (default: current directory)",
    )
    impact_parser.add_argument(
        "--max-depth",
        "-d",
        type=int,
        default=3,
        help="Maximum reverse dependency traversal depth (default: 3)",
    )
    impact_parser.add_argument(
        "--no-temporal",
        action="store_true",
        help="Disable strictly 1-hop logical co-change temporal expansion",
    )
    impact_parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Disable test recommendation discovery",
    )
    impact_parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output full impact report as JSON",
    )

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
        use_graph = not args.no_graph
        return search_repository(
            repo_path=args.path,
            query=args.query,
            top_k=args.top_k,
            use_graph=use_graph,
            as_json=args.json,
        )
    elif args.command == "ask":
        provider_type = "mock" if args.mock else None
        use_graph = not args.no_graph
        return ask_repository(
            repo_path=args.path,
            question=args.question,
            top_k=args.top_k,
            use_graph=use_graph,
            provider_type=provider_type,
            model_name=args.model,
            as_json=args.json,
        )
    elif args.command == "graph":
        return graph_repository(
            repo_path=args.path,
            impact_node=args.impact,
            cycles_only=args.cycles,
            max_depth=args.max_depth,
            as_json=args.json,
        )
    elif args.command == "investigate":
        if args.query is not None:
            repo_path = args.target
            query_str = args.query
        else:
            repo_path = "."
            query_str = args.target

        provider_type = "mock" if args.mock else None
        return investigate_repository(
            repo_path=repo_path,
            query=query_str,
            provider_type=provider_type,
            model_name=args.model,
            as_json=args.json,
        )
    elif args.command == "git-history":
        return git_history_cli(
            repo_path=args.path,
            path=args.file,
            limit=args.limit,
            since=args.since,
            author=args.author,
            as_json=args.json,
        )
    elif args.command == "git-churn":
        return git_churn_cli(
            repo_path=args.path,
            limit=args.limit,
            sort_by=args.sort_by,
            path=args.file,
            as_json=args.json,
        )
    elif args.command == "git-coupling":
        return git_coupling_cli(
            repo_path=args.path,
            file_path=args.file,
            min_support=args.min_support,
            min_confidence=args.min_confidence,
            limit=args.limit,
            as_json=args.json,
        )
    elif args.command == "impact":
        return impact_cli(
            target=args.target,
            repo_path=args.path,
            max_depth=args.max_depth,
            include_temporal=not args.no_temporal,
            show_tests=not args.no_tests,
            as_json=args.json,
        )
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
