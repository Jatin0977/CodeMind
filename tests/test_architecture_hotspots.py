"""
Unit and integration tests for CodeMind Phase 9.3:
Multi-Signal Maintenance Hotspot Detection & Risk Intelligence.
"""

import pytest
import networkx as nx

from codemind.architecture.models import (
    AnalysisState,
    HotspotArchetype,
    HotspotItem,
    HotspotReport,
    ModuleEntity,
)
from codemind.architecture.hotspots import (
    MaintenanceHotspotScorer,
    MaintenanceHotspotDetector,
    deterministic_pagerank,
    normalize_95th_percentile,
    compute_evidence_coverage,
)
from codemind.git.models import CommitRecord, FileChange, FileChangeStatus
from codemind.git.churn import FileChurnMetrics, RepositoryChurnSummary
from codemind.git.coupling import LogicalCoupling


class TestMaintenanceHotspotScorer:
    """Tests for the mathematical hotspot scoring formulas and renormalization."""

    def setup_method(self):
        self.scorer = MaintenanceHotspotScorer()

    def test_normal_scoring_all_signals_active(self):
        """Full evidence state with all 4 signals active: canonical base weights (0.30, 0.25, 0.30, 0.15)."""
        res = self.scorer.calculate_base_score(ccn=0.80, cent=0.60, churn=0.70, coup=0.40)
        assert res.is_available is True
        # Expected base score: 0.30*0.80 + 0.25*0.60 + 0.30*0.70 + 0.15*0.40 = 0.24 + 0.15 + 0.21 + 0.06 = 0.66
        assert res.base_score == 0.6600
        assert res.effective_weights == {"ccn": 0.3000, "cent": 0.2500, "churn": 0.3000, "coup": 0.1500}

    def test_missing_git_churn_weight_renormalization(self):
        """
        Approved worked example from Phase 9.0:
        Static-only intake where churn is None:
        ccn=0.80, cent=0.60, coup=0.40, churn=None
        W_active = 0.30 + 0.25 + 0.15 = 0.70
        Renormalized weights: ccn = 3/7, cent = 2.5/7, coup = 1.5/7
        Expected base score: round((3/7)*0.80 + (2.5/7)*0.60 + (1.5/7)*0.40, 4) = 0.6429
        """
        res = self.scorer.calculate_base_score(ccn=0.80, cent=0.60, coup=0.40, churn=None)
        expected = round((3 / 7) * 0.80 + (2.5 / 7) * 0.60 + (1.5 / 7) * 0.40, 4)
        assert res.base_score == expected
        assert res.base_score == 0.6429
        assert res.effective_weights == {
            "ccn": round(3 / 7, 4),
            "cent": round(2.5 / 7, 4),
            "coup": round(1.5 / 7, 4),
        }
        assert "churn" not in res.effective_weights

    def test_single_active_signal_renormalization(self):
        """When only 1 signal is available, effective weight renormalizes to 1.0000."""
        res = self.scorer.calculate_base_score(ccn=0.75, cent=None, churn=None, coup=None)
        assert res.is_available is True
        assert res.base_score == 0.7500
        assert res.effective_weights == {"ccn": 1.0000}

    def test_all_signals_missing_boundary(self):
        """When no signals are provided, is_available is False and base score is 0.0."""
        res = self.scorer.calculate_base_score(ccn=None, cent=None, churn=None, coup=None)
        assert res.is_available is False
        assert res.base_score == 0.0
        assert res.effective_weights == {}

    def test_interaction_multiplier_piecewise_boundaries(self):
        """
        Tests the non-linear interaction multiplier at all critical boundaries:
        - k_high <= 1: 1.0000
        - k_high == 2: 1.1500
        - k_high == 3: continuous linear scale from 1.2000 to 1.5000
        """
        # Case A: k_high = 0 (all below 0.60)
        assert self.scorer.compute_multiplier(churn=0.59, ccn=0.58, cent=0.55) == 1.0000

        # Case B: k_high = 1 (single high)
        assert self.scorer.compute_multiplier(churn=0.95, ccn=0.50, cent=0.40) == 1.0000

        # Case C: k_high = 2 (dual high right below 3-way boundary)
        assert self.scorer.compute_multiplier(churn=0.60, ccn=0.60, cent=0.5999) == 1.1500

        # Case D: k_high = 3 exact minimum (all 0.6000, sum = 1.8000)
        mu_triple_min = self.scorer.compute_multiplier(churn=0.60, ccn=0.60, cent=0.60)
        assert mu_triple_min == 1.2000
        assert mu_triple_min > 1.1500  # Strict step increase

        # Case E: k_high = 3 mid-point (sum = 2.2500)
        # 1.20 + 0.30 * ((2.25 - 1.80) / 1.20) = 1.20 + 0.30 * (0.45 / 1.20) = 1.3125
        assert self.scorer.compute_multiplier(churn=0.85, ccn=0.75, cent=0.65) == 1.3125

        # Case F: k_high = 3 maximum saturation (sum = 3.0000)
        assert self.scorer.compute_multiplier(churn=1.00, ccn=1.00, cent=1.00) == 1.5000

        # Non-Git mode: churn is None -> at most 2 signals can be high -> max multiplier 1.1500
        assert self.scorer.compute_multiplier(churn=None, ccn=0.90, cent=0.80) == 1.1500

    def test_score_clamping_at_unity(self):
        """When base_score * multiplier > 1.0, score clamps strictly to 1.0000."""
        # base_score = 0.85, multiplier = 1.50 -> raw product = 1.275 -> clamped = 1.0000
        final_score, base_score, mu, _ = self.scorer.calculate_hotspot_score(
            ccn=1.0, cent=1.0, churn=1.0, coup=1.0
        )
        assert base_score == 1.0000
        assert mu == 1.5000
        assert final_score == 1.0000

    def test_archetype_classifications(self):
        """Verify deterministic categorization of all hotspot archetypes."""
        # 1. Volatile Fragile: churn >= 0.60 and ccn >= 0.60
        arch, conf, _ = self.scorer.classify_archetype(ccn=0.75, cent=0.30, churn=0.80, coup=0.20)
        assert arch == HotspotArchetype.VOLATILE_FRAGILE
        assert conf == 1.0

        # 2. Brain Module: ccn >= 0.70 and cent >= 0.50 (with raw complexity guard >= 20)
        arch, conf, _ = self.scorer.classify_archetype(
            ccn=0.85, cent=0.65, churn=0.20, coup=0.30, raw_metrics={"complexity": 50}
        )
        assert arch == HotspotArchetype.BRAIN_MODULE
        assert conf == 1.0

        # 3. Shotgun Surgery Catalyst: coup >= 0.60 and cent >= 0.50
        arch, conf, _ = self.scorer.classify_archetype(ccn=0.40, cent=0.60, churn=0.20, coup=0.70)
        assert arch == HotspotArchetype.SHOTGUN_SURGERY
        assert conf == 1.0

        # 4. Stable Core: cent >= 0.50, churn <= 0.30, ccn <= 0.30
        arch, conf, _ = self.scorer.classify_archetype(ccn=0.20, cent=0.70, churn=0.15, coup=0.10)
        assert arch == HotspotArchetype.STABLE_CORE
        assert conf == 1.0

        # 5. Normal Component: below thresholds
        arch, conf, _ = self.scorer.classify_archetype(ccn=0.40, cent=0.30, churn=0.40, coup=0.30)
        assert arch == HotspotArchetype.NORMAL
        assert conf == 1.0

        # 6. Class entities: God Class Confirmed vs Candidate
        raw_god = {"sloc": 450, "methods_count": 18, "wmc": 42}
        arch_conf, conf_val, _ = self.scorer.classify_archetype(
            ccn=0.90, cent=0.60, churn=0.50, coup=0.40,
            entity_type="class", raw_metrics=raw_god, has_class_graph=True
        )
        assert arch_conf == HotspotArchetype.GOD_CLASS
        assert conf_val == 1.0

        arch_cand, cand_val, _ = self.scorer.classify_archetype(
            ccn=0.90, cent=None, churn=0.50, coup=0.40,
            entity_type="class", raw_metrics=raw_god, has_class_graph=False
        )
        assert arch_cand == HotspotArchetype.GOD_CLASS_CANDIDATE
        assert cand_val == 0.5


