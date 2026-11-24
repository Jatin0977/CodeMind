"""
Experiment E3: Multi-Signal Impact Scoring and Blast Radius Evaluation (RQ3)

Research Question:
Does combining structural reverse dependency reachability, 1-hop temporal co-change coupling,
and static test intelligence identify actually-affected code components and relevant regression
tests more accurately and completely than structural reachability alone?

This script performs reproducible, exact-path matching evaluation across 15 controlled scenarios,
evaluating the full system, baseline models, isolated ablations, and the multi-signal target risk scorer.
"""

import os
import sys
sys.path.insert(0, os.path.abspath("."))
import json
import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional

from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.parsing.python_parser import PythonParser
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.git import GitClient, GitMiner, CodeChurnAnalyzer, LogicalCouplingAnalyzer
from codemind.impact.engine import ChangeImpactEngine
from codemind.impact.models import ChangeTarget, ImpactAnalysisConfig
from codemind.impact.test_intelligence import TestIntelligenceEngine
from codemind.impact.scorer import MultiSignalImpactScorer


def normalize_canonical_path(path: str, repo_root: str = "eval_repos/ResilienceOS") -> str:
    """
    Canonical path normalization: converts separators to forward slashes,
    strips absolute or relative repository root prefixes, trims leading ./, and lowercases.
    """
    if not path:
        return ""
    norm = path.replace(os.sep, "/").replace("\\", "/").strip()
    abs_repo = os.path.abspath(repo_root).replace(os.sep, "/").replace("\\", "/").strip().rstrip("/")
    try:
        abs_p = os.path.abspath(norm).replace(os.sep, "/").replace("\\", "/").strip()
        if abs_p.lower().startswith(abs_repo.lower() + "/"):
            norm = abs_p[len(abs_repo) + 1:]
    except Exception:
        pass
    while norm.startswith("./"):
        norm = norm[2:]
    for prefix in ["eval_repos/resilienceos/", "eval_repos/resilienceos"]:
        if norm.lower().startswith(prefix):
            norm = norm[len(prefix):].lstrip("/")
    return norm.strip("/").lower()


def is_test_file(path: str) -> bool:
    """Categorize entity as regression test suite or code component."""
    p = path.lower()
    return (
        p.startswith("tests/")
        or p.startswith("test/")
        or p.endswith("_test.py")
        or "/test_" in p
        or p.startswith("test_")
    )


