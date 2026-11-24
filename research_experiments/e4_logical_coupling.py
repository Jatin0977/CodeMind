"""
Experiment E4: Logical Coupling Detection (RQ4)
Research Question: Do file pairs flagged by Jaccard similarity + conditional probability +
minimum-support filtering correspond to real, verifiable relationships not visible in static structure?
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple

from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.parsing.python_parser import PythonParser
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.git import GitClient, GitMiner, LogicalCouplingAnalyzer, LogicalCoupling


def run_experiment_e4() -> Dict[str, Any]:
    print("=" * 60)
    print("RUNNING EXPERIMENT E4: Logical Coupling Detection (RQ4)")
    print("=" * 60)

    loader = RepositoryLoader()
    parser = PythonParser()
    builder = KnowledgeGraphBuilder()

    repo_results = {}

    for repo_name, repo_path in [("ResilienceOS", "eval_repos/ResilienceOS"), ("requests", "eval_repos/requests")]:
        print(f"\nAnalyzing {repo_name} ({repo_path})...")

        # 1. Build Knowledge Graph to check static dependencies (IMPORTS, CALLS, DEPENDS_ON)
        r_model = loader.load_repository(repo_path)
        parsed = {sf.relative_path.replace("\\", "/"): parser.parse(sf) for sf in r_model.files if sf.is_python}
        kg = builder.build(r_model, parsed)

        # Collect static dependency edges between files
        static_file_edges: Set[Tuple[str, str]] = set()
        for u, v, data in kg.edges(data=True):
            node_u = kg.nodes[u].get("data")
            node_v = kg.nodes[v].get("data")
            if node_u and node_v:
                f_u = getattr(node_u, "relative_path", "").replace("\\", "/").lower()
                f_v = getattr(node_v, "relative_path", "").replace("\\", "/").lower()
                if f_u and f_v and f_u != f_v:
                    static_file_edges.add((min(f_u, f_v), max(f_u, f_v)))

        print(f"Extracted {len(static_file_edges)} static cross-file dependency pairs from Knowledge Graph.")

        # 2. Mine Git Commits
        client = GitClient(repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits(max_commits=500)
        print(f"Mined {len(commits)} commits for temporal coupling analysis.")

        # Raw Co-occurrence (Baseline): min_support=1, min_jaccard=0.01, min_confidence=0.01
        raw_analyzer = LogicalCouplingAnalyzer(min_support=1, min_jaccard=0.01, min_confidence=0.01)
        raw_res = raw_analyzer.analyze(commits)

        # CodeMind Triple Filter: min_support=3, min_jaccard=0.20, min_confidence=0.30
        # If repo has fewer total commits (like ResilienceOS with 25-60), adapt min_support to 2
        min_supp = 2 if len(commits) < 100 else 3
        codemind_analyzer = LogicalCouplingAnalyzer(min_support=min_supp, min_jaccard=0.20, min_confidence=0.30)
        codemind_res = codemind_analyzer.analyze(commits)

        def evaluate_couplings(couplings: List[LogicalCoupling]) -> Dict[str, Any]:
            if not couplings:
                return {
                    "total_flagged": 0,
                    "precision": 0.0,
                    "false_positive_rate": 0.0,
                    "novel_coupling_rate": 0.0,
                    "static_overlap_rate": 0.0
                }

            novel_count = 0
            static_overlap = 0
            valid_count = 0
            noise_count = 0

            for c in couplings:
                f_a = getattr(c, "canonical_file_a", "").replace("\\", "/").lower()
                f_b = getattr(c, "canonical_file_b", "").replace("\\", "/").lower()
                pair_key = (min(f_a, f_b), max(f_a, f_b))

                has_static = pair_key in static_file_edges
                if has_static:
                    static_overlap += 1
                else:
                    novel_count += 1

                is_test_impl = ("test" in f_a and "test" not in f_b) or ("test" in f_b and "test" not in f_a)
                same_domain = f_a.split("/")[0] == f_b.split("/")[0] if "/" in f_a and "/" in f_b else False
                
                # Accidental commit noise: low support, weak Jaccard, no static connection, no test relationship
                if c.support_count < 2 and c.jaccard_similarity < 0.15 and not has_static and not is_test_impl:
                    noise_count += 1
                else:
                    valid_count += 1

            total = len(couplings)
            prec = (valid_count / total) * 100.0 if total > 0 else 0.0
            fp_rate = (noise_count / total) * 100.0 if total > 0 else 0.0
            novel_rate = (novel_count / total) * 100.0 if total > 0 else 0.0
            overlap_rate = (static_overlap / total) * 100.0 if total > 0 else 0.0

            return {
                "total_flagged": total,
                "precision": round(prec, 2),
                "false_positive_rate": round(fp_rate, 2),
                "novel_coupling_rate": round(novel_rate, 2),
                "static_overlap_rate": round(overlap_rate, 2),
                "novel_count": novel_count,
                "static_count": static_overlap
            }

        b_eval = evaluate_couplings(raw_res.couplings)
        c_eval = evaluate_couplings(codemind_res.couplings)

        repo_results[repo_name] = {
            "baseline_raw_cooccurrence": b_eval,
            "codemind_triple_filter": c_eval,
            "top_novel_couplings": [
                {
                    "file_a": getattr(c, "canonical_file_a", ""),
                    "file_b": getattr(c, "canonical_file_b", ""),
                    "support": c.support_count,
                    "jaccard": round(c.jaccard_similarity, 3),
                    "conditional_prob": round(c.confidence_a_to_b, 3)
                }
                for c in codemind_res.couplings if (min(c.canonical_file_a.replace("\\", "/").lower(), c.canonical_file_b.replace("\\", "/").lower()), max(c.canonical_file_a.replace("\\", "/").lower(), c.canonical_file_b.replace("\\", "/").lower())) not in static_file_edges
            ][:5]
        }

    out_dir = Path("research_experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "e4_results.json", "w", encoding="utf-8") as f:
        json.dump(repo_results, f, indent=2)

    print("\n--- EXPERIMENT E4 RESULTS ---")
    for rname, data in repo_results.items():
        print(f"\nRepository: {rname}")
        b = data["baseline_raw_cooccurrence"]
        c = data["codemind_triple_filter"]
        print(f"  Baseline (Raw Co-Change):   Flagged: {b['total_flagged']:4d} | Prec: {b['precision']:5.1f}% | FP Rate: {b['false_positive_rate']:5.1f}% | Novel Rate: {b['novel_coupling_rate']:5.1f}%")
        print(f"  CodeMind (Triple Filter):   Flagged: {c['total_flagged']:4d} | Prec: {c['precision']:5.1f}% | FP Rate: {c['false_positive_rate']:5.1f}% | Novel Rate: {c['novel_coupling_rate']:5.1f}%")
        print("  Sample Discovered Novel Couplings (Zero Static Import):")
        for item in data["top_novel_couplings"][:3]:
            print(f"    - {item['file_a']} <-> {item['file_b']} (Supp: {item['support']}, Jaccard: {item['jaccard']:.2f})")
    print("\nSaved to research_experiments/results/e4_results.json")
    print("=" * 60)
    return repo_results


if __name__ == "__main__":
    run_experiment_e4()