class TestPercentileNormalization:
    """Tests for the 95th-Percentile Clipped Min-Max Normalization algorithm."""

    def test_vector_1_extreme_outlier(self):
        """Vector 1 from Phase 9.0: 9 zeros and one 100."""
        inputs = [0.0] * 9 + [100.0]
        out = normalize_95th_percentile(inputs)
        assert out[:9] == [0.0000] * 9
        assert out[9] == 1.0000

    def test_vector_2_linear_distribution(self):
        """Vector 2 from Phase 9.0: [10, 20, 30, 40, 50]."""
        inputs = [10.0, 20.0, 30.0, 40.0, 50.0]
        out = normalize_95th_percentile(inputs)
        assert out == [0.0000, 0.2632, 0.5263, 0.7895, 1.0000]

    def test_vector_3_constant_non_zero_zero_variance(self):
        """Vector 3 from Phase 9.0: All values identical and > 0."""
        inputs = [5.0, 5.0, 5.0, 5.0]
        out = normalize_95th_percentile(inputs)
        assert out == [0.5000, 0.5000, 0.5000, 0.5000]

    def test_zero_variance_all_zero(self):
        """All values 0.0 map to 0.0000."""
        inputs = [0.0, 0.0, 0.0]
        out = normalize_95th_percentile(inputs)
        assert out == [0.0000, 0.0000, 0.0000]

    def test_single_value_maps_to_half(self):
        """Single observation maps to neutral 0.5000."""
        out = normalize_95th_percentile([42.0])
        assert out == [0.5000]

    def test_missing_values_preserved(self):
        """None values remain None and do not distort valid element normalization."""
        inputs = [10.0, None, 50.0]
        out = normalize_95th_percentile(inputs)
        assert out[1] is None
        assert out[0] == 0.0000
        assert out[2] == 1.0000