def define_controlled_scenarios() -> List[Dict[str, Any]]:
    """
    The 15 controlled change scenarios across Leaf, Service, and Core tiers.
    Total: 64 ground-truth scenario-target instances (52 code, 12 test).
    """
    return [
        # --- 5 LEAF SCENARIOS ---
        {
            "id": "SCEN-01",
            "tier": "Leaf",
            "node_id": "file:simulation/report_generator.py",
            "name": "simulation/report_generator.py",
            "file": "simulation/report_generator.py",
            "expected_affected": [
                "simulation/report_generator.py",
                "tests/test_report_generator.py"
            ]
        },
        {
            "id": "SCEN-02",
            "tier": "Leaf",
            "node_id": "file:models/api_responses.py",
            "name": "models/api_responses.py",
            "file": "models/api_responses.py",
            "expected_affected": [
                "models/api_responses.py",
                "backend/app/api/simulation.py",
                "backend/app/core/errors.py"
            ]
        },
        {
            "id": "SCEN-03",
            "tier": "Leaf",
            "node_id": "file:backend/app/core/logging_config.py",
            "name": "backend/app/core/logging_config.py",
            "file": "backend/app/core/logging_config.py",
            "expected_affected": [
                "backend/app/core/logging_config.py",
                "backend/app/main.py"
            ]
        },
        {
            "id": "SCEN-04",
            "tier": "Leaf",
            "node_id": "file:database/models/simulation_run.py",
            "name": "database/models/simulation_run.py",
            "file": "database/models/simulation_run.py",
            "expected_affected": [
                "database/models/simulation_run.py",
                "backend/app/services/simulation_persistence.py"
            ]
        },
        {
            "id": "SCEN-05",
            "tier": "Leaf",
            "node_id": "file:simulation/explanation_engine.py",
            "name": "simulation/explanation_engine.py",
            "file": "simulation/explanation_engine.py",
            "expected_affected": [
                "simulation/explanation_engine.py",
                "backend/app/api/simulation.py"
            ]
        },

        # --- 5 SERVICE SCENARIOS ---
        {
            "id": "SCEN-06",
            "tier": "Service",
            "node_id": "file:simulation/resilience_index.py",
            "name": "simulation/resilience_index.py",
            "file": "simulation/resilience_index.py",
            "expected_affected": [
                "simulation/resilience_index.py",
                "simulation/state_engine.py",
                "backend/app/api/simulation.py",
                "tests/test_resilience_index.py"
            ]
        },
        {
            "id": "SCEN-07",
            "tier": "Service",
            "node_id": "file:simulation/state_engine.py",
            "name": "simulation/state_engine.py",
            "file": "simulation/state_engine.py",
            "expected_affected": [
                "simulation/state_engine.py",
                "simulation/cascade_engine.py",
                "backend/app/api/simulation.py",
                "backend/app/api/websocket.py",
                "tests/test_state_engine.py"
            ]
        },
        {
            "id": "SCEN-08",
            "tier": "Service",
            "node_id": "file:graph/traversals.py",
            "name": "graph/traversals.py",
            "file": "graph/traversals.py",
            "expected_affected": [
                "graph/traversals.py",
                "simulation/cascade_engine.py",
                "simulation/risk_engine.py",
                "tests/test_cascade_engine.py"
            ]
        },
        {
            "id": "SCEN-09",
            "tier": "Service",
            "node_id": "file:backend/app/services/hospital_service.py",
            "name": "backend/app/services/hospital_service.py",
            "file": "backend/app/services/hospital_service.py",
            "expected_affected": [
                "backend/app/services/hospital_service.py",
                "backend/app/api/hospital.py",
                "backend/app/main.py",
                "tests/test_api_endpoints.py"
            ]
        },
        {
            "id": "SCEN-10",
            "tier": "Service",
            "node_id": "file:models/infrastructure.py",
            "name": "models/infrastructure.py",
            "file": "models/infrastructure.py",
            "expected_affected": [
                "models/infrastructure.py",
                "graph/topology_builder.py",
                "simulation/cascade_engine.py",
                "tests/test_topology_graph.py"
            ]
        },

        # --- 5 CORE SCENARIOS ---
        {
            "id": "SCEN-11",
            "tier": "Core",
            "node_id": "file:simulation/cascade_engine.py",
            "name": "simulation/cascade_engine.py",
            "file": "simulation/cascade_engine.py",
            "expected_affected": [
                "simulation/cascade_engine.py",
                "simulation/what_if_engine.py",
                "simulation/state_engine.py",
                "backend/app/api/simulation.py",
                "backend/app/interfaces/contracts.py",
                "tests/test_cascade_engine.py",
                "tests/test_scenarios.py"
            ]
        },
        {
            "id": "SCEN-12",
            "tier": "Core",
            "node_id": "file:graph/topology_builder.py",
            "name": "graph/topology_builder.py",
            "file": "graph/topology_builder.py",
            "expected_affected": [
                "graph/topology_builder.py",
                "graph/traversals.py",
                "simulation/cascade_engine.py",
                "simulation/risk_engine.py",
                "backend/app/api/graph.py",
                "tests/test_topology_graph.py"
            ]
        },
        {
            "id": "SCEN-13",
            "tier": "Core",
            "node_id": "file:backend/app/api/simulation.py",
            "name": "backend/app/api/simulation.py",
            "file": "backend/app/api/simulation.py",
            "expected_affected": [
                "backend/app/api/simulation.py",
                "backend/app/api/hospital.py",
                "backend/app/api/websocket.py",
                "backend/app/main.py",
                "simulation/state_engine.py",
                "tests/test_api_endpoints.py",
                "tests/test_websocket.py"
            ]
        },
        {
            "id": "SCEN-14",
            "tier": "Core",
            "node_id": "file:database/session.py",
            "name": "database/session.py",
            "file": "database/session.py",
            "expected_affected": [
                "database/session.py",
                "database/base.py",
                "backend/app/services/simulation_persistence.py",
                "backend/app/services/telemetry_persistence.py",
                "backend/app/main.py"
            ]
        },
        {
            "id": "SCEN-15",
            "tier": "Core",
            "node_id": "file:models/service.py",
            "name": "models/service.py",
            "file": "models/service.py",
            "expected_affected": [
                "models/service.py",
                "models/infrastructure.py",
                "graph/topology_builder.py",
                "simulation/cascade_engine.py",
                "simulation/resilience_index.py",
                "backend/app/api/hospital.py",
                "tests/test_topology_graph.py"
            ]
        }
    ]


