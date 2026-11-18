"""
Final Acceptance Evaluation for CodeMind Phase 5.
Calculates Precision@K, Recall@K, MRR, and Expansion Relevance
for both Vector-Only and Hybrid Graph-Aware Retrieval.
"""

import sys
import time
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import tests.conftest

from CodeMind.ingestion.repo_loader import RepositoryLoader
from CodeMind.parsing.parser_factory import GLOBAL_PARSER_FACTORY
from CodeMind.chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from CodeMind.graph.builder import KnowledgeGraphBuilder
from CodeMind.graph.query import GraphQueryEngine
from CodeMind.graph.models import EdgeType
from CodeMind.retrieval.retriever import SemanticRetriever
from CodeMind.retrieval.hybrid_retriever import HybridGraphRetriever, classify_query_intent
from CodeMind.rag.engine import RAGEngine
from CodeMind.rag.providers.factory import get_llm_provider


GROUND_TRUTH_DEFINITIONS = {
    "Q1": {
        "id": "Q1_FLOW",
        "query": "How does RepositoryLoader filter ignored directories and binary files?",
        "intent": "flow",
        "target_symbol_substrings": [
            "RepositoryLoader",
            "FileFilter",
            "should_ignore_dir",
            "should_ignore_file",
            "is_binary_by_extension",
            "is_binary_content",
        ],
        "target_file_prefixes": ["ingestion/repo_loader.py", "ingestion/file_filter.py"],
        "controlled_seed": "method:ingestion/file_filter.py:FileFilter.should_ignore_file",
        "controlled_targets": [
            "method:ingestion/file_filter.py:FileFilter.is_binary_by_extension",
            "method:ingestion/file_filter.py:FileFilter.is_binary_content",
            "method:ingestion/file_filter.py:FileFilter.should_ignore_dir",
        ],
    },
    "Q2": {
        "id": "Q2_FLOW",
        "query": "Explain how the AST chunker builds signatures for classes and functions.",
        "intent": "flow",
        "target_symbol_substrings": [
            "ASTCodeChunker",
            "_build_class_signature",
            "_build_func_signature",
            "chunk",
        ],
        "target_file_prefixes": ["chunking/ast_chunker.py"],
        "controlled_seed": "class:chunking/ast_chunker.py:ASTCodeChunker",
        "controlled_targets": [
            "method:chunking/ast_chunker.py:ASTCodeChunker._build_class_signature",
            "method:chunking/ast_chunker.py:ASTCodeChunker._build_func_signature",
        ],
    },
    "Q3": {
        "id": "Q3_INHERIT",
        "query": "What base class does ASTCodeChunker inherit and what contract does it implement?",
        "intent": "flow",
        "target_symbol_substrings": [
            "ASTCodeChunker",
            "BaseChunker",
        ],
        "target_file_prefixes": ["chunking/ast_chunker.py", "chunking/base_chunker.py"],
        "controlled_seed": "class:chunking/ast_chunker.py:ASTCodeChunker",
        "controlled_targets": [
            "class:chunking/base_chunker.py:BaseChunker",
        ],
    },
    "Q4": {
        "id": "Q4_IMPACT",
        "query": "What components invoke or depend on file_filter.py?",
        "intent": "impact",
        "target_symbol_substrings": [
            "RepositoryLoader",
            "repo_loader.py",
            "ingestion/__init__.py",
        ],
        "target_file_prefixes": ["ingestion/repo_loader.py", "ingestion/__init__.py"],
        "controlled_seed": "class:ingestion/file_filter.py:FileFilter",
        "controlled_targets": [
            "method:ingestion/repo_loader.py:RepositoryLoader.__init__",
            "file:ingestion/repo_loader.py",
        ],
    },
}


def is_chunk_relevant(chunk, target_symbols, target_files):
    """Determine whether a chunk is genuinely relevant to the ground truth targets."""
    file_match = any(chunk.relative_path.startswith(p) for p in target_files)
    sym_match = any(
        sym.lower() in (chunk.symbol_name or "").lower() or sym.lower() in chunk.content.lower()
        for sym in target_symbols
    )
    # A chunk is relevant if it comes from the target file and matches the target symbol
    return file_match and sym_match


