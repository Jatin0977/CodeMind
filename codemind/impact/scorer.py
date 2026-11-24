"""
Multi-Signal Impact Scorer for CodeMind Phase 8.
Synthesizes structural reachability, graph centrality, historical volatility,
logical coupling, test exposure risk, and cyclomatic complexity into an explainable,
dynamically-renormalized composite impact score.
"""

import math
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple

from .models import (
    ChangeTarget,
    BlastRadiusReport,
    CentralityMetrics,
    ImpactSignal,
    ImpactAnalysisConfig,
    ImpactRiskLevel,
    ImpactReport,
    TestIntelligenceReport,
)
from ..graph.models import NodeType


class MultiSignalImpactScorer:
    """
    Computes explainable composite impact score with dynamic weight renormalization
    and confidence tracking. Strictly avoids equating missing data with zero risk.
    """

    def __init__(
        self,
        config: Optional[ImpactAnalysisConfig] = None,
        churn_analyzer: Optional[Any] = None,
        coupling_analyzer: Optional[Any] = None,
        has_git: bool = False,
        total_repo_commits: int = 0,
        has_tests: bool = False,
    ):
        self.config = config or ImpactAnalysisConfig()
        self.churn_analyzer = churn_analyzer
        self.coupling_analyzer = coupling_analyzer
        self.has_git = has_git
        self.total_repo_commits = total_repo_commits
        self.has_tests = has_tests

    def compute_impact(
        self,
        target: ChangeTarget,
        blast_radius: BlastRadiusReport,
        centrality: CentralityMetrics,
        test_report: Optional[TestIntelligenceReport] = None,
    ) -> ImpactReport:
        """
        Synthesize all available signals into a normalized ImpactReport.

        Args:
            target: The analyzed ChangeTarget.
            blast_radius: BlastRadiusReport from ChangeImpactEngine.
            centrality: CentralityMetrics from ChangeImpactEngine.
            test_report: Optional TestIntelligenceReport from TestIntelligenceEngine.

        Returns:
            Fully populated, explainable ImpactReport.
        """
        diagnostics: List[str] = []

        # 1. Signal Computations
        s1 = self._compute_s1_reachability(blast_radius)
        s2 = self._compute_s2_centrality(centrality)
        s3 = self._compute_s3_volatility(target, diagnostics)
        s4 = self._compute_s4_coupling(target, diagnostics)
        s5 = self._compute_s5_test_exposure(test_report, diagnostics)
        s6 = self._compute_s6_complexity(target, diagnostics)

        signals_map = {
            "structural_reachability": s1,
            "graph_centrality": s2,
            "historical_volatility": s3,
            "logical_coupling": s4,
            "test_exposure_risk": s5,
            "cyclomatic_complexity": s6,
        }

        # 2. Dynamic Weight Renormalization
        available_signals = [s for s in signals_map.values() if s.available]
        total_available_weight = sum(s.base_weight for s in available_signals)

        if total_available_weight > 0:
            for s in signals_map.values():
                if s.available:
                    s.effective_weight = round(s.base_weight / total_available_weight, 4)
                else:
                    s.effective_weight = 0.0

            composite_score = sum(s.effective_weight * s.normalized_score for s in available_signals)
            composite_score = round(min(1.0, max(0.0, composite_score)), 4)
        else:
            composite_score = 0.0

        # 3. Confidence Calculation
        confidence, confidence_level = self._compute_confidence(diagnostics)

        # 4. Risk Level Categorization
        risk_level = ImpactRiskLevel.from_score(composite_score).value

        # Add top driver diagnostic
        sorted_drivers = sorted(
            available_signals,
            key=lambda s: s.effective_weight * s.normalized_score,
            reverse=True,
        )
        if sorted_drivers:
            top_driver = sorted_drivers[0]
            diagnostics.insert(
                0,
                f"Primary risk driver is '{top_driver.name}' "
                f"(score: {top_driver.normalized_score:.2f}, weight: {top_driver.effective_weight:.2f})."
            )

        now_str = datetime.now(timezone.utc).isoformat()

        return ImpactReport(
            target=target,
            composite_score=composite_score,
            risk_level=risk_level,
            confidence=confidence,
            confidence_level=confidence_level,
            signals=signals_map,
            centrality=centrality,
            blast_radius=blast_radius,
            diagnostics=diagnostics,
            timestamp=now_str,
        )

    def _compute_s1_reachability(self, blast_radius: BlastRadiusReport) -> ImpactSignal:
        """S1: Structural Reachability using logistic sigmoid saturation."""
        r_total = blast_radius.total_impacted
        if r_total == 0:
            norm_score = 0.0
        else:
            m1 = self.config.reach_midpoint
            k1 = self.config.reach_slope
            # Logistic sigmoid
            norm_score = 1.0 / (1.0 + math.exp(-k1 * (r_total - m1)))
            norm_score = min(1.0, max(0.0, norm_score))

        return ImpactSignal(
            name="structural_reachability",
            raw_value=float(r_total),
            normalized_score=round(norm_score, 4),
            base_weight=self.config.w_reach,
            effective_weight=self.config.w_reach,
            available=True,
            description="Multi-hop reverse dependent count saturated via logistic sigmoid.",
        )

    def _compute_s2_centrality(self, centrality: CentralityMetrics) -> ImpactSignal:
        """S2: Graph Centrality combining In-Degree and PageRank on code subgraph."""
        score = centrality.composite_centrality
        return ImpactSignal(
            name="graph_centrality",
            raw_value=score,
            normalized_score=round(score, 4),
            base_weight=self.config.w_centrality,
            effective_weight=self.config.w_centrality,
            available=True,
            description="Normalized In-Degree and PageRank prestige on pure code dependency graph.",
        )

    def _compute_s3_volatility(self, target: ChangeTarget, diagnostics: List[str]) -> ImpactSignal:
        """S3: Historical Volatility / Commit Frequency from churn analysis."""
        if not self.has_git:
            diagnostics.append("Git history unavailable: historical volatility signal omitted.")
            return ImpactSignal(
                name="historical_volatility",
                raw_value=0.0,
                normalized_score=0.0,
                base_weight=self.config.w_volatility,
                effective_weight=0.0,
                available=False,
                description="Git temporal history not present.",
                diagnostic_note="NO_GIT_REPOSITORY",
            )

        if self.total_repo_commits < 3:
            diagnostics.append("Shallow Git history (< 3 commits): volatility omitted to avoid noise.")
            return ImpactSignal(
                name="historical_volatility",
                raw_value=float(self.total_repo_commits),
                normalized_score=0.0,
                base_weight=self.config.w_volatility,
                effective_weight=0.0,
                available=False,
                description="Shallow Git commit sample (< 3 commits).",
                diagnostic_note="INSUFFICIENT_GIT_HISTORY",
            )

        commits = 0
        file_path = target.relative_path or target.file_path or ""
        if self.churn_analyzer and file_path:
            norm_path = file_path.replace("\\", "/").strip("/").lower()
            while norm_path.startswith("./"):
                norm_path = norm_path[2:]
            churn_data = getattr(self.churn_analyzer, "file_metrics", None)
            if churn_data is None:
                summary_obj = getattr(self.churn_analyzer, "summary", None) or getattr(self.churn_analyzer, "last_summary", None)
                churn_data = getattr(summary_obj, "file_metrics", {}) if summary_obj else {}

            if isinstance(churn_data, dict):
                for k, v in churn_data.items():
                    k_norm = k.replace("\\", "/").strip("/").lower()
                    while k_norm.startswith("./"):
                        k_norm = k_norm[2:]
                    if k_norm == norm_path:
                        commits = getattr(v, "commit_frequency", 0)
                        break

        norm_score = min(1.0, float(commits) / self.config.volatility_sat)
        return ImpactSignal(
            name="historical_volatility",
            raw_value=float(commits),
            normalized_score=round(norm_score, 4),
            base_weight=self.config.w_volatility,
            effective_weight=self.config.w_volatility,
            available=True,
            description=f"File commit frequency ({commits} commits) saturated at {self.config.volatility_sat}.",
        )

    def _compute_s4_coupling(self, target: ChangeTarget, diagnostics: List[str]) -> ImpactSignal:
        """S4: Logical Coupling Strength."""
        if not self.has_git:
            return ImpactSignal(
                name="logical_coupling",
                raw_value=0.0,
                normalized_score=0.0,
                base_weight=self.config.w_coupling,
                effective_weight=0.0,
                available=False,
                description="Git repository not present.",
                diagnostic_note="NO_GIT_REPOSITORY",
            )

        if self.total_repo_commits < 3:
            return ImpactSignal(
                name="logical_coupling",
                raw_value=0.0,
                normalized_score=0.0,
                base_weight=self.config.w_coupling,
                effective_weight=0.0,
                available=False,
                description="Shallow Git history (< 3 commits).",
                diagnostic_note="INSUFFICIENT_GIT_HISTORY",
            )

        max_coupling = 0.0
        file_path = target.relative_path or target.file_path or ""
        if self.coupling_analyzer and file_path:
            norm_path = file_path.replace("\\", "/").strip("/").lower()
            while norm_path.startswith("./"):
                norm_path = norm_path[2:]
            couplings = getattr(self.coupling_analyzer, "couplings", [])
            for c in couplings:
                file_a = (getattr(c, "canonical_file_a", None) or getattr(c, "file_a", "") or "").replace("\\", "/").strip("/").lower()
                file_b = (getattr(c, "canonical_file_b", None) or getattr(c, "file_b", "") or "").replace("\\", "/").strip("/").lower()
                while file_a.startswith("./"):
                    file_a = file_a[2:]
                while file_b.startswith("./"):
                    file_b = file_b[2:]
                if norm_path in (file_a, file_b):
                    jaccard = getattr(c, "jaccard_similarity", 0.0)
                    conf = getattr(c, "confidence_a_to_b" if norm_path == file_a else "confidence_b_to_a", 1.0)
                    strength = jaccard * conf
                    if strength > max_coupling:
                        max_coupling = strength

        norm_score = min(1.0, max(0.0, max_coupling))
        return ImpactSignal(
            name="logical_coupling",
            raw_value=round(max_coupling, 4),
            normalized_score=round(norm_score, 4),
            base_weight=self.config.w_coupling,
            effective_weight=self.config.w_coupling,
            available=True,
            description="Peak co-change coupling strength (Jaccard * Confidence).",
        )

    def _compute_s5_test_exposure(
        self,
        test_report: Optional[TestIntelligenceReport],
        diagnostics: List[str],
    ) -> ImpactSignal:
        """
        S5: Test Exposure Risk.
        Inverted signal: high test presence -> low risk (0.0).
        Zero tests -> maximum blind-spot risk (1.0).
        """
        if not self.has_tests:
            diagnostics.append("No test suite detected in codebase: test exposure risk set to maximum (1.0).")
            return ImpactSignal(
                name="test_exposure_risk",
                raw_value=0.0,
                normalized_score=1.0,
                base_weight=self.config.w_test,
                effective_weight=self.config.w_test,
                available=True,
                description="No test suite detected; unmonitored blind spot risk is at maximum (1.0).",
                diagnostic_note="NO_TEST_SUITE_DETECTED",
            )

        if test_report is None or test_report.total_tests == 0:
            diagnostics.append("Target has 0 associated tests across blast radius: test exposure risk is 1.0.")
            return ImpactSignal(
                name="test_exposure_risk",
                raw_value=0.0,
                normalized_score=1.0,
                base_weight=self.config.w_test,
                effective_weight=self.config.w_test,
                available=True,
                description="Zero tests found for target across direct and transitive tiers.",
                diagnostic_note="ZERO_ASSOCIATED_TESTS",
            )

        # Calculate coverage score from test recommendations
        tier_weights = {0: 1.0, 1: 0.6, 2: 0.3}
        coverage_accum = 0.0
        for rec in test_report.recommendations:
            tw = tier_weights.get(rec.tier, 0.2)
            coverage_accum += rec.rank_score * tw

        # S5 = 1.0 - min(1.0, coverage_accum)
        exposure_risk = max(0.0, 1.0 - min(1.0, coverage_accum))
        return ImpactSignal(
            name="test_exposure_risk",
            raw_value=round(coverage_accum, 4),
            normalized_score=round(exposure_risk, 4),
            base_weight=self.config.w_test,
            effective_weight=self.config.w_test,
            available=True,
            description=f"Inverted test exposure risk (calculated from {test_report.total_tests} test candidate(s)).",
        )

    def _compute_s6_complexity(self, target: ChangeTarget, diagnostics: List[str]) -> ImpactSignal:
        """S6: Cyclomatic Complexity factor."""
        ccn = target.metadata.get("complexity") or target.metadata.get("cyclomatic_complexity") or 1
        ccn = max(1, int(ccn))

        norm_score = min(1.0, max(0.0, (ccn - 1) / self.config.complexity_sat))
        return ImpactSignal(
            name="cyclomatic_complexity",
            raw_value=float(ccn),
            normalized_score=round(norm_score, 4),
            base_weight=self.config.w_complexity,
            effective_weight=self.config.w_complexity,
            available=True,
            description=f"Cyclomatic complexity (CCN={ccn}) saturated at {self.config.complexity_sat}.",
        )

    def _compute_confidence(self, diagnostics: List[str]) -> Tuple[float, str]:
        """Compute analysis confidence score based on signal availability."""
        confidence = 0.50  # Base: AST Knowledge Graph available

        if self.has_git:
            if self.total_repo_commits >= 10:
                confidence += 0.30
            elif self.total_repo_commits >= 3:
                confidence += 0.15
            else:
                pass  # < 3 commits
        else:
            confidence += 0.0

        if self.has_tests:
            confidence += 0.20

        confidence = round(min(1.0, max(0.0, confidence)), 2)

        if confidence >= 0.80:
            conf_level = "HIGH"
        elif confidence >= 0.50:
            conf_level = "MEDIUM"
        else:
            conf_level = "LOW"
            diagnostics.append("LOW_CONFIDENCE_ANALYSIS: Git temporal or test suite signals are absent/shallow.")

        return confidence, conf_level
