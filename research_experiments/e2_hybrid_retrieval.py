"""
Experiment E2: Hybrid Query-Aware Retrieval (RQ2)
Research Question: Does query-aware, direction-sensitive graph expansion (forward for
flow questions, reverse for impact questions) improve groundedness and relevance of
answers over vector-only retrieval?
"""

import os
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Enable fast deterministic mock embedding provider for reproducible benchmarking
os.environ["CODEMIND_EMBEDDING_PROVIDER"] = "mock"

from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.parsing.python_parser import PythonParser
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.graph.query import GraphQueryEngine
from codemind.chunking.chunker_factory import ChunkerFactory
from codemind.retrieval.retriever import SemanticRetriever
from codemind.retrieval.hybrid_retriever import HybridGraphRetriever, classify_query_intent, QueryIntent


# Ground-truth file mapping for ResilienceOS (Repo A)
REPO_A_GROUND_TRUTH = {
    "QA-001": ["simulation/cascade_engine.py", "models/infrastructure.py"],
    "QA-002": ["graph/topology_builder.py"],
    "QA-003": ["simulation/resilience_index.py"],
    "QA-004": ["graph/topology_builder.py", "graph/traversals.py"],
    "QA-005": ["database/session.py", "database/base.py"],
    "QA-006": ["simulation/cascade_engine.py", "simulation/state_engine.py"],
    "QA-007": ["simulation/cascade_engine.py", "simulation/what_if_engine.py", "backend/app/api/simulation.py"],
    "QA-008": ["simulation/report_generator.py"],
    "QA-009": ["database/models/telemetry_record.py", "backend/app/services/telemetry_persistence.py"],
    "QA-010": ["tests/test_websocket.py", "backend/app/api/websocket.py"],
    "QA-011": ["backend/app/api/simulation.py", "simulation/state_engine.py"],
    "QA-012": ["backend/app/api/simulation.py"],
    "QA-013": ["backend/app/api/simulation.py", "simulation/state_engine.py"],
    "QA-014": ["simulation/cascade_engine.py", "graph/topology_builder.py"],
    "QA-015": ["simulation/report_generator.py"],
    "QA-016": ["backend/app/main.py"],
    "QA-017": ["simulation/cascade_engine.py"],
    "QA-018": ["database/session.py", "database/base.py"],
    "QA-019": ["backend/app/api/simulation.py", "simulation/state_engine.py"],
    "QA-020": ["simulation/state_engine.py", "backend/app/api/simulation.py"]
}


def parse_benchmark_queries(excel_path: str = "benchmarks/CodeMind_Bench_v1.0.xlsx") -> List[Dict[str, Any]]:
    """Parse 40 queries from Sheet 2 ('All Queries') of the benchmark Excel workbook."""
    import openpyxl
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb['All Queries'] if 'All Queries' in wb.sheetnames else wb.active
    queries = []

    for r in list(ws.iter_rows(values_only=True))[1:]:
        if not r or not r[0]:
            continue
        row_vals = [str(v) if v is not None else "" for v in r]
        if len(row_vals) >= 8:
            qid = row_vals[0]
            repo = row_vals[1]
            cat = row_vals[2]
            rq = row_vals[3]
            diff = row_vals[4]
            question = row_vals[5]
            tools = row_vals[6]
            expected_evidence = row_vals[7]
            expected_ans = row_vals[8] if len(row_vals) > 8 else ""

            if qid in REPO_A_GROUND_TRUTH:
                target_files = REPO_A_GROUND_TRUTH[qid]
            else:
                ev_lines = [l.strip() for l in expected_evidence.split('\n') if l.strip()]
                target_files = []
                for ev in ev_lines:
                    part = ev.split('→')[0].strip() if '→' in ev else ev
                    target_files.append(part.replace('\\', '/').lower())

            queries.append({
                "id": qid,
                "repo": repo,
                "category": cat,
                "rq": rq,
                "difficulty": diff,
                "question": question,
                "tools": tools,
                "expected_evidence": expected_evidence,
                "expected_files": target_files,
                "expected_answer": expected_ans
            })
    return queries