def evaluate_system_configuration(
    system_name: str,
    include_temporal: bool,
    include_tests: bool,
    scenarios: List[Dict[str, Any]],
    repo_path: str,
    impact_engine: ChangeImpactEngine,
    test_engine: TestIntelligenceEngine,
) -> Dict[str, Any]:
    """
    Evaluates a specific system configuration across the 15 scenarios.
    Applies exact path matching and target inclusion.
    """
    scenario_evaluations = []
    prediction_audit_records = []

    for sc in scenarios:
        sc_id = sc["id"]
        tier = sc["tier"]
        target_rel = sc["file"]

        target = ChangeTarget(
            node_id=sc["node_id"],
            name=sc["name"],
            entity_type="file",
            file_path=os.path.join(repo_path, sc["file"]),
            relative_path=sc["file"]
        )

        blast = impact_engine.analyze_blast_radius(target, include_temporal=include_temporal)

        # 1. Code predictions: Target file is explicitly included as the primary changed artifact
        code_preds_set: Set[str] = {normalize_canonical_path(target_rel, repo_path)}
        for n in blast.impacted_nodes:
            if n.file_path:
                p_norm = normalize_canonical_path(n.file_path, repo_path)
                if not is_test_file(p_norm):
                    code_preds_set.add(p_norm)

        # 2. Test recommendations: Statically prioritized candidates
        test_preds_set: Set[str] = set()
        test_audit_meta: Dict[str, Dict[str, Any]] = {}
        if include_tests:
            test_rep = test_engine.analyze_tests(target, blast)
            for t_rec in test_rep.recommendations:
                if t_rec.test_file:
                    t_norm = normalize_canonical_path(t_rec.test_file, repo_path)
                    test_preds_set.add(t_norm)
                    test_audit_meta[t_norm] = {
                        "rank_score": t_rec.rank_score,
                        "tier": t_rec.tier,
                        "evidence_type": t_rec.evidence_type,
                        "description": t_rec.description
                    }

        all_preds = code_preds_set | test_preds_set

        # Ground truth
        gt_code = {normalize_canonical_path(g, repo_path) for g in sc["expected_affected"] if not is_test_file(g)}
        gt_test = {normalize_canonical_path(g, repo_path) for g in sc["expected_affected"] if is_test_file(g)}
        all_gt = gt_code | gt_test

        # Exact matching
        tp_code_set = code_preds_set & gt_code
        tp_test_set = test_preds_set & gt_test
        tp_set = all_preds & all_gt
        fp_set = all_preds - all_gt
        fn_set = all_gt - all_preds

        tp = len(tp_set)
        fp = len(fp_set)
        fn = len(fn_set)

        tp_code = len(tp_code_set)
        fp_code = len(code_preds_set - gt_code)
        fn_code = len(gt_code - code_preds_set)

        tp_test = len(tp_test_set)
        fp_test = len(test_preds_set - gt_test)
        fn_test = len(gt_test - test_preds_set)

        # Metrics (exact 0.0 for zero denominators)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        p_code = tp_code / len(code_preds_set) if len(code_preds_set) > 0 else 0.0
        r_code = tp_code / len(gt_code) if len(gt_code) > 0 else 0.0
        f1_code = 2 * p_code * r_code / (p_code + r_code) if (p_code + r_code) > 0 else 0.0

        p_test = tp_test / len(test_preds_set) if len(test_preds_set) > 0 else 0.0
        r_test = tp_test / len(gt_test) if len(gt_test) > 0 else 0.0
        f1_test = 2 * p_test * r_test / (p_test + r_test) if (p_test + r_test) > 0 else 0.0

        scenario_evaluations.append({
            "scenario_id": sc_id,
            "tier": tier,
            "target": target_rel,
            "total_predictions": len(all_preds),
            "code_predictions": len(code_preds_set),
            "test_predictions": len(test_preds_set),
            "total_ground_truth": len(all_gt),
            "code_ground_truth": len(gt_code),
            "test_ground_truth": len(gt_test),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "tp_code": tp_code,
            "fp_code": fp_code,
            "fn_code": fn_code,
            "precision_code": p_code,
            "recall_code": r_code,
            "f1_code": f1_code,
            "tp_test": tp_test,
            "fp_test": fp_test,
            "fn_test": fn_test,
            "precision_test": p_test,
            "recall_test": r_test,
            "f1_test": f1_test,
            "predicted_paths": sorted(list(all_preds)),
            "ground_truth_paths": sorted(list(all_gt)),
            "true_positive_paths": sorted(list(tp_set)),
            "false_positive_paths": sorted(list(fp_set)),
            "false_negative_paths": sorted(list(fn_set)),
        })

        for p_path in sorted(list(all_preds)):
            is_test = is_test_file(p_path)
            is_tp = p_path in all_gt
            evidence = "target_self" if p_path == normalize_canonical_path(target_rel, repo_path) else ("test_recommendation" if is_test else "blast_radius_dependency")
            score_meta = test_audit_meta.get(p_path, {})
            prediction_audit_records.append({
                "scenario_id": sc_id,
                "tier": tier,
                "target": target_rel,
                "predicted_path": p_path,
                "category": "test" if is_test else "code",
                "evidence_source": evidence,
                "matched_ground_truth": is_tp,
                "rank_score": score_meta.get("rank_score", 1.0 if not is_test else 0.0),
                "evidence_type": score_meta.get("evidence_type", "STRUCTURAL" if not is_test else "HEURISTIC"),
            })

    # Global aggregations
    tot_tp = sum(r["tp"] for r in scenario_evaluations)
    tot_fp = sum(r["fp"] for r in scenario_evaluations)
    tot_fn = sum(r["fn"] for r in scenario_evaluations)
    tot_preds = sum(r["total_predictions"] for r in scenario_evaluations)
    tot_gt = sum(r["total_ground_truth"] for r in scenario_evaluations)

    tot_tp_code = sum(r["tp_code"] for r in scenario_evaluations)
    tot_fp_code = sum(r["fp_code"] for r in scenario_evaluations)
    tot_fn_code = sum(r["fn_code"] for r in scenario_evaluations)
    tot_preds_code = sum(r["code_predictions"] for r in scenario_evaluations)
    tot_gt_code = sum(r["code_ground_truth"] for r in scenario_evaluations)

    tot_tp_test = sum(r["tp_test"] for r in scenario_evaluations)
    tot_fp_test = sum(r["fp_test"] for r in scenario_evaluations)
    tot_fn_test = sum(r["fn_test"] for r in scenario_evaluations)
    tot_preds_test = sum(r["test_predictions"] for r in scenario_evaluations)
    tot_gt_test = sum(r["test_ground_truth"] for r in scenario_evaluations)

    micro_p = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) > 0 else 0.0
    micro_r = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) > 0 else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) > 0 else 0.0

    macro_p = sum(r["precision"] for r in scenario_evaluations) / len(scenario_evaluations)
    macro_r = sum(r["recall"] for r in scenario_evaluations) / len(scenario_evaluations)
    macro_f1 = sum(r["f1"] for r in scenario_evaluations) / len(scenario_evaluations)

    micro_p_code = tot_tp_code / tot_preds_code if tot_preds_code > 0 else 0.0
    micro_r_code = tot_tp_code / tot_gt_code if tot_gt_code > 0 else 0.0
    micro_f1_code = 2 * micro_p_code * micro_r_code / (micro_p_code + micro_r_code) if (micro_p_code + micro_r_code) > 0 else 0.0

    macro_p_code = sum(r["precision_code"] for r in scenario_evaluations) / len(scenario_evaluations)
    macro_r_code = sum(r["recall_code"] for r in scenario_evaluations) / len(scenario_evaluations)
    macro_f1_code = sum(r["f1_code"] for r in scenario_evaluations) / len(scenario_evaluations)

    micro_p_test = tot_tp_test / tot_preds_test if tot_preds_test > 0 else 0.0
    micro_r_test = tot_tp_test / tot_gt_test if tot_gt_test > 0 else 0.0
    micro_f1_test = 2 * micro_p_test * micro_r_test / (micro_p_test + micro_r_test) if (micro_p_test + micro_r_test) > 0 else 0.0

    macro_p_test = sum(r["precision_test"] for r in scenario_evaluations) / len(scenario_evaluations)
    macro_r_test = sum(r["recall_test"] for r in scenario_evaluations) / len(scenario_evaluations)
    macro_f1_test = sum(r["f1_test"] for r in scenario_evaluations) / len(scenario_evaluations)

    # Per-tier performance breakdown
    tier_metrics = {}
    for tier_name in ["Leaf", "Service", "Core"]:
        t_scens = [r for r in scenario_evaluations if r["tier"] == tier_name]
        t_tp = sum(r["tp"] for r in t_scens)
        t_fp = sum(r["fp"] for r in t_scens)
        t_fn = sum(r["fn"] for r in t_scens)
        t_mic_p = t_tp / (t_tp + t_fp) if (t_tp + t_fp) > 0 else 0.0
        t_mic_r = t_tp / (t_tp + t_fn) if (t_tp + t_fn) > 0 else 0.0
        t_mic_f1 = 2 * t_mic_p * t_mic_r / (t_mic_p + t_mic_r) if (t_mic_p + t_mic_r) > 0 else 0.0
        t_mac_p = sum(r["precision"] for r in t_scens) / len(t_scens)
        t_mac_r = sum(r["recall"] for r in t_scens) / len(t_scens)
        t_mac_f1 = sum(r["f1"] for r in t_scens) / len(t_scens)
        tier_metrics[tier_name] = {
            "scenarios_count": len(t_scens),
            "tp": t_tp, "fp": t_fp, "fn": t_fn,
            "micro_precision": t_mic_p, "micro_recall": t_mic_r, "micro_f1": t_mic_f1,
            "macro_precision": t_mac_p, "macro_recall": t_mac_r, "macro_f1": t_mac_f1,
        }

    return {
        "system_name": system_name,
        "include_temporal": include_temporal,
        "include_tests": include_tests,
        "total_scenarios": len(scenario_evaluations),
        "total_predictions": tot_preds,
        "total_ground_truth": tot_gt,
        "true_positives": tot_tp,
        "false_positives": tot_fp,
        "false_negatives": tot_fn,
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "code_components": {
            "total_predictions": tot_preds_code,
            "total_ground_truth": tot_gt_code,
            "true_positives": tot_tp_code,
            "false_positives": tot_fp_code,
            "false_negatives": tot_fn_code,
            "micro_precision": micro_p_code,
            "micro_recall": micro_r_code,
            "micro_f1": micro_f1_code,
            "macro_precision": macro_p_code,
            "macro_recall": macro_r_code,
            "macro_f1": macro_f1_code,
        },
        "regression_tests": {
            "total_predictions": tot_preds_test,
            "total_ground_truth": tot_gt_test,
            "true_positives": tot_tp_test,
            "false_positives": tot_fp_test,
            "false_negatives": tot_fn_test,
            "micro_precision": micro_p_test,
            "micro_recall": micro_r_test,
            "micro_f1": micro_f1_test,
            "macro_precision": macro_p_test,
            "macro_recall": macro_r_test,
            "macro_f1": macro_f1_test,
        },
        "performance_by_tier": tier_metrics,
        "scenario_evaluations": scenario_evaluations,
        "prediction_audit_records": prediction_audit_records,
    }


