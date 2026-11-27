"""
CodeMind Maintenance Hotspot Detection & Risk Intelligence (Phase 9, Milestone 3).
Computes multi-signal maintenance risk using cyclomatic complexity, dependency centrality,
Git churn, and hybrid coupling, with active-signal weight renormalization, non-linear
interaction multiplier, 95th-percentile clipped normalization, and archetype classification.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any, Union

import networkx as nx

from .models import (
    AnalysisState,
    HotspotArchetype,
    HotspotItem,
    HotspotReport,
    EvidenceCoverage,
    ModuleEntity,
)
from ..git.churn import CodeChurnAnalyzer, RepositoryChurnSummary
from ..git.coupling import LogicalCouplingAnalyzer, LogicalCoupling
from ..git.models import CommitRecord

logger = logging.getLogger(__name__)


def deterministic_pagerank(
    graph_or_nodes: Any,
    edges: Optional[List[Tuple[str, str]]] = None,
    damping: float = 0.85,
    eps: float = 1.0e-6,
    max_iter: int = 100,
) -> Dict[str, float]:
    """
    Independent deterministic Power Iteration algorithm for directed graphs.
    Guarantees strict input-order invariance and stable IEEE-754 precision by
    enforcing lexicographical node sorting and explicit neighbor canonicalization.
    """
    if isinstance(graph_or_nodes, (list, set, tuple)):
        nodes = list(graph_or_nodes)
        edge_list = list(edges or [])
    elif hasattr(graph_or_nodes, "nodes") and hasattr(graph_or_nodes, "edges"):
        nodes = list(graph_or_nodes.nodes())
        edge_list = list(graph_or_nodes.edges())
    else:
        return {}

    v_sorted = sorted(list(set(str(n) for n in nodes)))
    n = len(v_sorted)
    if n == 0:
        return {}
    if n == 1:
        return {v_sorted[0]: 1.000000}

    # Canonicalize directed adjacency structures
    out_neighbors: Dict[str, List[str]] = {u: [] for u in v_sorted}
    in_neighbors: Dict[str, List[str]] = {u: [] for u in v_sorted}

    for edge in edge_list:
        u, v = str(edge[0]), str(edge[1])
        if u in out_neighbors and v in in_neighbors:
            out_neighbors[u].append(v)
            in_neighbors[v].append(u)

    for u in v_sorted:
        out_neighbors[u] = sorted(list(set(out_neighbors[u])))
        in_neighbors[u] = sorted(list(set(in_neighbors[u])))

    out_degree = {u: len(out_neighbors[u]) for u in v_sorted}

    # Initialize uniform probability mass
    p_curr = {u: 1.0 / n for u in v_sorted}

    # Power Iteration
    for _ in range(1, max_iter + 1):
        dangling_sum = sum(p_curr[u] for u in v_sorted if out_degree[u] == 0)
        dangling_contrib = (damping * dangling_sum) / n
        base_teleport = (1.0 - damping) / n

        p_next: Dict[str, float] = {}
        for v in v_sorted:
            in_sum = sum(p_curr[u] / out_degree[u] for u in in_neighbors[v])
            p_next[v] = base_teleport + dangling_contrib + (damping * in_sum)

        l1_delta = sum(abs(p_next[u] - p_curr[u]) for u in v_sorted)
        p_curr = p_next
        if l1_delta < eps:
            break

    total_mass = sum(p_curr.values())
    if total_mass > 0:
        return {u: round(p_curr[u] / total_mass, 6) for u in v_sorted}
    return {u: round(1.0 / n, 6) for u in v_sorted}


def normalize_95th_percentile(values: List[Optional[float]]) -> List[Optional[float]]:
    """
    95th-Percentile Clipped Min-Max Normalization per Phase 9.0 specification.
    - Preserves None for missing signal observations.
    - Single observation maps to neutral 0.5000.
    - Zero variance maps to 0.0000 if min == 0 else 0.5000.
    - Multi-value distributions clip at continuous linearly interpolated P95.
    """
    valid_indices = [i for i, v in enumerate(values) if v is not None]
    n = len(valid_indices)

    result: List[Optional[float]] = [None] * len(values)
    if n == 0:
        return result
    if n == 1:
        result[valid_indices[0]] = 0.5000
        return result

    valid_vals = [float(values[i]) for i in valid_indices]
    x_min = min(valid_vals)
    x_max = max(valid_vals)

    if x_max == x_min:
        fill_val = 0.0000 if x_min == 0.0 else 0.5000
        for i in valid_indices:
            result[i] = fill_val
        return result

    s = sorted(valid_vals)
    idx = 0.95 * (n - 1)
    j = int(math.floor(idx))
    f = idx - j

    if j + 1 < n:
        p95 = s[j] + f * (s[j + 1] - s[j])
    else:
        p95 = s[j]

    p_upper = x_max if p95 <= x_min else p95
    divisor = p_upper - x_min

    for i in valid_indices:
        val = float(values[i])
        scaled = (val - x_min) / divisor
        clamped = min(1.0, max(0.0, scaled))
        result[i] = round(clamped, 4)

    return result


@dataclass
class BaseScoreResult:
    """Detailed calculation outcome of raw signal base score weighting."""
    base_score: float
    effective_weights: Dict[str, float]
    active_signals: List[str]
    is_available: bool


class MaintenanceHotspotScorer:
    """
    Mathematical calculation engine for multi-signal maintenance hotspot scores.
    Implements universal raw base weights, dynamic active-signal renormalization,
    and piecewise continuous interaction multipliers.
    """

    CANONICAL_WEIGHTS = {
        "ccn": 0.30,
        "cent": 0.25,
        "churn": 0.30,
        "coup": 0.15,
    }

    def calculate_base_score(
        self,
        ccn: Optional[float] = None,
        cent: Optional[float] = None,
        churn: Optional[float] = None,
        coup: Optional[float] = None,
    ) -> BaseScoreResult:
        """
        Calculates the linear base score with active-signal weight renormalization:
        w'_s = w_s / sum(w_active). Missing signals do not silently become zero.
        """
        signals = {
            "ccn": ccn,
            "cent": cent,
            "churn": churn,
            "coup": coup,
        }
        active = {k: v for k, v in signals.items() if v is not None}
        if not active:
            return BaseScoreResult(
                base_score=0.0,
                effective_weights={},
                active_signals=[],
                is_available=False,
            )

        w_active = sum(self.CANONICAL_WEIGHTS[k] for k in active)
        if w_active <= 0.0:
            return BaseScoreResult(
                base_score=0.0,
                effective_weights={},
                active_signals=[],
                is_available=False,
            )

        eff_weights = {k: round(self.CANONICAL_WEIGHTS[k] / w_active, 4) for k in active}
        raw_weighted_sum = sum((self.CANONICAL_WEIGHTS[k] / w_active) * active[k] for k in active)
        base_score = round(raw_weighted_sum, 4)

        return BaseScoreResult(
            base_score=base_score,
            effective_weights=eff_weights,
            active_signals=sorted(list(active.keys())),
            is_available=True,
        )

    def compute_multiplier(
        self,
        churn: Optional[float] = None,
        ccn: Optional[float] = None,
        cent: Optional[float] = None,
    ) -> float:
        """
        Computes the piecewise non-linear synergy interaction multiplier across
        the three core signals: churn, complexity (ccn), and centrality.
        Threshold theta = 0.6000:
        - k_high <= 1: 1.0000
        - k_high == 2: 1.1500
        - k_high == 3: 1.2000 + 0.3000 * ((sum - 1.8000) / 1.2000) in [1.20, 1.50]
        """
        core_signals = [s for s in [churn, ccn, cent] if s is not None]
        k_high = sum(1 for s in core_signals if s >= 0.6000)

        if k_high <= 1:
            return 1.0000
        elif k_high == 2:
            return 1.1500
        else:
            # k_high == 3: all three are non-null and >= 0.6000
            s_sum = float(churn + ccn + cent)  # type: ignore
            fraction = (s_sum - 1.8000) / 1.2000
            mu = 1.2000 + 0.3000 * fraction
            return round(mu, 4)

    def calculate_hotspot_score(
        self,
        ccn: Optional[float] = None,
        cent: Optional[float] = None,
        churn: Optional[float] = None,
        coup: Optional[float] = None,
    ) -> Tuple[float, float, float, Dict[str, float]]:
        """
        Evaluates full hotspot score: base score, interaction multiplier, and final clamped score.
        Returns: (final_score, base_score, multiplier, effective_weights)
        """
        base_res = self.calculate_base_score(ccn=ccn, cent=cent, churn=churn, coup=coup)
        if not base_res.is_available:
            return 0.0, 0.0, 1.0, {}

        mu = self.compute_multiplier(churn=churn, ccn=ccn, cent=cent)
        final_score = round(min(1.0000, base_res.base_score * mu), 4)
        return final_score, base_res.base_score, mu, base_res.effective_weights

    def classify_archetype(
        self,
        ccn: Optional[float],
        cent: Optional[float],
        churn: Optional[float],
        coup: Optional[float],
        entity_type: str = "module",
        raw_metrics: Optional[Dict[str, Any]] = None,
        has_class_graph: bool = True,
    ) -> Tuple[HotspotArchetype, float, str]:
        """
        Classifies entity into debt archetypes per approved Phase 9.0 rules.
        Returns: (HotspotArchetype, confidence, rationale)
        """
        raw = raw_metrics or {}
        raw_wmc = raw.get("wmc", raw.get("complexity", 0))
        raw_sloc = raw.get("sloc", raw.get("loc", 0))
        raw_methods = raw.get("methods_count", raw.get("methods", 0))

        # 1. God Class / Candidate (classes only)
        if entity_type == "class" and raw_sloc >= 300 and raw_methods >= 10 and raw_wmc >= 30:
            if has_class_graph and cent is not None and cent >= 0.40:
                return (
                    HotspotArchetype.GOD_CLASS,
                    1.0,
                    "Confirmed God Class: excessive direct methods (>=10), high WMC (>=30), large SLOC (>=300), and high centrality (>=0.40).",
                )
            else:
                return (
                    HotspotArchetype.GOD_CLASS_CANDIDATE,
                    0.5,
                    "God Class Candidate: size and complexity criteria met, but class-level graph centrality is unverified or unavailable.",
                )

        # 2. Volatile Fragile Hotspot (rapid mutation + high complexity)
        if churn is not None and ccn is not None and churn >= 0.6000 and ccn >= 0.6000:
            return (
                HotspotArchetype.VOLATILE_FRAGILE,
                1.0,
                "Volatile Fragile Hotspot: rapidly mutating code (churn >= 0.60) coupled with high cyclomatic complexity (CCN >= 0.60).",
            )

        # 3. Brain Module (excessive complexity + central bottleneck)
        raw_ccn = raw.get("complexity", raw.get("ccn", None))
        complexity_guard = True
        if raw_ccn is not None and raw_ccn < 20:
            complexity_guard = False

        if ccn is not None and cent is not None and ccn >= 0.7000 and cent >= 0.5000 and complexity_guard:
            return (
                HotspotArchetype.BRAIN_MODULE,
                1.0,
                "Brain Module: central architectural bottleneck (centrality >= 0.50) carrying high cyclomatic complexity (CCN >= 0.70).",
            )

        # 4. Shotgun Surgery Catalyst (high coupling + central)
        if coup is not None and cent is not None and coup >= 0.6000 and cent >= 0.5000:
            return (
                HotspotArchetype.SHOTGUN_SURGERY,
                1.0,
                "Shotgun Surgery Catalyst: high coupling (coup >= 0.60) and centrality (cent >= 0.50) requiring ripple changes across dependencies.",
            )

        # 5. Stable Core (high centrality sink, low churn, low complexity)
        churn_is_low = (churn is None) or (churn <= 0.3000)
        ccn_is_low = (ccn is not None) and (ccn <= 0.3000)
        if cent is not None and cent >= 0.5000 and churn_is_low and ccn_is_low:
            return (
                HotspotArchetype.STABLE_CORE,
                1.0,
                "Stable Core: healthy, highly depended upon architectural sink with low volatility and low complexity.",
            )

        # 6. Normal Component
        return (
            HotspotArchetype.NORMAL,
            1.0,
            "Normal Component: balanced complexity, churn, and coupling within standard operating thresholds.",
        )


def compute_evidence_coverage(
    total_source_files: int = 0,
    valid_ast_files: int = 0,
    has_graph: bool = False,
    has_churn: bool = False,
    eligible_commits_count: int = 0,
    has_temporal_coupling: bool = False,
    has_structural_coupling: bool = False,
    total_classes: int = 0,
    classes_with_edges: int = 0,
) -> EvidenceCoverage:
    """
    Computes quantified analytical evidence coverage across AST, graph, and Git dimensions.
    """
    d_ast = (valid_ast_files / total_source_files) if total_source_files > 0 else 1.0
    d_graph = 1.0 if has_graph else 0.0
    d_churn = 1.0 if has_churn else 0.0
    d_temp_coup = 1.0 if (has_temporal_coupling or eligible_commits_count >= 5) else 0.0
    d_struct_coup = 1.0 if has_structural_coupling else 0.0
    d_class_graph = (classes_with_edges / total_classes) if total_classes > 0 else 1.0

    overall = (
        0.25 * d_ast
        + 0.20 * d_graph
        + 0.20 * d_churn
        + 0.15 * d_temp_coup
        + 0.10 * d_struct_coup
        + 0.10 * d_class_graph
    )
    overall = round(min(1.0, max(0.0, overall)), 4)

    missing = []
    if d_ast < 1.0:
        missing.append("INCOMPLETE_AST_PARSING")
    if not has_graph:
        missing.append("STATIC_DEPENDENCY_GRAPH_UNAVAILABLE")
    if not has_churn:
        missing.append("GIT_CHURN_HISTORY_UNAVAILABLE")
    if d_temp_coup == 0.0:
        missing.append("TEMPORAL_COUPLING_INSUFFICIENT_COMMITS")
    if not has_structural_coupling:
        missing.append("STRUCTURAL_COUPLING_UNAVAILABLE")
    if d_class_graph < 1.0:
        missing.append("CLASS_DEPENDENCY_GRAPH_PARTIAL")

    if overall >= 0.90:
        state = AnalysisState.FULL_EVIDENCE
    elif overall >= 0.55:
        state = AnalysisState.PARTIAL_STATIC_ONLY
    else:
        state = AnalysisState.DEGRADED_ANALYSIS

    return EvidenceCoverage(
        overall_coverage=overall,
        analysis_state=state,
        ast_coverage=round(d_ast, 4),
        graph_available=has_graph,
        churn_available=has_churn,
        temporal_coupling_available=(d_temp_coup == 1.0),
        structural_coupling_available=has_structural_coupling,
        class_graph_coverage=round(d_class_graph, 4),
        missing_signals=missing,
    )


class MaintenanceHotspotDetector:
    """
    High-level orchestrating engine for multi-signal maintenance hotspot analysis.
    Aggregates module entities, runs PageRank centrality, integrates Git churn
    and temporal coupling, applies 95th-percentile normalization, and classifies archetypes.
    """

    def __init__(
        self,
        scorer: Optional[MaintenanceHotspotScorer] = None,
        churn_analyzer: Optional[CodeChurnAnalyzer] = None,
        coupling_analyzer: Optional[LogicalCouplingAnalyzer] = None,
    ):
        self.scorer = scorer or MaintenanceHotspotScorer()
        self.churn_analyzer = churn_analyzer or CodeChurnAnalyzer()
        self.coupling_analyzer = coupling_analyzer or LogicalCouplingAnalyzer()

    def detect_hotspots(
        self,
        modules: Union[Dict[str, ModuleEntity], List[ModuleEntity]],
        quotient_graph: Optional[nx.DiGraph] = None,
        commits: Optional[List[CommitRecord]] = None,
        churn_summary: Optional[RepositoryChurnSummary] = None,
        temporal_couplings: Optional[List[LogicalCoupling]] = None,
        total_source_files: int = 0,
        valid_ast_files: int = 0,
    ) -> HotspotReport:
        """
        Executes end-to-end multi-signal hotspot detection over logical modules or packages.
        """
        # 1. Normalize module input mapping
        if isinstance(modules, list):
            mod_map = {m.name: m for m in modules}
        else:
            mod_map = dict(modules)

        if not mod_map:
            cov = compute_evidence_coverage(
                total_source_files=total_source_files,
                valid_ast_files=valid_ast_files,
                has_graph=False,
                has_churn=False,
            )
            return HotspotReport(
                hotspots=[],
                evidence_coverage=cov,
                analysis_state=cov.analysis_state,
                total_entities_analyzed=0,
                top_hotspot_mean=0.0,
            )

        mod_names = sorted(list(mod_map.keys()))
        q_graph = quotient_graph or nx.DiGraph()
        for m in mod_names:
            if not q_graph.has_node(m):
                q_graph.add_node(m)

        # 2. Extract Raw Metrics
        # A. Cyclomatic Complexity
        raw_ccn: Dict[str, float] = {}
        for m in mod_names:
            entity = mod_map[m]
            raw_ccn[m] = float(entity.total_complexity)

        # B. Dependency Centrality (PageRank + In-Degree on quotient graph)
        pr_scores = deterministic_pagerank(q_graph)
        raw_cent: Dict[str, float] = {}
        max_pr = max(pr_scores.values()) if pr_scores else 0.0
        n_nodes = len(mod_names)
        baseline_jump = (1.0 - 0.85) / n_nodes if n_nodes > 0 else 0.0

        for m in mod_names:
            in_deg = float(q_graph.in_degree(m))
            in_deg_norm = min(1.0, in_deg / 10.0)
            pr = pr_scores.get(m, 0.0)

            if in_deg == 0:
                pr_norm = 0.0
            else:
                if max_pr > baseline_jump:
                    pr_norm = min(1.0, max(0.0, (pr - baseline_jump) / (max_pr - baseline_jump)))
                else:
                    pr_norm = 0.0

            raw_cent[m] = round(0.5 * in_deg_norm + 0.5 * pr_norm, 4)

        # C. Git Churn Analysis
        has_git_churn = False
        raw_churn: Dict[str, Optional[float]] = {m: None for m in mod_names}

        # Resolve churn summary if commits provided
        eff_churn_summary = churn_summary
        if eff_churn_summary is None and commits:
            try:
                eff_churn_summary = self.churn_analyzer.analyze(commits)
            except Exception as e:
                logger.debug(f"Git churn analysis failed or skipped: {e}")

        file_metrics_map = (
            eff_churn_summary.get("file_metrics")
            if isinstance(eff_churn_summary, dict)
            else getattr(eff_churn_summary, "file_metrics", None)
        )
        if file_metrics_map:
            has_git_churn = True
            for m in mod_names:
                entity = mod_map[m]
                mod_churn = 0
                for f in entity.files:
                    norm_f = f.replace("\\", "/")
                    if norm_f in file_metrics_map:
                        fm = file_metrics_map[norm_f]
                        churn_val = fm.get("total_churn", 0) if isinstance(fm, dict) else getattr(fm, "total_churn", 0)
                        mod_churn += churn_val
                raw_churn[m] = float(mod_churn)

        # D. Hybrid Coupling Intensity
        # Structural coupling: in-degree + out-degree in quotient graph
        raw_coup: Dict[str, float] = {}
        eff_couplings = temporal_couplings
        eligible_commits = len(commits) if commits else 0

        if eff_couplings is None and commits and eligible_commits >= 5:
            try:
                coup_res = self.coupling_analyzer.analyze(commits)
                if coup_res.status == "success":
                    eff_couplings = coup_res.couplings
            except Exception as e:
                logger.debug(f"Logical coupling analysis skipped: {e}")

        has_temp_coup = eff_couplings is not None and len(eff_couplings) > 0

        # Precompute temporal coupling sums per file
        file_temp_coupling: Dict[str, float] = {}
        if eff_couplings:
            for c in eff_couplings:
                fa = c.get("canonical_file_a", "") if isinstance(c, dict) else getattr(c, "canonical_file_a", "")
                fb = c.get("canonical_file_b", "") if isinstance(c, dict) else getattr(c, "canonical_file_b", "")
                jacc = c.get("jaccard_similarity", 0.0) if isinstance(c, dict) else getattr(c, "jaccard_similarity", 0.0)
                file_temp_coupling[fa] = file_temp_coupling.get(fa, 0.0) + jacc
                file_temp_coupling[fb] = file_temp_coupling.get(fb, 0.0) + jacc

        for m in mod_names:
            entity = mod_map[m]
            c_struct = float(q_graph.in_degree(m) + q_graph.out_degree(m))
            c_struct_norm = min(1.0, c_struct / 20.0)

            if has_temp_coup:
                c_temp = sum(file_temp_coupling.get(f.replace("\\", "/"), 0.0) for f in entity.files)
                c_temp_norm = min(1.0, c_temp / 3.0)
                raw_coup[m] = round(0.50 * c_struct_norm + 0.50 * c_temp_norm, 4)
            else:
                raw_coup[m] = round(1.00 * c_struct_norm, 4)

        # 3. 95th-Percentile Relative Normalization
        ordered_ccn = [raw_ccn[m] for m in mod_names]
        ordered_cent = [raw_cent[m] for m in mod_names]
        ordered_churn = [raw_churn[m] for m in mod_names]
        ordered_coup = [raw_coup[m] for m in mod_names]

        norm_ccn = normalize_95th_percentile(ordered_ccn)
        norm_cent = normalize_95th_percentile(ordered_cent)
        norm_churn = normalize_95th_percentile(ordered_churn)
        norm_coup = normalize_95th_percentile(ordered_coup)

        # 4. Score Each Entity
        hotspots: List[HotspotItem] = []

        for idx, m in enumerate(mod_names):
            s_ccn = norm_ccn[idx]
            s_cent = norm_cent[idx]
            s_churn = norm_churn[idx]
            s_coup = norm_coup[idx]

            final_score, base_score, mu, eff_weights = self.scorer.calculate_hotspot_score(
                ccn=s_ccn,
                cent=s_cent,
                churn=s_churn,
                coup=s_coup,
            )

            raw_dict = {
                "complexity": int(raw_ccn[m]),
                "centrality_score": raw_cent[m],
                "churn": int(raw_churn[m]) if raw_churn[m] is not None else None,
                "coupling_intensity": raw_coup[m],
                "loc": mod_map[m].total_loc,
                "files_count": len(mod_map[m].files),
            }

            sig_avail = {
                "ccn": s_ccn is not None,
                "cent": s_cent is not None,
                "churn": s_churn is not None,
                "coup": s_coup is not None,
            }

            norm_signals = {
                "ccn": s_ccn,
                "cent": s_cent,
                "churn": s_churn,
                "coup": s_coup,
            }

            archetype, conf, rationale = self.scorer.classify_archetype(
                ccn=s_ccn,
                cent=s_cent,
                churn=s_churn,
                coup=s_coup,
                entity_type="module",
                raw_metrics=raw_dict,
            )

            item = HotspotItem(
                entity_path=m,
                entity_type="module",
                hotspot_score=final_score,
                base_score=base_score,
                multiplier=mu,
                archetype=archetype,
                raw_metrics=raw_dict,
                normalized_signals=norm_signals,
                effective_weights=eff_weights,
                signal_availability=sig_avail,
                confidence=conf,
                rationale=rationale,
            )
            hotspots.append(item)

        # 5. Deterministic Tie-Breaking & Sorting
        # Primary: hotspot_score descending, Secondary: base_score descending, Tertiary: entity_path ascending
        hotspots.sort(key=lambda h: (-h.hotspot_score, -h.base_score, h.entity_path))

        # 6. Mean Top Hotspots Calculation
        top_k = hotspots[:5]
        top_mean = round(sum(h.hotspot_score for h in top_k) / len(top_k), 4) if top_k else 0.0

        # 7. Evidence Coverage Evaluation
        cov = compute_evidence_coverage(
            total_source_files=total_source_files or sum(len(m.files) for m in mod_map.values()),
            valid_ast_files=valid_ast_files or sum(len(m.files) for m in mod_map.values()),
            has_graph=(q_graph.number_of_edges() > 0),
            has_churn=has_git_churn,
            eligible_commits_count=eligible_commits,
            has_temporal_coupling=has_temp_coup,
            has_structural_coupling=(q_graph.number_of_edges() > 0),
            total_classes=0,
            classes_with_edges=0,
        )

        return HotspotReport(
            hotspots=hotspots,
            evidence_coverage=cov,
            analysis_state=cov.analysis_state,
            total_entities_analyzed=len(hotspots),
            top_hotspot_mean=top_mean,
        )