def compute_metrics(results, target_symbols, target_files, k=4):
    """Compute Precision@K, Recall@K, and MRR."""
    top_results = results[:k]
    relevance_flags = [is_chunk_relevant(r.chunk, target_symbols, target_files) for r in top_results]

    # Precision@K: fraction of retrieved top-k chunks that are relevant
    relevant_count = sum(relevance_flags)
    precision_at_k = relevant_count / k if k > 0 else 0.0

    # Recall proxy: fraction of target symbols covered in retrieved chunks
    retrieved_text = " ".join([r.chunk.content + " " + (r.chunk.symbol_name or "") for r in top_results])
    covered_syms = [s for s in target_symbols if s.lower() in retrieved_text.lower()]
    recall_at_k = len(covered_syms) / len(target_symbols) if target_symbols else 0.0

    # MRR (Mean Reciprocal Rank): 1 / rank of first relevant chunk
    mrr = 0.0
    for idx, is_rel in enumerate(relevance_flags, start=1):
        if is_rel:
            mrr = 1.0 / idx
            break

    return {
        "precision_at_k": round(precision_at_k, 3),
        "recall_at_k": round(recall_at_k, 3),
        "mrr": round(mrr, 3),
        "relevant_count": relevant_count,
        "covered_symbols": covered_syms,
        "relevance_flags": relevance_flags,
    }


