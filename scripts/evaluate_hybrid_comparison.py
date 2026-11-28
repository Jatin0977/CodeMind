"""
Evaluation benchmark comparing Vector-Only vs. Hybrid Graph-Aware Retrieval
on CodeMind codebase across 4 representative benchmark queries.

Separated into two rigorous evaluations:
Part A: End-to-End Retrieval Evaluation (User Query -> Vector Seed -> Graph Expansion -> RAG)
Part B: Controlled Graph Traversal Evaluation (Verified Ground-Truth Seed -> Graph Expansion)
"""

import os
import sys
import time
import json
from pathlib import Path

# Ensure root dir is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import tests.conftest

from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.parsing.parser_factory import GLOBAL_PARSER_FACTORY
from codemind.chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.graph.query import GraphQueryEngine
from codemind.graph.models import EdgeType
from codemind.retrieval.retriever import SemanticRetriever
from codemind.retrieval.hybrid_retriever import HybridGraphRetriever, classify_query_intent
from codemind.rag.engine import RAGEngine
from codemind.rag.providers.factory import get_llm_provider


CORRECTED_BENCHMARK_QUERIES = [
    {
        "id": "Q1_FLOW",
        "query": "How does RepositoryLoader filter ignored directories and binary files?",
        "expected_intent": "flow",
        "target_symbols": ["RepositoryLoader", "FileFilter", "should_ignore_dir", "is_binary_by_extension", "should_ignore_file"],
        "controlled_seed_node": "method:ingestion/repo_loader.py:RepositoryLoader._scan_directory",
        "controlled_expected_rels": [("CALLS", "FileFilter.should_ignore_dir"), ("CALLS", "FileFilter.should_ignore_file"), ("CALLS", "FileFilter.is_binary_by_extension")],
        "description": "Forward/Flow: RepositoryLoader._scan_directory delegates to FileFilter methods.",
    },
    {
        "id": "Q2_FLOW",
        "query": "Explain how the AST chunker builds signatures for classes and functions.",
        "expected_intent": "flow",
        "target_symbols": ["ASTCodeChunker", "_build_class_signature", "_build_func_signature"],
        "controlled_seed_node": "class:chunking/ast_chunker.py:ASTCodeChunker",
        "controlled_expected_rels": [("CONTAINS", "_build_class_signature"), ("CONTAINS", "_build_func_signature")],
        "description": "Forward/Flow: ASTCodeChunker defines signature builder helper methods.",
    },
    {
        "id": "Q3_INHERIT",
        "query": "What base class does ASTCodeChunker inherit and what contract does it implement?",
        "expected_intent": "flow",
        "target_symbols": ["ASTCodeChunker", "BaseChunker"],
        "controlled_seed_node": "class:chunking/ast_chunker.py:ASTCodeChunker",
        "controlled_expected_rels": [("INHERITS", "class:chunking/base_chunker.py:BaseChunker")],
        "description": "Inheritance: ASTCodeChunker inherits from BaseChunker.",
    },
    {
        "id": "Q4_IMPACT",
        "query": "What components invoke or depend on file_filter.py?",
        "expected_intent": "impact",
        "target_symbols": ["file_filter.py", "FileFilter", "RepositoryLoader", "repo_loader.py"],
        "controlled_seed_node": "class:ingestion/file_filter.py:FileFilter",
        "controlled_expected_rels": [("CALLS", "RepositoryLoader.__init__"), ("IMPORTS", "repo_loader.py")],
        "description": "Impact/Dependency: RepositoryLoader.__init__ calls FileFilter; repo_loader imports file_filter.",
    },
]


