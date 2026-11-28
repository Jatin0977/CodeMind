"""
Automated unit and integration test suite for RQ3 reproducibility,
path normalization, exact matching, temporal coupling, scorer fields, and metric calculation.
"""

import os
import unittest
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import networkx as nx

from codemind.git.coupling import LogicalCoupling, LogicalCouplingAnalyzer
from codemind.git.models import CommitRecord, FileChange
from codemind.impact.models import ChangeTarget, ImpactAnalysisConfig, BlastRadiusNode, BlastRadiusReport
from codemind.impact.scorer import MultiSignalImpactScorer
from codemind.impact.engine import ChangeImpactEngine
from codemind.impact.test_intelligence import TestIntelligenceEngine
from codemind.graph.models import NodeType, EdgeType


def normalize_canonical_path(path: str, repo_root: str = "eval_repos/ResilienceOS") -> str:
    """Shared canonical path normalization helper for RQ3 evaluation."""
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
    # Handle Windows/POSIX repo root prefixes reliably across OS runners
    lower_norm = norm.lower()
    for prefix in ["eval_repos/resilienceos/", "eval_repos/resilienceos"]:
        idx = lower_norm.find(prefix)
        if idx != -1:
            norm = norm[idx + len(prefix):].lstrip("/")
            break
    while norm.startswith("./"):
        norm = norm[2:]
    return norm.strip("/").lower()


def is_test_file(path: str) -> bool:
    """Categorize path into test suite or code component."""
    p = path.lower()
    return p.startswith("tests/") or p.startswith("test/") or p.endswith("_test.py") or "/test_" in p or p.startswith("test_")