def run_acceptance_eval():
    print("=" * 85)
    print("PHASE 5 FINAL ACCEPTANCE EVALUATION: VECTOR-ONLY VS. HYBRID GRAPH-AWARE")
    print("Criterion: Hybrid retrieval should outperform vector-only retrieval on representative sample queries.")
    print("=" * 85)

    # 1. Ingest
    loader = RepositoryLoader()
    repo = loader.load_repository(str(root_dir / "CodeMind"))
    parsed_files = {sf.relative_path: GLOBAL_PARSER_FACTORY.parse(sf) for sf in repo.files if GLOBAL_PARSER_FACTORY.parse(sf)}
    chunks = []
    for sf in repo.files:
        chunks.extend(GLOBAL_CHUNKER_FACTORY.chunk_file(sf, parsed_files.get(sf.relative_path)))

    retriever = SemanticRetriever()
    retriever.index_chunks(chunks)

    builder = KnowledgeGraphBuilder()
    nx_g = builder.build(repo, parsed_files)
    query_engine = GraphQueryEngine(nx_g, builder.nodes_by_id)

    hybrid = HybridGraphRetriever(retriever=retriever, graph=nx_g, query_engine=query_engine)
    hybrid.index(chunks, nx_g)

    rag = RAGEngine(retriever=retriever, hybrid_retriever=hybrid, llm_provider=get_llm_provider(provider_type="mock"))

    K = 4
    eval_a_summary = {}

    print("\n" + "-" * 85)
    print(f"PART A: END-TO-END RETRIEVAL EVALUATION (Top-{K})")
    print("-" * 85)

    for qkey, qdata in GROUND_TRUTH_DEFINITIONS.items():
        qid = qdata["id"]
        query = qdata["query"]
        target_syms = qdata["target_symbol_substrings"]
        target_files = qdata["target_file_prefixes"]

        # Vector-Only
        v_results = hybrid.search(query, top_k=K, use_graph=False)
        v_rag = rag.ask(query, top_k=K, use_graph=False)
        v_metrics = compute_metrics(v_results, target_syms, target_files, k=K)

        # Hybrid
        h_results = hybrid.search(query, top_k=K, use_graph=True)
        h_rag = rag.ask(query, top_k=K, use_graph=True)
        h_metrics = compute_metrics(h_results, target_syms, target_files, k=K)

        # Inspect graph-expanded nodes in hybrid
        expanded_nodes = [r for r in h_results if getattr(r, "provenance", "") == "graph_expanded"]
        rel_expanded = [r for r in expanded_nodes if is_chunk_relevant(r.chunk, target_syms, target_files)]
        irrel_expanded = [r for r in expanded_nodes if not is_chunk_relevant(r.chunk, target_syms, target_files)]

        eval_a_summary[qkey] = {
            "query": query,
            "vector": {
                "precision": v_metrics["precision_at_k"],
                "recall": v_metrics["recall_at_k"],
                "mrr": v_metrics["mrr"],
                "citations": len(v_rag.citations),
                "is_sufficient": v_rag.is_sufficient,
                "chunks": [f"{r.chunk.relative_path}:{r.chunk.start_line}-{r.chunk.end_line} ({r.chunk.symbol_name})" for r in v_results],
            },
            "hybrid": {
                "precision": h_metrics["precision_at_k"],
                "recall": h_metrics["recall_at_k"],
                "mrr": h_metrics["mrr"],
                "citations": len(h_rag.citations),
                "is_sufficient": h_rag.is_sufficient,
                "chunks": [f"{r.chunk.relative_path}:{r.chunk.start_line}-{r.chunk.end_line} ({r.chunk.symbol_name}, prov={getattr(r, 'provenance', 'unknown')})" for r in h_results],
                "total_expanded": len(expanded_nodes),
                "relevant_expanded": len(rel_expanded),
                "irrelevant_expanded": len(irrel_expanded),
                "relevant_expanded_symbols": [r.chunk.symbol_name for r in rel_expanded],
                "irrelevant_expanded_symbols": [r.chunk.symbol_name for r in irrel_expanded],
            },
        }

        print(f"\n>>> [{qid}]: '{query}'")
        print(f"  Vector-Only : P@{K}: {v_metrics['precision_at_k']} | R@{K}: {v_metrics['recall_at_k']} | MRR: {v_metrics['mrr']} | Citations: {len(v_rag.citations)} | Suff: {v_rag.is_sufficient}")
        print(f"  Hybrid Mode : P@{K}: {h_metrics['precision_at_k']} | R@{K}: {h_metrics['recall_at_k']} | MRR: {h_metrics['mrr']} | Citations: {len(h_rag.citations)} | Suff: {h_rag.is_sufficient}")
        print(f"  Graph Exp   : Total={len(expanded_nodes)}, Relevant={len(rel_expanded)}, Irrelevant={len(irrel_expanded)}")
        if rel_expanded:
            print(f"    - Relevant Exp: {[r.chunk.symbol_name for r in rel_expanded]}")
        if irrel_expanded:
            print(f"    - Irrelevant Exp: {[r.chunk.symbol_name for r in irrel_expanded]}")

    # Summary Averages
    avg_v_p = sum(eval_a_summary[q]["vector"]["precision"] for q in eval_a_summary) / len(eval_a_summary)
    avg_v_r = sum(eval_a_summary[q]["vector"]["recall"] for q in eval_a_summary) / len(eval_a_summary)
    avg_v_mrr = sum(eval_a_summary[q]["vector"]["mrr"] for q in eval_a_summary) / len(eval_a_summary)

    avg_h_p = sum(eval_a_summary[q]["hybrid"]["precision"] for q in eval_a_summary) / len(eval_a_summary)
    avg_h_r = sum(eval_a_summary[q]["hybrid"]["recall"] for q in eval_a_summary) / len(eval_a_summary)
    avg_h_mrr = sum(eval_a_summary[q]["hybrid"]["mrr"] for q in eval_a_summary) / len(eval_a_summary)

    total_exp = sum(eval_a_summary[q]["hybrid"]["total_expanded"] for q in eval_a_summary)
    total_rel_exp = sum(eval_a_summary[q]["hybrid"]["relevant_expanded"] for q in eval_a_summary)
    total_irrel_exp = sum(eval_a_summary[q]["hybrid"]["irrelevant_expanded"] for q in eval_a_summary)

    print("\n" + "=" * 85)
    print("END-TO-END METRIC SUMMARY (PART A)")
    print(f"Vector-Only Retrieval : Mean P@{K}: {avg_v_p:.3f} | Mean R@{K}: {avg_v_r:.3f} | Mean MRR: {avg_v_mrr:.3f}")
    print(f"Hybrid Retrieval      : Mean P@{K}: {avg_h_p:.3f} | Mean R@{K}: {avg_h_r:.3f} | Mean MRR: {avg_h_mrr:.3f}")
    print(f"Graph Expansions      : Total Expanded: {total_exp} | Relevant: {total_rel_exp} ({(total_rel_exp/total_exp)*100 if total_exp else 0:.1f}%) | Irrelevant: {total_irrel_exp}")
    print("=" * 85)

    # PART B: CONTROLLED GRAPH TRAVERSAL
    print("\n" + "-" * 85)
    print("PART B: CONTROLLED GRAPH TRAVERSAL EVALUATION (Verified Seeds)")
    print("-" * 85)

    b_results = {}
    for qkey, qdata in GROUND_TRUTH_DEFINITIONS.items():
        seed = qdata["controlled_seed"]
        intent = qdata["intent"]
        expected_targets = qdata["controlled_targets"]

        exp = hybrid._expand_node(seed, seed_score=0.8, intent=intent)
        discovered_nodes = {e["node_id"] for e in exp}
        found_targets = [t for t in expected_targets if t in discovered_nodes]
        coverage = len(found_targets) / len(expected_targets)

        b_results[qkey] = {
            "seed": seed,
            "intent": intent,
            "expected_targets": expected_targets,
            "found_targets": found_targets,
            "coverage_pct": round(coverage * 100, 1),
            "all_discovered": [f"{e['relationship']} -> {e['node_id']} (hop={e['hop']}, score={e['graph_score']:.3f})" for e in exp],
        }
        print(f"\n>>> [{qdata['id']}] Controlled Seed: {seed} ({intent})")
        print(f"    Expected Targets: {expected_targets}")
        print(f"    Found Targets   : {found_targets} ({coverage*100:.1f}%)")
        print(f"    Total Expansions: {len(exp)}")

    # Write report to JSON
    with open(root_dir / "scratch" / "acceptance_evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump({"part_a_end_to_end": eval_a_summary, "part_b_controlled": b_results}, f, indent=2)


if __name__ == "__main__":
    run_acceptance_eval()
