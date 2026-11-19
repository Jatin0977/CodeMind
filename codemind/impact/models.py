"""
Data models and type definitions for CodeMind Phase 8:
Change Impact and Test Intelligence.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, Optional, List


class TestEvidenceType(str, Enum):
    """Categorized evidence types for test discovery and prioritization."""
    __test__ = False
    DIRECT_INVOCATION = "DIRECT_INVOCATION"
    DIRECT_IMPORT = "DIRECT_IMPORT"
    HEURISTIC_NAMING = "HEURISTIC_NAMING"
    HEURISTIC_MIRRORING = "HEURISTIC_MIRRORING"
    HEURISTIC_CO_CHANGE = "HEURISTIC_CO_CHANGE"


class ImpactRiskLevel(str, Enum):
    """Categorized risk tiers based on composite impact score."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_score(cls, score: float) -> "ImpactRiskLevel":
        if score >= 0.75:
            return cls.CRITICAL
        elif score >= 0.50:
            return cls.HIGH
        elif score >= 0.25:
            return cls.MEDIUM
        return cls.LOW


# --- Domain Exceptions ---

class TargetResolutionError(Exception):
    """Base exception for all change target resolution errors."""
    pass


class AmbiguousTargetError(TargetResolutionError):
    """Raised when an unqualified symbol matches multiple candidates in the codebase."""

    def __init__(self, query: str, candidates: List[Dict[str, Any]], message: Optional[str] = None):
        self.query = query
        self.candidates = candidates
        msg = message or (
            f"Symbol '{query}' is ambiguous ({len(candidates)} candidates found). "
            f"Specify a qualified path or file location to disambiguate."
        )
        super().__init__(msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": "AmbiguousTargetError",
            "query": self.query,
            "candidate_count": len(self.candidates),
            "candidates": self.candidates,
            "message": str(self),
        }


class TargetNotFoundError(TargetResolutionError):
    """Raised when a change target cannot be resolved anywhere in the repository or graph."""

    def __init__(self, query: str, suggestions: Optional[List[str]] = None, message: Optional[str] = None):
        self.query = query
        self.suggestions = suggestions or []
        msg = message or f"Target '{query}' could not be resolved in the codebase."
        if self.suggestions:
            msg += f" Did you mean: {', '.join(self.suggestions)}?"
        super().__init__(msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": "TargetNotFoundError",
            "query": self.query,
            "suggestions": self.suggestions,
            "message": str(self),
        }


# --- Target Representation ---

@dataclass
class ChangeTarget:
    """Resolved target entity for change impact analysis."""
    node_id: str
    name: str
    entity_type: str  # file, class, function, method
    file_path: Optional[str] = None
    relative_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    resolution_method: str = "canonical_id"  # canonical_id, file_path, qualified_symbol, unqualified_symbol
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Blast Radius Representation ---

@dataclass
class BlastRadiusNode:
    """An impacted node within the reverse dependency blast radius."""
    node_id: str
    name: str
    entity_type: str
    file_path: Optional[str]
    depth: int
    direct_relationship: Optional[str]
    path: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)  # e.g. DIRECT_CALLER, COARSE_FILE_DEPENDENT, TEMPORAL_CO_CHANGE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlastRadiusEdge:
    """A directed dependency or coupling edge within the blast radius."""
    source: str
    target: str
    edge_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlastRadiusReport:
    """Complete reverse dependency reachability report."""
    target: ChangeTarget
    max_depth: int
    total_impacted: int
    impacted_nodes: List[BlastRadiusNode] = field(default_factory=list)
    impacted_edges: List[BlastRadiusEdge] = field(default_factory=list)
    counts_by_type: Dict[str, int] = field(default_factory=dict)
    counts_by_depth: Dict[int, int] = field(default_factory=dict)
    counts_by_tag: Dict[str, int] = field(default_factory=dict)
    disclaimer: str = (
        "Structural reachability traces deterministic static relationships in the AST graph "
        "and direct temporal co-change relationships. It represents static dependency, not guaranteed "
        "runtime execution probability."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "max_depth": self.max_depth,
            "total_impacted": self.total_impacted,
            "impacted_nodes": [n.to_dict() for n in self.impacted_nodes],
            "impacted_edges": [e.to_dict() for e in self.impacted_edges],
            "counts_by_type": self.counts_by_type,
            "counts_by_depth": self.counts_by_depth,
            "counts_by_tag": self.counts_by_tag,
            "disclaimer": self.disclaimer,
        }