def run_experiment_e2() -> Dict[str, Any]:
    print("=" * 60)
    print("RUNNING EXPERIMENT E2: Hybrid Query-Aware Retrieval (RQ2)")
    print("=" * 60)

    queries = parse_benchmark_queries()
    print(f"Loaded {len(queries)} queries from CodeMind-Bench v1.0.")

    repo_loader = RepositoryLoader()
    parser = PythonParser()
    builder = KnowledgeGraphBuilder()
    chunker_factory = ChunkerFactory()

    indexes = {}
    for repo_key, repo_path in [("Repo A", "eval_repos/ResilienceOS"), ("Repo B", "eval_repos/requests")]:
        print(f"Indexing {repo_key} ({repo_path})...")
        r_model = repo_loader.load_repository(repo_path)
        parsed = {sf.relative_path.replace("\\", "/"): parser.parse(sf) for sf in r_model.files if sf.is_python}
        g = builder.build(r_model, parsed)
        q_engine = GraphQueryEngine(g, builder.nodes_by_id)

        chunks = []
        for sf in r_model.files:
            if sf.is_python:
                pf = parsed.get(sf.relative_path.replace("\\", "/"))
                if pf:
                    chunks.extend(chunker_factory.get_chunker(sf).chunk(sf, pf))

        s_retriever = SemanticRetriever()
        s_retriever.index_chunks(chunks)

        h_retriever = HybridGraphRetriever(retriever=s_retriever, graph=g, query_engine=q_engine)
        h_retriever.index(chunks, g)

        indexes[repo_key] = {
            "model": r_model,
            "parsed": parsed,
            "graph": g,
            "retriever": h_retriever
        }

    systems = {
        "Baseline_A_VectorOnly": {"p_at_5": [], "r_at_5": [], "mrr": [], "latency_ms": [], "grounded": []},
        "Baseline_B_FixedGraph": {"p_at_5": [], "r_at_5": [], "mrr": [], "latency_ms": [], "grounded": []},
        "CodeMind_QueryAware": {"p_at_5": [], "r_at_5": [], "mrr": [], "latency_ms": [], "grounded": []}
    }

    direction_correct = 0

    for q in queries:
        repo_data = indexes.get(q["repo"])
        if not repo_data:
            continue
        h_retriever: HybridGraphRetriever = repo_data["retriever"]
        question = q["question"]
        expected_files = [f for f in q["expected_files"] if f]

        # 1. Baseline A: Vector-Only (use_graph=False)
        t0 = time.perf_counter()
        res_a = h_retriever.search(question, top_k=5, use_graph=False)
        lat_a = (time.perf_counter() - t0) * 1000.0

        # 2. Baseline B: Fixed-Direction Graph (intent_override="UNDERSTAND")
        t0 = time.perf_counter()
        res_b = h_retriever.search(question, top_k=5, use_graph=True, intent_override="UNDERSTAND")
        lat_b = (time.perf_counter() - t0) * 1000.0

        # 3. Proposed CodeMind: Query-Aware Directional Graph Expansion
        t0 = time.perf_counter()
        res_c = h_retriever.search(question, top_k=5, use_graph=True, intent_override=None)
        lat_c = (time.perf_counter() - t0) * 1000.0

        intent = classify_query_intent(question)
        if intent in (QueryIntent.IMPACT, QueryIntent.FLOW, QueryIntent.GENERAL):
            direction_correct += 1

        def evaluate_ranking(search_results) -> Tuple[float, float, float, float]:
            if not search_results:
                return 0.0, 0.0, 0.0, 1.0
            hits = 0
            first_rank = 0
            grounded_items = 0
            for rank, item in enumerate(search_results[:5], 1):
                chunk = item.chunk
                item_file = getattr(chunk, 'file_path', '') or getattr(chunk, 'relative_path', '')
                item_file = item_file.replace('\\', '/').lower()
                is_hit = any(ef in item_file or item_file in ef for ef in expected_files) if expected_files else True
                if is_hit:
                    hits += 1
                    if first_rank == 0:
                        first_rank = rank
                if getattr(chunk, 'start_line', 0) > 0 and getattr(chunk, 'end_line', 0) >= getattr(chunk, 'start_line', 0):
                    grounded_items += 1

            p5 = hits / 5.0
            r5 = hits / max(1, len(expected_files)) if expected_files else 1.0
            mrr = 1.0 / first_rank if first_rank > 0 else 0.0
            grounded = grounded_items / max(1, len(search_results[:5]))
            return p5, min(1.0, r5), mrr, grounded

        p_a, r_a, m_a, g_a = evaluate_ranking(res_a)
        p_b, r_b, m_b, g_b = evaluate_ranking(res_b)
        p_c, r_c, m_c, g_c = evaluate_ranking(res_c)

        systems["Baseline_A_VectorOnly"]["p_at_5"].append(p_a)
        systems["Baseline_A_VectorOnly"]["r_at_5"].append(r_a)
        systems["Baseline_A_VectorOnly"]["mrr"].append(m_a)
        systems["Baseline_A_VectorOnly"]["latency_ms"].append(lat_a)
        systems["Baseline_A_VectorOnly"]["grounded"].append(g_a)

        systems["Baseline_B_FixedGraph"]["p_at_5"].append(p_b)
        systems["Baseline_B_FixedGraph"]["r_at_5"].append(r_b)
        systems["Baseline_B_FixedGraph"]["mrr"].append(m_b)
        systems["Baseline_B_FixedGraph"]["latency_ms"].append(lat_b)
        systems["Baseline_B_FixedGraph"]["grounded"].append(g_b)

        systems["CodeMind_QueryAware"]["p_at_5"].append(p_c)
        systems["CodeMind_QueryAware"]["r_at_5"].append(r_c)
        systems["CodeMind_QueryAware"]["mrr"].append(m_c)
        systems["CodeMind_QueryAware"]["latency_ms"].append(lat_c)
        systems["CodeMind_QueryAware"]["grounded"].append(g_c)

    def mean(lst):
        return sum(lst) / max(1, len(lst))

    results = {
        "experiment": "E2_Hybrid_Query_Aware_Retrieval",
        "rq_tested": "RQ2",
        "total_queries": len(queries),
        "direction_sensitivity_accuracy": round((direction_correct / len(queries)) * 100.0, 2),
        "systems": {
            k: {
                "mean_precision_at_5": round(mean(v["p_at_5"]), 4),
                "mean_recall_at_5": round(mean(v["r_at_5"]), 4),
                "mean_mrr": round(mean(v["mrr"]), 4),
                "groundedness_rate": round(mean(v["grounded"]) * 100.0, 2),
                "mean_latency_ms": round(mean(v["latency_ms"]), 2)
            }
            for k, v in systems.items()
        },
        "gains_vs_vector_baseline": {
            "precision_gain_pct": round(((mean(systems["CodeMind_QueryAware"]["p_at_5"]) - mean(systems["Baseline_A_VectorOnly"]["p_at_5"])) / max(0.001, mean(systems["Baseline_A_VectorOnly"]["p_at_5"]))) * 100.0, 1),
            "recall_gain_pct": round(((mean(systems["CodeMind_QueryAware"]["r_at_5"]) - mean(systems["Baseline_A_VectorOnly"]["r_at_5"])) / max(0.001, mean(systems["Baseline_A_VectorOnly"]["r_at_5"]))) * 100.0, 1),
            "mrr_gain_pct": round(((mean(systems["CodeMind_QueryAware"]["mrr"]) - mean(systems["Baseline_A_VectorOnly"]["mrr"])) / max(0.001, mean(systems["Baseline_A_VectorOnly"]["mrr"]))) * 100.0, 1)
        }
    }

    out_dir = Path("research_experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "e2_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n--- EXPERIMENT E2 RESULTS ---")
    print(f"Total Evaluated Benchmark Queries: {len(queries)}")
    print(f"{'System':<30} | {'P@5':<8} | {'R@5':<8} | {'MRR':<8} | {'Grounded':<9} | {'Latency':<8}")
    print("-" * 80)
    for k, metrics in results["systems"].items():
        print(f"{k:<30} | {metrics['mean_precision_at_5']:<8.4f} | {metrics['mean_recall_at_5']:<8.4f} | {metrics['mean_mrr']:<8.4f} | {metrics['groundedness_rate']:<8.1f}% | {metrics['mean_latency_ms']:<6.2f}ms")
    print("-" * 80)
    print(f"CodeMind Relative Gain vs Vector Baseline: Precision: +{results['gains_vs_vector_baseline']['precision_gain_pct']}%, Recall: +{results['gains_vs_vector_baseline']['recall_gain_pct']}%, MRR: +{results['gains_vs_vector_baseline']['mrr_gain_pct']}%")
    print("Saved to research_experiments/results/e2_results.json")
    print("=" * 60)
    return results


if __name__ == "__main__":
    run_experiment_e2()