class TestDeterministicPageRank:
    """Tests for the Power Iteration PageRank implementation."""

    def test_pagerank_deterministic_sum_and_shuffled_invariance(self):
        """
        Verify that:
        1. Scores sum approximately to 1.0 within tolerance bound len(nodes) * 1e-6.
        2. Input order (shuffled/reversed) produces bit-identical floating point results.
        """
        nodes = ["C", "A", "D", "B"]
        edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"), ("B", "D")]

        # Run 1: original order
        pr1 = deterministic_pagerank(nodes, edges)
        assert sum(pr1.values()) == pytest.approx(1.0, abs=len(nodes) * 1e-6)

        # Run 2: reversed nodes and edges
        pr2 = deterministic_pagerank(list(reversed(nodes)), list(reversed(edges)))

        # Assert strict bit-identical match across runs
        assert pr1 == pr2

    def test_dangling_sink_node_redistribution(self):
        """Graph with dangling sink (node with out-degree = 0) redistributes probability mass uniformly."""
        nodes = ["A", "B", "C"]
        edges = [("A", "B"), ("B", "C")]  # C has no outgoing edges
        pr = deterministic_pagerank(nodes, edges)
        assert sum(pr.values()) == pytest.approx(1.0, abs=len(nodes) * 1e-6)
        # Node C receives in-flow from B and dangling redistribution, so its PR is highest
        assert pr["C"] > pr["B"] > pr["A"]

    def test_empty_and_single_node_graphs(self):
        """Boundary handling for empty and 1-node graphs."""
        assert deterministic_pagerank([], []) == {}
        assert deterministic_pagerank(["lone_node"], []) == {"lone_node": 1.000000}