# --- Centrality Metrics ---

@dataclass
class CentralityMetrics:
    """Graph centrality measurements computed on the pure code dependency subgraph."""
    in_degree_centrality: float
    pagerank: float
    composite_centrality: float
    betweenness_centrality: Optional[float] = None  # Diagnostic-only

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Multi-Signal Impact Scoring ---

@dataclass
class ImpactSignal:
    """Individual signal contributing to the composite impact score."""
    name: str
    raw_value: float
    normalized_score: float
    base_weight: float
    effective_weight: float
    available: bool
    description: str
    diagnostic_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImpactAnalysisConfig:
    """Configurable weights and saturation thresholds for impact analysis."""
    # Signal Weights (sum to 1.0 by default)
    w_reach: float = 0.30        # S1: Structural Reachability
    w_centrality: float = 0.20   # S2: Graph Centrality (In-Degree + PageRank)
    w_volatility: float = 0.15   # S3: Historical Volatility / Commit Frequency
    w_coupling: float = 0.15     # S4: Logical Coupling
    w_test: float = 0.10         # S5: Test Exposure Risk
    w_complexity: float = 0.10   # S6: Cyclomatic Complexity

    # Centrality weights
    w_in_degree: float = 0.60
    w_pagerank: float = 0.40

    # Saturation parameters
    reach_midpoint: float = 15.0     # M1 in logistic sigmoid
    reach_slope: float = 0.25        # k1 in logistic sigmoid
    volatility_sat: float = 20.0     # Commits threshold for S3 saturation
    complexity_sat: float = 15.0     # CCN threshold for S6 saturation
    damping_factor: float = 0.85     # PageRank damping

    # Traversal parameters
    default_max_depth: int = 3
    coupling_lambda: float = 0.25    # Temporal ranking boost for tests

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImpactReport:
    """Complete Multi-Signal Impact Assessment report."""
    target: ChangeTarget
    composite_score: float
    risk_level: str
    confidence: float
    confidence_level: str
    signals: Dict[str, ImpactSignal]
    centrality: CentralityMetrics
    blast_radius: BlastRadiusReport
    diagnostics: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "composite_score": self.composite_score,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "signals": {k: v.to_dict() for k, v in self.signals.items()},
            "centrality": self.centrality.to_dict(),
            "blast_radius": self.blast_radius.to_dict(),
            "diagnostics": self.diagnostics,
            "timestamp": self.timestamp,
        }


# --- Test Intelligence ---

@dataclass
class TestRecommendation:
    """Prioritized candidate test recommended for verifying target changes."""
    __test__ = False
    test_file: str
    test_target: str
    evidence_type: str  # TestEvidenceType
    tier: int           # 0 = target, 1 = direct dependent, 2 = transitive
    rank_score: float
    associated_source_entity: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestIntelligenceReport:
    """Comprehensive test mapping and regression test prioritization report."""
    __test__ = False
    target: ChangeTarget
    total_tests: int
    recommendations: List[TestRecommendation] = field(default_factory=list)
    tier_breakdown: Dict[int, int] = field(default_factory=dict)
    evidence_breakdown: Dict[str, int] = field(default_factory=dict)
    disclaimer: str = (
        "Test recommendations are statically derived candidates prioritized for regression testing. "
        "They do not represent dynamic execution confirmation, test execution results, or coverage guarantees."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "total_tests": self.total_tests,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "tier_breakdown": self.tier_breakdown,
            "evidence_breakdown": self.evidence_breakdown,
            "disclaimer": self.disclaimer,
        }