def run_benchmark():
    print("=" * 85)
    print("CODEMIND PHASE 5 — RETRIEVAL & GRAPH EXPANSION INTEGRITY BENCHMARK")
    print("=" * 85)

    # 1. Ingest repository
    print("\n[Step 1] Ingesting CodeMind production repository...")
    loader = RepositoryLoader()
    repo = loader.load_repository(str(root_dir / "codemind"))
    print(f"Loaded {repo.summary.total_files} files ({repo.summary.total_lines} lines).")

    # 2. Parse & Chunk
    print("\n[Step 2] Parsing AST symbols and chunking...")
    parsed_files = {}
    all_chunks = []
    for sf in repo.files:
        parsed = GLOBAL_PARSER_FACTORY.parse(sf)
        if parsed:
            parsed_files[sf.relative_path] = parsed
        chunks = GLOBAL_CHUNKER_FACTORY.chunk_file(sf, parsed)
        all_chunks.extend(chunks)
    print(f"Extracted {len(all_chunks)} chunks across {len(parsed_files)} parsed files.")

    # 3. Vector Indexing
    print("\n[Step 3] Initializing semantic retriever & vector store...")
    retriever = SemanticRetriever()
    indexed_count = retriever.index_chunks(all_chunks)
    print(f"Indexed {indexed_count} chunks in vector store.")

    # 4. Graph Construction
    print("\n[Step 4] Building Knowledge Graph & GraphQueryEngine...")
    graph_builder = KnowledgeGraphBuilder()
    nx_graph = graph_builder.build(repo, parsed_files)
    query_engine = GraphQueryEngine(nx_graph, graph_builder.nodes_by_id)
    summary = graph_builder.get_summary()
    print(f"Constructed graph: {summary.total_nodes} nodes, {summary.total_edges} edges.")

    # 5. Hybrid Retriever
    print("\n[Step 5] Initializing HybridGraphRetriever & Bidirectional Mapper...")
    hybrid_retriever = HybridGraphRetriever(
        retriever=retriever,
        graph=nx_graph,
        query_engine=query_engine,
        alpha=0.6,
        gamma=0.7,
    )
    hybrid_retriever.index(all_chunks, nx_graph)
    print(f"Mapped {len(hybrid_retriever.mapper.chunk_id_to_node_id)} chunks to graph nodes.")

    # 6. RAG Engine
    llm_provider = get_llm_provider(provider_type="mock")
    rag_engine = RAGEngine(
        retriever=retriever,
        hybrid_retriever=hybrid_retriever,
        llm_provider=llm_provider,
    )

    # =========================================================================
    # PART A: END-TO-END RETRIEVAL EVALUATION
    # User Query -> Vector Seeds -> Graph Expansion -> RAG
    # =========================================================================
    print("\n" + "=" * 85)
    print("PART A: END-TO-END RETRIEVAL EVALUATION (Natural Language Queries)")
    print("Notice: Evaluated using MockEmbeddingProvider (hash-based random projection).")
    print("=" * 85)

    e2e_results = []
    top_k = 4

    for bq in CORRECTED_BENCHMARK_QUERIES:
        qid = bq["id"]
        query = bq["query"]
        target_symbols = bq["target_symbols"]
        print(f"\n>>> [{qid}]: '{query}'")

        # --- Vector-Only Retrieval ---
        t_v0 = time.perf_counter()
        vec_results = hybrid_retriever.search(query=query, top_k=top_k, use_graph=False)
        t_v_retrieval = (time.perf_counter() - t_v0) * 1000

        t_rag_v0 = time.perf_counter()
        vec_rag = rag_engine.ask(query=query, top_k=top_k, use_graph=False)
        t_rag_v = (time.perf_counter() - t_rag_v0) * 1000

        vec_texts = " ".join([r.chunk.content + " " + (r.chunk.symbol_name or "") for r in vec_results])
        vec_covered = [sym for sym in target_symbols if sym.lower() in vec_texts.lower()]
        vec_coverage_pct = (len(vec_covered) / len(target_symbols)) * 100

        # --- Hybrid Graph-Aware Retrieval ---
        t_h0 = time.perf_counter()
        hyb_results = hybrid_retriever.search(query=query, top_k=top_k, use_graph=True)
        t_h_retrieval = (time.perf_counter() - t_h0) * 1000

        t_rag_h0 = time.perf_counter()
        hyb_rag = rag_engine.ask(query=query, top_k=top_k, use_graph=True)
        t_rag_h = (time.perf_counter() - t_rag_h0) * 1000

        seed_results = [r for r in hyb_results if getattr(r, "provenance", "") == "vector_seed"]
        expanded_results = [r for r in hyb_results if getattr(r, "provenance", "") == "graph_expanded"]
        ger = (len(expanded_results) / len(hyb_results)) * 100 if hyb_results else 0.0

        hyb_texts = " ".join([r.chunk.content + " " + (r.chunk.symbol_name or "") for r in hyb_results])
        hyb_covered = [sym for sym in target_symbols if sym.lower() in hyb_texts.lower()]
        hyb_coverage_pct = (len(hyb_covered) / len(target_symbols)) * 100

        intent_val = classify_query_intent(query)
        rels_used = list({r.relationship_type for r in expanded_results if r.relationship_type})

        item_result = {
            "query_id": qid,
            "query": query,
            "classified_intent": intent_val,
            "vector_only": {
                "retrieval_latency_ms": round(t_v_retrieval, 2),
                "total_rag_latency_ms": round(t_rag_v, 2),
                "citations_count": len(vec_rag.citations),
                "citations": vec_rag.citations,
                "covered_symbols": vec_covered,
                "symbol_coverage_pct": round(vec_coverage_pct, 1),
                "sources": [
                    {
                        "chunk_id": r.chunk.chunk_id,
                        "file": r.chunk.relative_path,
                        "lines": f"{r.chunk.start_line}-{r.chunk.end_line}",
                        "symbol": r.chunk.symbol_name,
                        "score": round(r.score, 4),
                    }
                    for r in vec_results
                ],
            },
            "hybrid": {
                "retrieval_latency_ms": round(t_h_retrieval, 2),
                "total_rag_latency_ms": round(t_rag_h, 2),
                "seed_count": len(seed_results),
                "expanded_count": len(expanded_results),
                "graph_enhancement_rate_pct": round(ger, 1),
                "relationships_used": rels_used,
                "citations_count": len(hyb_rag.citations),
                "citations": hyb_rag.citations,
                "covered_symbols": hyb_covered,
                "symbol_coverage_pct": round(hyb_coverage_pct, 1),
                "sources": [
                    {
                        "chunk_id": r.chunk.chunk_id,
                        "file": r.chunk.relative_path,
                        "lines": f"{r.chunk.start_line}-{r.chunk.end_line}",
                        "symbol": r.chunk.symbol_name,
                        "provenance": getattr(r, "provenance", "unknown"),
                        "rel": getattr(r, "relationship_type", None),
                        "hop": getattr(r, "hop_distance", 0),
                        "hybrid_score": round(r.score, 4),
                        "vec_score": round(r.vector_score, 4) if getattr(r, "vector_score", None) else None,
                        "graph_score": round(r.graph_score, 4) if getattr(r, "graph_score", None) else None,
                    }
                    for r in hyb_results
                ],
            },
        }
        e2e_results.append(item_result)

        print(f"  Classified Intent: {intent_val}")
        print(f"  Vector-Only Mode : Latency: {t_v_retrieval:.2f}ms | Coverage: {vec_coverage_pct:.1f}% ({len(vec_covered)}/{len(target_symbols)}) | Citations: {len(vec_rag.citations)}")
        print(f"  Hybrid Mode      : Latency: {t_h_retrieval:.2f}ms | Coverage: {hyb_coverage_pct:.1f}% ({len(hyb_covered)}/{len(target_symbols)}) | GER: {ger:.1f}% | Citations: {len(hyb_rag.citations)}")
        for exp in expanded_results:
            print(f"    - [Graph: {exp.relationship_type}] {exp.chunk.symbol_name} in {exp.chunk.relative_path}:{exp.chunk.start_line}-{exp.chunk.end_line} (Hop {exp.hop_distance}, score: {exp.graph_score:.3f})")

    # =========================================================================
    # PART B: CONTROLLED GRAPH TRAVERSAL EVALUATION
    # Verified Ground-Truth Seeds -> Graph Expansion Verification
    # =========================================================================
    print("\n" + "=" * 85)
    print("PART B: CONTROLLED GRAPH TRAVERSAL EVALUATION (Verified Ground-Truth Seeds)")
    print("Tests graph expansion mechanics directly without seed quality degradation.")
    print("=" * 85)

    controlled_results = []

    # B.1: Q1 Flow from should_ignore_file and RepositoryLoader._scan_directory
    seed_q1_filter = "method:ingestion/file_filter.py:FileFilter.should_ignore_file"
    seed_q1_loader = "method:ingestion/repo_loader.py:RepositoryLoader._scan_directory"
    exp_q1_filter = hybrid_retriever._expand_node(seed_q1_filter, seed_score=0.8, intent="flow")
    exp_q1_loader = hybrid_retriever._expand_node(seed_q1_loader, seed_score=0.8, intent="flow")

    print(f"\n>>> [B.1 / Q1] Seed: {seed_q1_filter} (intent='flow')")
    print(f"    Discovered {len(exp_q1_filter)} connected filtering methods along CALLS:")
    for e in exp_q1_filter:
        print(f"      [{e['relationship']}] {e['node_id']} (Hop {e['hop']}, score: {e['graph_score']:.3f})")

    has_binary_ext = any("is_binary_by_extension" in e["node_id"] for e in exp_q1_filter)
    has_binary_cnt = any("is_binary_content" in e["node_id"] for e in exp_q1_filter)
    has_ignore_dir = any("should_ignore_dir" in e["node_id"] for e in exp_q1_filter)
    print(f"    -> Status: should_ignore_dir={has_ignore_dir}, is_binary_by_extension={has_binary_ext}, is_binary_content={has_binary_cnt}")

    # B.2: Q2 Flow from ASTCodeChunker
    seed_q2 = "class:chunking/ast_chunker.py:ASTCodeChunker"
    exp_q2 = hybrid_retriever._expand_node(seed_q2, seed_score=0.8, intent="flow")
    print(f"\n>>> [B.2 / Q2] Seed: {seed_q2} (intent='flow')")
    print(f"    Discovered {len(exp_q2)} connected nodes along CONTAINS/INHERITS:")
    for e in exp_q2:
        print(f"      [{e['relationship']}] {e['node_id']} (Hop {e['hop']}, score: {e['graph_score']:.3f})")
    has_class_sig = any("_build_class_signature" in e["node_id"] for e in exp_q2)
    has_func_sig = any("_build_func_signature" in e["node_id"] for e in exp_q2)
    print(f"    -> Status: _build_class_signature={has_class_sig}, _build_func_signature={has_func_sig}")

    # B.3: Q3 Inheritance from ASTCodeChunker
    print(f"\n>>> [B.3 / Q3] Seed: {seed_q2} (intent='flow' - testing INHERITS)")
    inherits_targets = [e for e in exp_q2 if e["relationship"] == EdgeType.INHERITS]
    print(f"    Discovered {len(inherits_targets)} INHERITS edges:")
    for inh in inherits_targets:
        print(f"      [INHERITS] {inh['node_id']} (Hop {inh['hop']}, score: {inh['graph_score']:.3f})")
    has_base_chunker = any("BaseChunker" in e["node_id"] for e in inherits_targets)
    print(f"    -> Status: BaseChunker inherited={has_base_chunker}")

    # B.4: Q4 Impact from FileFilter
    seed_q4 = "class:ingestion/file_filter.py:FileFilter"
    seed_q4_file = "file:ingestion/file_filter.py"
    exp_q4 = hybrid_retriever._expand_node(seed_q4, seed_score=0.8, intent="impact")
    exp_q4_file = hybrid_retriever._expand_node(seed_q4_file, seed_score=0.8, intent="impact")
    print(f"\n>>> [B.4 / Q4] Seeds: {seed_q4} and {seed_q4_file} (intent='impact')")
    print(f"    Discovered incoming dependencies:")
    for e in exp_q4:
        print(f"      Incoming [{e['relationship']}] from: {e['node_id']} (Hop {e['hop']}, score: {e['graph_score']:.3f})")
    for e in exp_q4_file:
        print(f"      Incoming [{e['relationship']}] from: {e['node_id']} (Hop {e['hop']}, score: {e['graph_score']:.3f})")
    has_repo_loader_call = any("RepositoryLoader" in e["node_id"] for e in exp_q4)
    has_repo_loader_import = any("repo_loader.py" in e["node_id"] for e in exp_q4_file)
    print(f"    -> Status: RepositoryLoader call={has_repo_loader_call}, repo_loader.py import={has_repo_loader_import}")

    # Summary JSON packaging
    full_output = {
        "evaluation_a_end_to_end": e2e_results,
        "evaluation_b_controlled_graph": {
            "q1_repository_loader_flow": {
                "filter_seed": seed_q1_filter,
                "has_should_ignore_dir": has_ignore_dir,
                "has_is_binary_by_extension": has_binary_ext,
                "has_is_binary_content": has_binary_cnt,
                "discovered": exp_q1_filter,
            },
            "q2_ast_chunker_signatures": {
                "seed": seed_q2,
                "has_build_class_signature": has_class_sig,
                "has_build_func_signature": has_func_sig,
                "discovered": exp_q2,
            },
            "q3_ast_chunker_inheritance": {
                "seed": seed_q2,
                "has_base_chunker": has_base_chunker,
                "discovered": inherits_targets,
            },
            "q4_file_filter_impact": {
                "class_seed": seed_q4,
                "file_seed": seed_q4_file,
                "has_repo_loader_call": has_repo_loader_call,
                "has_repo_loader_import": has_repo_loader_import,
                "discovered_class_deps": exp_q4,
                "discovered_file_deps": exp_q4_file,
            },
        },
    }

    out_path = root_dir / "scratch" / "hybrid_benchmark_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(full_output, f, indent=2)
    print(f"\nSaved separated benchmark results to: {out_path}")


if __name__ == "__main__":
    run_benchmark()