class TestMaintenanceHotspotDetectorIntegration:
    """Integration tests for the full detector over module quotient graphs and Git evidence."""

    def setup_method(self):
        self.detector = MaintenanceHotspotDetector()

    def test_end_to_end_full_evidence_hotspot_detection(self):
        """
        Comprehensive integration test with 4 modules, quotient graph edges,
        mock Git churn, and temporal co-change coupling.
        """
        m1 = ModuleEntity(name="mod_api", relative_dir="api", files=["api/views.py"], total_complexity=80, total_loc=400)
        m2 = ModuleEntity(name="mod_core", relative_dir="core", files=["core/engine.py"], total_complexity=120, total_loc=600)
        m3 = ModuleEntity(name="mod_db", relative_dir="db", files=["db/models.py"], total_complexity=30, total_loc=200)
        m4 = ModuleEntity(name="mod_util", relative_dir="util", files=["util/helpers.py"], total_complexity=10, total_loc=100)

        modules = [m1, m2, m3, m4]

        q_graph = nx.DiGraph()
        q_graph.add_edge("mod_api", "mod_core")
        q_graph.add_edge("mod_core", "mod_db")
        q_graph.add_edge("mod_core", "mod_util")
        q_graph.add_edge("mod_db", "mod_util")

        churn_summary = RepositoryChurnSummary(
            total_churn=1000,
            file_metrics={
                "core/engine.py": FileChurnMetrics(path="core/engine.py", total_churn=700, commit_frequency=25),
                "api/views.py": FileChurnMetrics(path="api/views.py", total_churn=200, commit_frequency=10),
                "db/models.py": FileChurnMetrics(path="db/models.py", total_churn=80, commit_frequency=5),
                "util/helpers.py": FileChurnMetrics(path="util/helpers.py", total_churn=20, commit_frequency=2),
            },
        )

        couplings = [
            LogicalCoupling(
                canonical_file_a="core/engine.py",
                canonical_file_b="api/views.py",
                support_count=8,
                jaccard_similarity=0.75,
                confidence_a_to_b=0.8,
                confidence_b_to_a=0.7,
            )
        ]

        report = self.detector.detect_hotspots(
            modules=modules,
            quotient_graph=q_graph,
            churn_summary=churn_summary,
            temporal_couplings=couplings,
            total_source_files=4,
            valid_ast_files=4,
        )

        assert report.total_entities_analyzed == 4
        assert len(report.hotspots) == 4

        # mod_core has highest complexity, highest churn, central position -> ranks top
        top_hotspot = report.hotspots[0]
        assert top_hotspot.entity_path == "mod_core"
        assert top_hotspot.hotspot_score > 0.70
        assert top_hotspot.multiplier >= 1.15
        assert top_hotspot.archetype in (HotspotArchetype.VOLATILE_FRAGILE, HotspotArchetype.BRAIN_MODULE)

        # Evidence coverage is FULL_EVIDENCE
        assert report.evidence_coverage is not None
        assert report.evidence_coverage.analysis_state == AnalysisState.FULL_EVIDENCE
        assert report.evidence_coverage.churn_available is True
        assert report.top_hotspot_mean > 0.0

    def test_non_git_intake_degraded_to_partial_static_only(self):
        """
        When Git churn and commits are unavailable, weights renormalize dynamically,
        and evidence coverage state is PARTIAL_STATIC_ONLY.
        """
        m1 = ModuleEntity(name="pkg_a", relative_dir="pkg_a", files=["pkg_a/a.py"], total_complexity=50)
        m2 = ModuleEntity(name="pkg_b", relative_dir="pkg_b", files=["pkg_b/b.py"], total_complexity=20)

        q_graph = nx.DiGraph()
        q_graph.add_edge("pkg_a", "pkg_b")

        report = self.detector.detect_hotspots(
            modules=[m1, m2],
            quotient_graph=q_graph,
            commits=None,
            churn_summary=None,
            temporal_couplings=None,
            total_source_files=2,
            valid_ast_files=2,
        )

        assert report.total_entities_analyzed == 2
        assert report.analysis_state == AnalysisState.PARTIAL_STATIC_ONLY
        assert report.evidence_coverage.churn_available is False
        assert "GIT_CHURN_HISTORY_UNAVAILABLE" in report.evidence_coverage.missing_signals

        # Verify active signals on hotspot items exclude churn
        for h in report.hotspots:
            assert h.signal_availability["churn"] is False
            assert "churn" not in h.effective_weights
            # ccn, cent, coup are present
            assert "ccn" in h.effective_weights

    def test_deterministic_tie_breaking(self):
        """
        When two entities have identical hotspot_score and base_score,
        they must be sorted deterministically in ascending alphabetical order of entity_path.
        """
        # Create 2 modules with identical metrics
        m_beta = ModuleEntity(name="beta_mod", relative_dir="beta", files=["beta/x.py"], total_complexity=50)
        m_alpha = ModuleEntity(name="alpha_mod", relative_dir="alpha", files=["alpha/x.py"], total_complexity=50)

        # Empty graph -> identical centrality, identical complexity -> identical score
        report = self.detector.detect_hotspots(modules=[m_beta, m_alpha])

        assert len(report.hotspots) == 2
        assert report.hotspots[0].hotspot_score == report.hotspots[1].hotspot_score
        assert report.hotspots[0].base_score == report.hotspots[1].base_score

        # Alphabetical tie breaker: "alpha_mod" comes before "beta_mod"
        assert report.hotspots[0].entity_path == "alpha_mod"
        assert report.hotspots[1].entity_path == "beta_mod"

    def test_empty_modules_returns_clean_report(self):
        """Empty module input returns zero hotspots without division errors."""
        report = self.detector.detect_hotspots(modules=[])
        assert report.total_entities_analyzed == 0
        assert report.hotspots == []
        assert report.top_hotspot_mean == 0.0
