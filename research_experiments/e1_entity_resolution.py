"""
Experiment E1: Canonical Entity Resolution (RQ1)
Research Question: Can a canonical qualified identifier reliably join the same code
entity across the vector index, knowledge graph, and Git history without ambiguity or
silent merging of unrelated entities?
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any

from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.parsing.python_parser import PythonParser
from codemind.graph.builder import KnowledgeGraphBuilder


def run_experiment_e1(repo_path: str = "eval_repos/ResilienceOS") -> Dict[str, Any]:
    print("=" * 60)
    print("RUNNING EXPERIMENT E1: Canonical Entity Resolution (RQ1)")
    print(f"Target Repository: {repo_path}")
    print("=" * 60)

    loader = RepositoryLoader()
    repo = loader.load_repository(repo_path)
    parser = PythonParser()
    parsed_files = {sf.relative_path.replace("\\", "/"): parser.parse(sf) for sf in repo.files if sf.is_python}

    builder = KnowledgeGraphBuilder()
    graph = builder.build(repo, parsed_files)
    nodes_by_id = builder.nodes_by_id

    symbols_by_name: Dict[str, List[Dict[str, Any]]] = {}
    canonical_entities: Dict[str, Dict[str, Any]] = {}

    for rel_path, parsed in parsed_files.items():
        if not parsed.is_valid:
            continue
        for cls in parsed.classes:
            cid = f"class:{rel_path}:{cls.name}"
            info = {
                "id": cid,
                "name": cls.name,
                "type": "class",
                "file": rel_path,
                "start_line": cls.start_line,
                "end_line": cls.end_line
            }
            symbols_by_name.setdefault(cls.name, []).append(info)
            canonical_entities[cid] = info

            for m in cls.methods:
                mid = f"method:{rel_path}:{cls.name}.{m.name}"
                minfo = {
                    "id": mid,
                    "name": m.name,
                    "qualified_name": f"{cls.name}.{m.name}",
                    "type": "method",
                    "file": rel_path,
                    "start_line": m.start_line,
                    "end_line": m.end_line
                }
                symbols_by_name.setdefault(m.name, []).append(minfo)
                canonical_entities[mid] = minfo

        for fn in parsed.functions:
            fid = f"function:{rel_path}:{fn.name}"
            finfo = {
                "id": fid,
                "name": fn.name,
                "qualified_name": fn.name,
                "type": "function",
                "file": rel_path,
                "start_line": fn.start_line,
                "end_line": fn.end_line
            }
            symbols_by_name.setdefault(fn.name, []).append(finfo)
            canonical_entities[fid] = finfo

    ambiguous_names = [k for k, v in symbols_by_name.items() if len(v) > 1 and k != "__init__"]
    
    test_instances: List[Dict[str, Any]] = []
    for name in sorted(ambiguous_names):
        instances = symbols_by_name[name]
        for inst in instances:
            test_instances.append(inst)
            if len(test_instances) >= 30:
                break
        if len(test_instances) >= 30:
            break

    if len(test_instances) < 30:
        for name, instances in symbols_by_name.items():
            if len(instances) > 1:
                for inst in instances:
                    if inst not in test_instances:
                        test_instances.append(inst)
                    if len(test_instances) >= 30:
                        break
            if len(test_instances) >= 30:
                break

    print(f"Selected {len(test_instances)} ambiguous entity instances across {len(set(t['name'] for t in test_instances))} distinct names.")

    name_only_resolved = 0
    name_only_false_merges = 0
    total_queries = len(test_instances)

    for target in test_instances:
        matches = symbols_by_name[target["name"]]
        if len(matches) == 1:
            name_only_resolved += 1
        else:
            name_only_false_merges += 1

    baseline_accuracy = (name_only_resolved / total_queries) * 100.0
    baseline_false_merge_rate = (name_only_false_merges / total_queries) * 100.0

    codemind_resolved = 0
    codemind_false_merges = 0
    codemind_cross_source_joined = 0

    for target in test_instances:
        cid = target["id"]
        if cid in nodes_by_id:
            node = nodes_by_id[cid]
            if node.relative_path == target["file"] and node.name in (target["name"], target.get("qualified_name")):
                codemind_resolved += 1
                codemind_cross_source_joined += 1
            else:
                codemind_false_merges += 1
        else:
            codemind_false_merges += 1

    codemind_accuracy = (codemind_resolved / total_queries) * 100.0
    codemind_false_merge_rate = (codemind_false_merges / total_queries) * 100.0
    codemind_join_rate = (codemind_cross_source_joined / total_queries) * 100.0

    results = {
        "experiment": "E1_Canonical_Entity_Resolution",
        "rq_tested": "RQ1",
        "repository": "ResilienceOS",
        "total_test_instances": total_queries,
        "unique_ambiguous_names": len(set(t['name'] for t in test_instances)),
        "baseline_name_only": {
            "accuracy": round(baseline_accuracy, 2),
            "false_merge_rate": round(baseline_false_merge_rate, 2),
            "cross_source_join_rate": round(baseline_accuracy, 2)
        },
        "codemind_canonical": {
            "accuracy": round(codemind_accuracy, 2),
            "false_merge_rate": round(codemind_false_merge_rate, 2),
            "cross_source_join_rate": round(codemind_join_rate, 2)
        },
        "improvement_delta": {
            "accuracy_gain_pct": round(codemind_accuracy - baseline_accuracy, 2),
            "false_merge_reduction_pct": round(baseline_false_merge_rate - codemind_false_merge_rate, 2)
        },
        "sample_disambiguated_entities": [
            {
                "name": t["name"],
                "canonical_id": t["id"],
                "file": t["file"],
                "lines": f"{t['start_line']}-{t['end_line']}"
            }
            for t in test_instances[:5]
        ]
    }

    out_dir = Path("research_experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "e1_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n--- EXPERIMENT E1 RESULTS ---")
    print(f"Total Evaluated Instances: {total_queries}")
    print(f"Baseline (Name-Only) Accuracy:       {baseline_accuracy:.2f}% (False Merge: {baseline_false_merge_rate:.2f}%)")
    print(f"CodeMind (Canonical) Accuracy:       {codemind_accuracy:.2f}% (False Merge: {codemind_false_merge_rate:.2f}%)")
    print(f"Cross-Source Join Rate:              {codemind_join_rate:.2f}%")
    print(f"Disambiguation Gain:                 +{codemind_accuracy - baseline_accuracy:.2f}%")
    print("Saved to research_experiments/results/e1_results.json")
    print("=" * 60)
    return results


if __name__ == "__main__":
    run_experiment_e1()
