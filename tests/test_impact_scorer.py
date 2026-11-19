"""
Unit tests for CodeMind Phase 8 Milestone 8.2:
Multi-Signal Impact Scorer, Dynamic Renormalization, and Confidence Metrics.
"""

import unittest
from unittest.mock import MagicMock

from codemind.impact.models import (
    ChangeTarget,
    BlastRadiusNode,
    BlastRadiusReport,
    CentralityMetrics,
    ImpactAnalysisConfig,
    ImpactRiskLevel,
    TestRecommendation,
    TestIntelligenceReport,
)
from codemind.impact.scorer import MultiSignalImpactScorer


class TestMilestone82ImpactScorer(unittest.TestCase):
    """Test suite for Milestone 8.2 Multi-Signal Impact Scorer."""

    def setUp(self):
        self.config = ImpactAnalysisConfig()
        self.target = ChangeTarget(
            node_id="function:auth.py:verify_token",
            name="verify_token",
            entity_type="function",
            file_path="auth.py",
            relative_path="auth.py",
            metadata={"complexity": 5},
        )
        self.blast_radius = BlastRadiusReport(
            target=self.target,
            max_depth=3,
            total_impacted=10,
            impacted_nodes=[],
            impacted_edges=[],
            counts_by_type={"function": 6, "file": 4},
            counts_by_depth={1: 4, 2: 6},
        )
        self.centrality = CentralityMetrics(
            in_degree_centrality=0.40,
            pagerank=0.60,
            composite_centrality=0.48,
        )

    def test_full_signals_scoring(self):
        """Test scoring when all signals (graph, git, tests) are available."""
        # Mock churn analyzer
        churn_analyzer = MagicMock()
        metric_mock = MagicMock()
        metric_mock.commit_frequency = 10
        churn_analyzer.file_metrics = {"auth.py": metric_mock}

        # Mock coupling analyzer
        coupling_analyzer = MagicMock()
        coupling_mock = MagicMock()
        coupling_mock.file_a = "auth.py"
        coupling_mock.file_b = "api.py"
        coupling_mock.jaccard_similarity = 0.50
        coupling_mock.confidence_a_to_b = 0.80
        coupling_analyzer.couplings = [coupling_mock]

        # Mock test report
        test_rec = TestRecommendation(
            test_file="tests/test_auth.py",
            test_target="test_verify_token",
            evidence_type="DIRECT_INVOCATION",
            tier=0,
            rank_score=0.90,
            associated_source_entity="function:auth.py:verify_token",
            description="Direct test call",
        )
        test_report = TestIntelligenceReport(
            target=self.target,
            total_tests=1,
            recommendations=[test_rec],
            tier_breakdown={0: 1},
            evidence_breakdown={"DIRECT_INVOCATION": 1},
        )

        scorer = MultiSignalImpactScorer(
            config=self.config,
            churn_analyzer=churn_analyzer,
            coupling_analyzer=coupling_analyzer,
            has_git=True,
            total_repo_commits=25,
            has_tests=True,
        )

        report = scorer.compute_impact(
            target=self.target,
            blast_radius=self.blast_radius,
            centrality=self.centrality,
            test_report=test_report,
        )

        self.assertGreater(report.composite_score, 0.0)
        self.assertLessEqual(report.composite_score, 1.0)
        self.assertEqual(report.confidence, 1.0)  # 0.50 + 0.30 + 0.20
        self.assertEqual(report.confidence_level, "HIGH")

        # Verify all signals available
        for name, sig in report.signals.items():
            self.assertTrue(sig.available, f"Signal {name} should be available")

        # Effective weights sum to 1.0
        eff_weight_sum = sum(s.effective_weight for s in report.signals.values())
        self.assertAlmostEqual(eff_weight_sum, 1.0, places=3)

    def test_dynamic_weight_renormalization_non_git(self):
        """Test dynamic weight renormalization when Git history is absent."""
        scorer = MultiSignalImpactScorer(
            config=self.config,
            has_git=False,
            total_repo_commits=0,
            has_tests=True,
        )

        report = scorer.compute_impact(
            target=self.target,
            blast_radius=self.blast_radius,
            centrality=self.centrality,
            test_report=None,
        )

        # Volatility and coupling must be unavailable
        self.assertFalse(report.signals["historical_volatility"].available)
        self.assertFalse(report.signals["logical_coupling"].available)
        self.assertEqual(report.signals["historical_volatility"].effective_weight, 0.0)
        self.assertEqual(report.signals["logical_coupling"].effective_weight, 0.0)

        # Available signals effective weights sum to 1.0
        eff_weight_sum = sum(s.effective_weight for s in report.signals.values())
        self.assertAlmostEqual(eff_weight_sum, 1.0, places=3)

        # Confidence penalized for no git (0.50 + 0.0 + 0.20 = 0.70)
        self.assertEqual(report.confidence, 0.70)
        self.assertEqual(report.confidence_level, "MEDIUM")

    def test_missing_tests_yields_maximum_exposure_risk(self):
        """CRITICAL: Missing tests must yield test exposure risk = 1.0 (blind spot)."""
        scorer = MultiSignalImpactScorer(
            config=self.config,
            has_git=False,
            total_repo_commits=0,
            has_tests=False,  # No test suite detected
        )

        report = scorer.compute_impact(
            target=self.target,
            blast_radius=self.blast_radius,
            centrality=self.centrality,
            test_report=None,
        )

        test_signal = report.signals["test_exposure_risk"]
        self.assertTrue(test_signal.available)
        self.assertEqual(test_signal.normalized_score, 1.0)
        self.assertIn("NO_TEST_SUITE_DETECTED", test_signal.diagnostic_note)

    def test_shallow_git_history_handling(self):
        """Git history with < 3 commits is marked insufficient and omitted."""
        scorer = MultiSignalImpactScorer(
            config=self.config,
            has_git=True,
            total_repo_commits=2,
            has_tests=True,
        )

        report = scorer.compute_impact(
            target=self.target,
            blast_radius=self.blast_radius,
            centrality=self.centrality,
            test_report=None,
        )

        vol_signal = report.signals["historical_volatility"]
        self.assertFalse(vol_signal.available)
        self.assertIn("INSUFFICIENT_GIT_HISTORY", vol_signal.diagnostic_note)


if __name__ == "__main__":
    unittest.main()