class TestRQ3Reproducibility(unittest.TestCase):

    def test_canonical_path_normalization(self):
        """Test that Windows separators, leading dots, and repo prefixes are normalized."""
        variants = [
            "F:\\COdemind\\eval_repos\\ResilienceOS\\simulation\\report_generator.py",
            "F:/COdemind/eval_repos/ResilienceOS/simulation/report_generator.py",
            "eval_repos/ResilienceOS/simulation/report_generator.py",
            "./simulation/report_generator.py",
            "simulation/report_generator.py",
        ]
        expected = "simulation/report_generator.py"
        for v in variants:
            self.assertEqual(normalize_canonical_path(v), expected)

    def test_category_separation(self):
        """Test strict category separation between code and test components."""
        self.assertTrue(is_test_file("tests/test_report_generator.py"))
        self.assertTrue(is_test_file("tests/test_websocket.py"))
        self.assertTrue(is_test_file("backend/tests/test_api.py"))
        self.assertFalse(is_test_file("simulation/report_generator.py"))
        self.assertFalse(is_test_file("backend/app/api/simulation.py"))
        self.assertFalse(is_test_file("models/api_responses.py"))

    def test_exact_path_matching_no_substring(self):
        """Verify that substring matching does NOT occur between distinct files."""
        preds = ["backend/app/api/simulation.py"]
        gt = ["backend/app/api/simulation_helper.py"]  # Substring should NOT match
        norm_preds = {normalize_canonical_path(p) for p in preds}
        norm_gt = {normalize_canonical_path(g) for g in gt}
        matched = norm_preds & norm_gt
        self.assertEqual(len(matched), 0, "Substring matching must not produce false positive")

        # Exact match must succeed
        gt_exact = ["backend/app/api/simulation.py"]
        norm_gt_exact = {normalize_canonical_path(g) for g in gt_exact}
        self.assertEqual(len(norm_preds & norm_gt_exact), 1)

    def test_deduplication_within_scenario(self):
        """Verify that predictions repeated within a scenario are counted exactly once."""
        raw_preds = [
            "simulation/report_generator.py",
            "simulation/report_generator.py",
            "./simulation/report_generator.py",
        ]
        norm_preds = {normalize_canonical_path(p) for p in raw_preds}
        self.assertEqual(len(norm_preds), 1)

    def test_target_inclusion_rule(self):
        """Verify that target file is explicitly included in the prediction set."""
        target_file = "simulation/report_generator.py"
        blast_nodes = []  # No reverse dependents
        predicted = {normalize_canonical_path(target_file)}
        for n in blast_nodes:
            predicted.add(normalize_canonical_path(n.file_path))
        self.assertIn("simulation/report_generator.py", predicted)

    def test_scorer_coupling_field_access(self):
        """Verify MultiSignalImpactScorer correctly accesses canonical_file_a / canonical_file_b."""
        coupling = LogicalCoupling(
            canonical_file_a="simulation/state_engine.py",
            canonical_file_b="backend/app/api/simulation.py",
            support_count=5,
            jaccard_similarity=0.60,
            confidence_a_to_b=0.80,
            confidence_b_to_a=0.75,
        )
        class DummyCouplingAnalyzer:
            couplings = [coupling]

        scorer = MultiSignalImpactScorer(
            coupling_analyzer=DummyCouplingAnalyzer(),
            has_git=True,
            total_repo_commits=50
        )
        target = ChangeTarget(
            node_id="file:simulation/state_engine.py",
            name="simulation/state_engine.py",
            entity_type="file",
            file_path="simulation/state_engine.py",
            relative_path="simulation/state_engine.py"
        )
        diagnostics = []
        sig = scorer._compute_s4_coupling(target, diagnostics)
        self.assertTrue(sig.available)
        self.assertAlmostEqual(sig.raw_value, 0.60 * 0.80, places=4)
        self.assertGreater(sig.normalized_score, 0.0)

        # Non-matching target must yield 0.0
        target_unrelated = ChangeTarget(
            node_id="file:unrelated/module.py",
            name="unrelated/module.py",
            entity_type="file",
            file_path="unrelated/module.py",
            relative_path="unrelated/module.py"
        )
        sig_unrelated = scorer._compute_s4_coupling(target_unrelated, diagnostics)
        self.assertEqual(sig_unrelated.raw_value, 0.0)

    def test_scorer_churn_field_access(self):
        """Verify MultiSignalImpactScorer correctly reads commit_frequency from summary."""
        @dataclass
        class DummyFileMetric:
            commit_frequency: int

        @dataclass
        class DummySummary:
            file_metrics: Dict[str, Any]

        class DummyChurnAnalyzer:
            summary = DummySummary(file_metrics={
                "simulation/state_engine.py": DummyFileMetric(commit_frequency=10)
            })

        scorer = MultiSignalImpactScorer(
            churn_analyzer=DummyChurnAnalyzer(),
            has_git=True,
            total_repo_commits=50
        )
        target = ChangeTarget(
            node_id="file:simulation/state_engine.py",
            name="simulation/state_engine.py",
            entity_type="file",
            file_path="simulation/state_engine.py",
            relative_path="simulation/state_engine.py"
        )
        diagnostics = []
        sig = scorer._compute_s3_volatility(target, diagnostics)
        self.assertTrue(sig.available)
        self.assertEqual(sig.raw_value, 10.0)
        self.assertAlmostEqual(sig.normalized_score, 10.0 / 20.0, places=4)

    def test_bidirectional_temporal_expansion(self):
        """Verify that temporal expansion discovers coupling partners regardless of edge direction."""
        g = nx.DiGraph()
        # file_a -> file_b (only one direction added)
        g.add_node("file:comp_a.py", node_type=NodeType.FILE, file_path="comp_a.py", name="comp_a.py")
        g.add_node("file:comp_b.py", node_type=NodeType.FILE, file_path="comp_b.py", name="comp_b.py")
        g.add_edge("file:comp_a.py", "file:comp_b.py", edge_type=EdgeType.CO_CHANGED_WITH, metadata={"is_temporal": True})

        engine = ChangeImpactEngine(graph=g)

        # Target A should discover B (successor)
        target_a = ChangeTarget(node_id="file:comp_a.py", name="comp_a.py", entity_type="file", file_path="comp_a.py")
        blast_a = engine.analyze_blast_radius(target_a, include_temporal=True)
        discovered_a = [n.node_id for n in blast_a.impacted_nodes if "TEMPORAL_CO_CHANGE" in n.tags]
        self.assertIn("file:comp_b.py", discovered_a)

        # Target B should discover A (predecessor)
        target_b = ChangeTarget(node_id="file:comp_b.py", name="comp_b.py", entity_type="file", file_path="comp_b.py")
        blast_b = engine.analyze_blast_radius(target_b, include_temporal=True)
        discovered_b = [n.node_id for n in blast_b.impacted_nodes if "TEMPORAL_CO_CHANGE" in n.tags]
        self.assertIn("file:comp_a.py", discovered_b)

    def test_dynamic_weight_renormalization(self):
        """Verify that when git and tests are absent, available weights renormalize to sum to 1.0."""
        scorer = MultiSignalImpactScorer(has_git=False, has_tests=False)
        target = ChangeTarget(
            node_id="file:core.py", name="core.py", entity_type="file", file_path="core.py",
            metadata={"complexity": 5}
        )
        blast = BlastRadiusReport(
            target=target, max_depth=3, total_impacted=5,
            impacted_nodes=[], impacted_edges=[]
        )
        centrality = engine = ChangeImpactEngine(nx.DiGraph()).compute_centrality("file:core.py")
        report = scorer.compute_impact(target, blast, centrality)

        # Available signals: reachability (w=0.30), centrality (w=0.20), test_exposure (w=0.10, max risk=1.0), complexity (w=0.10)
        # Git signals (volatility, coupling) are unavailable (weight=0.0)
        eff_weights = [s.effective_weight for s in report.signals.values() if s.available]
        self.assertAlmostEqual(sum(eff_weights), 1.0, places=3)
        self.assertEqual(report.signals["historical_volatility"].effective_weight, 0.0)
        self.assertEqual(report.signals["logical_coupling"].effective_weight, 0.0)

    def test_micro_and_macro_calculation(self):
        """Verify mathematical definition of micro vs macro precision and recall."""
        # Scenario 1: TP=1, FP=1, FN=0 -> P=0.5, R=1.0
        # Scenario 2: TP=3, FP=1, FN=1 -> P=0.75, R=0.75
        p1, r1 = 1.0 / 2.0, 1.0 / 1.0
        p2, r2 = 3.0 / 4.0, 3.0 / 4.0

        macro_p = (p1 + p2) / 2.0  # (0.5 + 0.75)/2 = 0.625
        macro_r = (r1 + r2) / 2.0  # (1.0 + 0.75)/2 = 0.875

        tot_tp = 1 + 3
        tot_fp = 1 + 1
        tot_fn = 0 + 1

        micro_p = tot_tp / (tot_tp + tot_fp)  # 4 / 6 = 0.6667
        micro_r = tot_tp / (tot_tp + tot_fn)  # 4 / 5 = 0.8000

        self.assertAlmostEqual(macro_p, 0.625, places=4)
        self.assertAlmostEqual(macro_r, 0.875, places=4)
        self.assertAlmostEqual(micro_p, 4.0 / 6.0, places=4)
        self.assertAlmostEqual(micro_r, 4.0 / 5.0, places=4)


if __name__ == "__main__":
    unittest.main()