def run_experiment_e3(repo_path: str = "eval_repos/ResilienceOS") -> Dict[str, Any]:
    start_time = datetime.now(timezone.utc)
    print("=" * 80)
    print("EXPERIMENT E3: REPRODUCIBLE MULTI-SIGNAL IMPACT SCORING (RQ3)")
    print(f"Target Repository: {repo_path}")
    print(f"Start Time: {start_time.isoformat()}")
    print("=" * 80)

    # 1. Record Git commit hash
    git_commit_hash = "UNKNOWN"
    try:
        git_commit_hash = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception as e:
        git_commit_hash = f"git_error: {e}"
    print(f"Repository Git Commit Hash: {git_commit_hash}")

    # 2. Verify all scenario and ground truth paths on disk
    scenarios = define_controlled_scenarios()
    print(f"Loaded {len(scenarios)} controlled change scenarios.")
    missing_paths = []
    for sc in scenarios:
        t_path = os.path.join(repo_path, sc["file"])
        if not os.path.exists(t_path):
            missing_paths.append((sc["id"], "target", sc["file"]))
        for g in sc["expected_affected"]:
            g_path = os.path.join(repo_path, g)
            if not os.path.exists(g_path):
                missing_paths.append((sc["id"], "ground_truth", g))

    if missing_paths:
        print(f"ERROR: Found {len(missing_paths)} missing paths on disk!")
        for m in missing_paths:
            print(f"  Missing: {m}")
        raise FileNotFoundError(f"Verification failed: {len(missing_paths)} files missing.")
    else:
        print("Path Verification Passed: All 34 unique scenario targets and ground-truth files exist on disk.")

    # 3. Load repository and build AST graph
    loader = RepositoryLoader()
    repo = loader.load_repository(repo_path)
    parser = PythonParser()
    parsed_files = {sf.relative_path.replace("\\", "/"): parser.parse(sf) for sf in repo.files if sf.is_python}

    builder = KnowledgeGraphBuilder()
    graph = builder.build(repo, parsed_files)
    print(f"Initial Knowledge Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")

    # 4. Mine Git commit history and logical couplings
    client = GitClient(repo_path)
    miner = GitMiner(client)
    commits = miner.mine_commits(max_commits=500)
    churn_analyzer = CodeChurnAnalyzer()
    churn_summary = churn_analyzer.analyze(commits)
    coupling_analyzer = LogicalCouplingAnalyzer(min_support=2, min_confidence=0.3)
    coupling_res = coupling_analyzer.analyze(commits)
    print(f"Git Mining: {len(commits)} commits mined. Discovered {len(coupling_res.couplings)} logical couplings.")

    # 5. Materialize temporal intelligence into graph
    builder.materialize_temporal_graph(commits, coupling_res.couplings)
    print(f"Materialized Knowledge Graph with Temporal Edges: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")

    # 6. Initialize impact and test intelligence engines
    impact_engine = ChangeImpactEngine(graph=graph, coupling_analyzer=coupling_analyzer)
    test_engine = TestIntelligenceEngine(graph=graph, coupling_analyzer=coupling_analyzer, repo=repo)
    scorer = MultiSignalImpactScorer(
        churn_analyzer=churn_analyzer,
        coupling_analyzer=coupling_analyzer,
        has_git=True,
        total_repo_commits=len(commits),
        has_tests=True
    )

    # 7. Evaluate Systems:
    # System 1: Baseline A (Genuine Structural Reachability Only, with target file, no temporal, no tests)
    # System 2: Baseline B (Structural Reachability + 1-hop Temporal Co-change, no tests)
    # System 3: CodeMind Minus Temporal Coupling (Structural Reachability + Test Intelligence, no temporal)
    # System 4: CodeMind Full (Structural Reachability + 1-hop Temporal Co-change + Test Intelligence)
    systems_config = [
        ("Baseline_A_StructuralOnly", False, False),
        ("Baseline_B_StructuralPlusTemporal", True, False),
        ("CodeMind_Minus_Temporal_Coupling", False, True),
        ("CodeMind_Full_MultiSignal", True, True),
    ]

    evaluated_systems: Dict[str, Any] = {}
    for sys_name, inc_temp, inc_test in systems_config:
        print(f"Evaluating {sys_name} (Temporal={inc_temp}, Tests={inc_test})...")
        res = evaluate_system_configuration(
            system_name=sys_name,
            include_temporal=inc_temp,
            include_tests=inc_test,
            scenarios=scenarios,
            repo_path=repo_path,
            impact_engine=impact_engine,
            test_engine=test_engine,
        )
        evaluated_systems[sys_name] = res

    # 8. Compute Multi-Signal Target Risk Reports for all 15 scenarios
    scorer_reports = []
    for sc in scenarios:
        target = ChangeTarget(
            node_id=sc["node_id"],
            name=sc["name"],
            entity_type="file",
            file_path=os.path.join(repo_path, sc["file"]),
            relative_path=sc["file"]
        )
        blast = impact_engine.analyze_blast_radius(target, include_temporal=True)
        centrality = impact_engine.compute_centrality(target.node_id)
        test_rep = test_engine.analyze_tests(target, blast)
        imp_rep = scorer.compute_impact(target, blast, centrality, test_rep)

        scorer_reports.append({
            "scenario_id": sc["id"],
            "tier": sc["tier"],
            "target": sc["file"],
            "composite_score": imp_rep.composite_score,
            "risk_level": imp_rep.risk_level,
            "confidence": imp_rep.confidence,
            "confidence_level": imp_rep.confidence_level,
            "signals": {k: v.to_dict() for k, v in imp_rep.signals.items()},
            "diagnostics": imp_rep.diagnostics,
        })

    # 9. Output Directory Setup
    out_dir = Path("research_experiments/results/rq3_final")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 10. Generate Artifact 1: rq3_final_results.json
    end_time = datetime.now(timezone.utc)
    final_results_payload = {
        "metadata": {
            "experiment": "E3_Multi_Signal_Impact_Scoring",
            "research_question": "RQ3",
            "repository": repo_path,
            "git_commit_hash": git_commit_hash,
            "execution_start": start_time.isoformat(),
            "execution_end": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "total_scenarios_evaluated": len(scenarios),
            "benchmark_instances": {
                "total_ground_truth": 64,
                "code_components": 52,
                "regression_tests": 12
            },
            "path_matching_protocol": "canonical_normalized_exact_match",
            "target_inclusion_rule": "changed_target_explicitly_included_in_component_predictions"
        },
        "systems": {
            name: {k: v for k, v in data.items() if k not in ("scenario_evaluations", "prediction_audit_records")}
            for name, data in evaluated_systems.items()
        },
        "per_scenario_evaluations": {
            name: data["scenario_evaluations"] for name, data in evaluated_systems.items()
        },
        "scorer_reports": scorer_reports,
    }

    with open(out_dir / "rq3_final_results.json", "w", encoding="utf-8") as f:
        json.dump(final_results_payload, f, indent=2)

    # Also save backward-compatible e3_results.json in parent results directory
    e3_compat = {
        "experiment": "E3_Multi_Signal_Impact_Scoring",
        "rq_tested": "RQ3",
        "total_scenarios": len(scenarios),
        "systems": {
            "Baseline_A_DependencyOnly": {
                "precision": evaluated_systems["Baseline_A_StructuralOnly"]["macro_precision"],
                "recall": evaluated_systems["Baseline_A_StructuralOnly"]["macro_recall"],
                "f1": evaluated_systems["Baseline_A_StructuralOnly"]["macro_f1"],
                "micro_precision": evaluated_systems["Baseline_A_StructuralOnly"]["micro_precision"],
                "micro_recall": evaluated_systems["Baseline_A_StructuralOnly"]["micro_recall"],
                "micro_f1": evaluated_systems["Baseline_A_StructuralOnly"]["micro_f1"]
            },
            "Baseline_B_StructuralPlusTemporal": {
                "precision": evaluated_systems["Baseline_B_StructuralPlusTemporal"]["macro_precision"],
                "recall": evaluated_systems["Baseline_B_StructuralPlusTemporal"]["macro_recall"],
                "f1": evaluated_systems["Baseline_B_StructuralPlusTemporal"]["macro_f1"],
                "micro_precision": evaluated_systems["Baseline_B_StructuralPlusTemporal"]["micro_precision"],
                "micro_recall": evaluated_systems["Baseline_B_StructuralPlusTemporal"]["micro_recall"],
                "micro_f1": evaluated_systems["Baseline_B_StructuralPlusTemporal"]["micro_f1"]
            },
            "CodeMind_Full_MultiSignal": {
                "precision": evaluated_systems["CodeMind_Full_MultiSignal"]["macro_precision"],
                "recall": evaluated_systems["CodeMind_Full_MultiSignal"]["macro_recall"],
                "f1": evaluated_systems["CodeMind_Full_MultiSignal"]["macro_f1"],
                "micro_precision": evaluated_systems["CodeMind_Full_MultiSignal"]["micro_precision"],
                "micro_recall": evaluated_systems["CodeMind_Full_MultiSignal"]["micro_recall"],
                "micro_f1": evaluated_systems["CodeMind_Full_MultiSignal"]["micro_f1"]
            }
        },
        "performance_by_tier": evaluated_systems["CodeMind_Full_MultiSignal"]["performance_by_tier"]
    }
    with open(Path("research_experiments/results") / "e3_results.json", "w", encoding="utf-8") as f:
        json.dump(e3_compat, f, indent=2)

    # 11. Generate Artifact 2: rq3_final_summary.csv
    csv_file = out_dir / "rq3_final_summary.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scenario_ID", "Tier", "Target_File", "System_Name",
            "Total_Predictions", "Total_GT", "TP", "FP", "FN", "Precision", "Recall", "F1",
            "Code_Predictions", "Code_GT", "Code_TP", "Code_FP", "Code_FN", "Code_Precision", "Code_Recall", "Code_F1",
            "Test_Predictions", "Test_GT", "Test_TP", "Test_FP", "Test_FN", "Test_Precision", "Test_Recall", "Test_F1"
        ])
        for sys_name, s_data in evaluated_systems.items():
            for r in s_data["scenario_evaluations"]:
                writer.writerow([
                    r["scenario_id"], r["tier"], r["target"], sys_name,
                    r["total_predictions"], r["total_ground_truth"], r["tp"], r["fp"], r["fn"],
                    round(r["precision"], 4), round(r["recall"], 4), round(r["f1"], 4),
                    r["code_predictions"], r["code_ground_truth"], r["tp_code"], r["fp_code"], r["fn_code"],
                    round(r["precision_code"], 4), round(r["recall_code"], 4), round(r["f1_code"], 4),
                    r["test_predictions"], r["test_ground_truth"], r["tp_test"], r["fp_test"], r["fn_test"],
                    round(r["precision_test"], 4), round(r["recall_test"], 4), round(r["f1_test"], 4)
                ])

    # 12. Generate Artifact 3: rq3_prediction_audit.json
    audit_file = out_dir / "rq3_prediction_audit.json"
    audit_data = {
        name: data["prediction_audit_records"] for name, data in evaluated_systems.items()
    }
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)

    # 13. Generate Artifact 5: rq3_execution_log.txt
    log_file = out_dir / "rq3_execution_log.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("RQ3 EXPERIMENT EXECUTION LOG\n")
        f.write(f"Timestamp: {start_time.isoformat()}\n")
        f.write(f"Repository: {repo_path}\n")
        f.write(f"Git Commit Hash: {git_commit_hash}\n")
        f.write(f"Python Version: {sys.version}\n")
        f.write("Status: Completed successfully without errors.\n")
        f.write("=" * 80 + "\n\n")
        for sys_name, res in evaluated_systems.items():
            f.write(f"System: {sys_name}\n")
            f.write(f"  Total Predictions: {res['total_predictions']}, TP: {res['true_positives']}, FP: {res['false_positives']}, FN: {res['false_negatives']}\n")
            f.write(f"  Micro Metrics: Precision={res['micro_precision']:.4f}, Recall={res['micro_recall']:.4f}, F1={res['micro_f1']:.4f}\n")
            f.write(f"  Macro Metrics: Precision={res['macro_precision']:.4f}, Recall={res['macro_recall']:.4f}, F1={res['macro_f1']:.4f}\n")
            f.write(f"  Code Components: Micro P={res['code_components']['micro_precision']:.4f}, R={res['code_components']['micro_recall']:.4f} ({res['code_components']['true_positives']}/{res['code_components']['total_ground_truth']}), F1={res['code_components']['micro_f1']:.4f}\n")
            f.write(f"  Regression Tests: Micro P={res['regression_tests']['micro_precision']:.4f}, R={res['regression_tests']['micro_recall']:.4f} ({res['regression_tests']['true_positives']}/{res['regression_tests']['total_ground_truth']}), F1={res['regression_tests']['micro_f1']:.4f}\n\n")

    # 14. Generate Artifact 6: rq3_paper_tables.md
    tables_file = out_dir / "rq3_paper_tables.md"
    full_sys = evaluated_systems["CodeMind_Full_MultiSignal"]
    base_a = evaluated_systems["Baseline_A_StructuralOnly"]
    base_b = evaluated_systems["Baseline_B_StructuralPlusTemporal"]
    abl_temp = evaluated_systems["CodeMind_Minus_Temporal_Coupling"]

    with open(tables_file, "w", encoding="utf-8") as f:
        f.write("# RQ3 Publication-Ready Tables\n\n")
        f.write("## Table 1: Comparative Evaluation of CodeMind against Baselines on RQ3 (N=15 Scenarios, 64 GT Instances)\n\n")
        f.write("| System Configuration | Preds | TP | FP | FN | Micro Prec | Micro Rec | Micro F1 | Macro Prec | Macro Rec | Macro F1 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        f.write(f"| Baseline A (Structural Only) | {base_a['total_predictions']} | {base_a['true_positives']} | {base_a['false_positives']} | {base_a['false_negatives']} | {base_a['micro_precision']*100:.1f}\\% | {base_a['micro_recall']*100:.1f}\\% | {base_a['micro_f1']:.4f} | {base_a['macro_precision']*100:.1f}\\% | {base_a['macro_recall']*100:.1f}\\% | {base_a['macro_f1']:.4f} |\n")
        f.write(f"| Baseline B (Structural + Temporal) | {base_b['total_predictions']} | {base_b['true_positives']} | {base_b['false_positives']} | {base_b['false_negatives']} | {base_b['micro_precision']*100:.1f}\\% | {base_b['micro_recall']*100:.1f}\\% | {base_b['micro_f1']:.4f} | {base_b['macro_precision']*100:.1f}\\% | {base_b['macro_recall']*100:.1f}\\% | {base_b['macro_f1']:.4f} |\n")
        f.write(f"| **CodeMind (Full Multi-Signal)** | **{full_sys['total_predictions']}** | **{full_sys['true_positives']}** | **{full_sys['false_positives']}** | **{full_sys['false_negatives']}** | **{full_sys['micro_precision']*100:.1f}\\%** | **{full_sys['micro_recall']*100:.1f}\\%** | **{full_sys['micro_f1']:.4f}** | **{full_sys['macro_precision']*100:.1f}\\%** | **{full_sys['macro_recall']*100:.1f}\\%** | **{full_sys['macro_f1']:.4f}** |\n\n")

        f.write("## Table 2: Category-Specific Decomposition: Code Components vs. Regression Tests\n\n")
        f.write("| System | Code Preds | Code GT | Code TP | Code Rec | Code Prec | Test Preds | Test GT | Test TP | Test Rec | Test Prec |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        f.write(f"| Baseline A | {base_a['code_components']['total_predictions']} | 52 | {base_a['code_components']['true_positives']} | {base_a['code_components']['micro_recall']*100:.1f}\\% | {base_a['code_components']['micro_precision']*100:.1f}\\% | 0 | 12 | 0 | 0.0\\% | N/A |\n")
        f.write(f"| Baseline B | {base_b['code_components']['total_predictions']} | 52 | {base_b['code_components']['true_positives']} | {base_b['code_components']['micro_recall']*100:.1f}\\% | {base_b['code_components']['micro_precision']*100:.1f}\\% | 0 | 12 | 0 | 0.0\\% | N/A |\n")
        f.write(f"| Minus Temporal | {abl_temp['code_components']['total_predictions']} | 52 | {abl_temp['code_components']['true_positives']} | {abl_temp['code_components']['micro_recall']*100:.1f}\\% | {abl_temp['code_components']['micro_precision']*100:.1f}\\% | {abl_temp['regression_tests']['total_predictions']} | 12 | {abl_temp['regression_tests']['true_positives']} | {abl_temp['regression_tests']['micro_recall']*100:.1f}\\% | {abl_temp['regression_tests']['micro_precision']*100:.1f}\\% |\n")
        f.write(f"| **CodeMind Full** | **{full_sys['code_components']['total_predictions']}** | **52** | **{full_sys['code_components']['true_positives']}** | **{full_sys['code_components']['micro_recall']*100:.1f}\\%** | **{full_sys['code_components']['micro_precision']*100:.1f}\\%** | **{full_sys['regression_tests']['total_predictions']}** | **12** | **{full_sys['regression_tests']['true_positives']}** | **{full_sys['regression_tests']['micro_recall']*100:.1f}\\%** | **{full_sys['regression_tests']['micro_precision']*100:.1f}\\%** |\n\n")

        f.write("## Table 3: Genuinely Isolated Ablation Study (All Executed on Benchmark)\n\n")
        f.write("| Experimental Configuration | Predictions | TP | FP | FN | Micro Recall | Micro F1 | Macro F1 | Delta F1 (Macro) |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        f.write(f"| Full System | {full_sys['total_predictions']} | {full_sys['true_positives']} | {full_sys['false_positives']} | {full_sys['false_negatives']} | {full_sys['micro_recall']*100:.1f}\\% | {full_sys['micro_f1']:.4f} | {full_sys['macro_f1']:.4f} | Ref |\n")
        f.write(f"| Minus Temporal Coupling | {abl_temp['total_predictions']} | {abl_temp['true_positives']} | {abl_temp['false_positives']} | {abl_temp['false_negatives']} | {abl_temp['micro_recall']*100:.1f}\\% | {abl_temp['micro_f1']:.4f} | {abl_temp['macro_f1']:.4f} | {abl_temp['macro_f1'] - full_sys['macro_f1']:+.4f} |\n")
        f.write(f"| Minus Test Intelligence (= Baseline B) | {base_b['total_predictions']} | {base_b['true_positives']} | {base_b['false_positives']} | {base_b['false_negatives']} | {base_b['micro_recall']*100:.1f}\\% | {base_b['micro_f1']:.4f} | {base_b['macro_f1']:.4f} | {base_b['macro_f1'] - full_sys['macro_f1']:+.4f} |\n")
        f.write(f"| Structural Only (= Baseline A) | {base_a['total_predictions']} | {base_a['true_positives']} | {base_a['false_positives']} | {base_a['false_negatives']} | {base_a['micro_recall']*100:.1f}\\% | {base_a['micro_f1']:.4f} | {base_a['macro_f1']:.4f} | {base_a['macro_f1'] - full_sys['macro_f1']:+.4f} |\n\n")

        f.write("## Table 4: Descriptive Summary of Multi-Signal Impact Scorer Across Scenarios\n\n")
        f.write("| Scenario ID | Tier | Target File | S1 (Reach) | S2 (Cent) | S3 (Churn) | S4 (Coup) | S5 (Test) | S6 (CCN) | Composite Score | Risk Level | Confidence |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for sc_rep in scorer_reports:
            sig = sc_rep["signals"]
            f.write(f"| {sc_rep['scenario_id']} | {sc_rep['tier']} | `{sc_rep['target']}` | {sig['structural_reachability']['normalized_score']:.2f} | {sig['graph_centrality']['normalized_score']:.2f} | {sig['historical_volatility']['normalized_score']:.2f} | {sig['logical_coupling']['normalized_score']:.2f} | {sig['test_exposure_risk']['normalized_score']:.2f} | {sig['cyclomatic_complexity']['normalized_score']:.2f} | **{sc_rep['composite_score']:.4f}** | {sc_rep['risk_level']} | {sc_rep['confidence']:.2f} |\n")

    # 15. Generate Artifact 4: rq3_methodology_report.md
    report_file = out_dir / "rq3_methodology_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# RQ3 Methodology and Reproducibility Audit Report\n\n")
        f.write("## 1. Benchmark Construction and Ground Truth\n")
        f.write("- **Repository**: `ResilienceOS` (Healthcare Infrastructure Resilience Simulation Engine, Python/FastAPI/SQLAlchemy).\n")
        f.write(f"- **Git Commit Hash**: `{git_commit_hash}`.\n")
        f.write("- **Benchmark Scope**: 15 controlled change scenarios stratified across 3 architectural tiers (5 Leaf, 5 Service, 5 Core).\n")
        f.write("- **Ground Truth Universe**: Exactly 64 scenario-target instances (52 code components, 12 regression test suites).\n")
        f.write("- **Independence Guarantee**: Ground truth targets were established by dynamic execution traces and manual commit inspection, independent of static heuristic mining.\n\n")
        f.write("## 2. Prediction Task and Target Inclusion\n")
        f.write("- **Task Definition**: Given a changed repository file $s$, predict the set of affected repository code components and relevant regression-test files.\n")
        f.write("- **Target Inclusion Rule**: The changed target file itself is explicitly included in the component prediction set because modifying a component inherently affects that component. This rule is applied uniformly across all evaluated systems.\n\n")
        f.write("## 3. Path Normalization and Exact Matching Protocol\n")
        f.write("- **No Substring Matching**: Substring matching (`p in g or g in p`) is strictly banned. Evaluation uses exact path equality (`p == g`) on canonical repository-relative paths.\n")
        f.write("- **Normalization**: Converts all path separators to `/`, strips absolute repository prefixes, trims `./`, and applies lowercase normalization for consistent cross-platform matching.\n")
        f.write("- **Deduplication**: Predictions are deduplicated within each scenario before evaluation.\n\n")
        f.write("## 4. Compared Systems and Baselines\n")
        f.write("1. **Baseline A (Structural Only)**: Static AST reverse dependency traversal (CALLS, INHERITS, IMPORTS) with target file included. No temporal co-change, no test recommendations.\n")
        f.write("2. **Baseline B (Structural + Temporal)**: Static AST reverse dependency traversal + strictly 1-hop temporal co-change expansion mined from Git history. No test recommendations.\n")
        f.write("3. **CodeMind Minus Temporal Coupling**: Static AST reverse dependency traversal + test intelligence recommendations. No temporal co-change.\n")
        f.write("4. **CodeMind Full**: Static AST reverse dependency traversal + 1-hop temporal co-change + test intelligence recommendations.\n\n")
        f.write("## 5. Ablations and Multi-Signal Target Risk Scorer\n")
        f.write("- **Synthetic Multiplier Removal**: All synthetic metric multipliers (e.g., `* 0.92`, `* 0.95`) have been completely deleted. All ablations represent actual executions of the software system.\n")
        f.write("- **Scorer Decoupling**: The six-signal impact scorer computes target-level risk $S_{\\text{impact}}(s) \\in [0, 1]$ and signal contributions. It is descriptively reported and strictly decoupled from candidate set prediction.\\n\\n")
        f.write("## 6. Reproducibility Statement\n")
        f.write("The entire benchmark can be reproduced with a single command:\n")
        f.write("```bash\npython research_experiments/e3_impact_scoring.py\n```\n")
        f.write("All execution logs, per-scenario predictions, ground-truth paths, and test metrics are persisted in `research_experiments/results/rq3_final/`.\n")

    print("\n" + "=" * 80)
    print("EXPERIMENT E3 COMPLETED SUCCESSFULLY")
    print(f"Results saved to {out_dir}/")
    print(f"  - rq3_final_results.json")
    print(f"  - rq3_final_summary.csv")
    print(f"  - rq3_prediction_audit.json")
    print(f"  - rq3_methodology_report.md")
    print(f"  - rq3_execution_log.txt")
    print(f"  - rq3_paper_tables.md")
    print("=" * 80)

    return final_results_payload


if __name__ == "__main__":
    run_experiment_e3()
