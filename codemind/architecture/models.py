"""
Data models and interfaces for CodeMind Phase 9 (Advanced Architecture and Risk Insights).
Includes complexity metrics, module entities, layer definitions, and evidence coverage.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Set, Any, Tuple


class ViolationSeverity(str, Enum):
    """Severity levels for architectural rule violations."""
    CRITICAL = "CRITICAL"  # Forbidden upward layer leak or prohibited boundary
    WARNING = "WARNING"    # Strict layer skipping or boundary warning
    INFO = "INFO"          # Informational diagnostic or unclassified dependency


class AnalysisState(str, Enum):
    """System-level data evidence state for architecture intelligence."""
    FULL_EVIDENCE = "FULL_EVIDENCE"              # All AST, graph, and Git signals active
    PARTIAL_STATIC_ONLY = "PARTIAL_STATIC_ONLY"  # Static AST and graph active; Git temporal uninitialized
    DEGRADED_ANALYSIS = "DEGRADED_ANALYSIS"      # Parse errors, missing dependencies, or empty graph


class HotspotArchetype(str, Enum):
    """Archetypal classifications of architectural debt and maintenance fragility."""
    GOD_CLASS = "God Class"
    GOD_CLASS_CANDIDATE = "God Class Candidate"
    BRAIN_MODULE = "Brain Module"
    VOLATILE_FRAGILE = "Volatile Fragile Hotspot"
    SHOTGUN_SURGERY = "Shotgun Surgery Catalyst"
    STABLE_CORE = "Stable Core"
    NORMAL = "Normal Component"


@dataclass
class SymbolComplexity:
    """Cyclomatic complexity metrics for an individual callable code symbol."""
    name: str
    symbol_type: str              # "function", "method", "closure"
    start_line: int
    end_line: int
    complexity: int
    parent_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComplexityMetrics:
    """Aggregate cyclomatic complexity metrics for a parsed source file."""
    file_path: str
    relative_path: str
    script_complexity: int        # Complexity of code outside functions/classes
    file_complexity: int          # Aggregate complexity of entire file
    max_symbol_complexity: int
    symbols: List[SymbolComplexity] = field(default_factory=list)
    is_valid: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["symbols"] = [s.to_dict() for s in self.symbols]
        return data


@dataclass
class ModuleEntity:
    """Logical architectural package or module aggregating physical source files."""
    name: str                                           # e.g., "codemind.chunking"
    relative_dir: str                                   # e.g., "codemind/chunking"
    files: List[str] = field(default_factory=list)      # Relative file paths
    inferred_layer: str = "UNCLASSIFIED"                # Assigned architectural layer
    inference_confidence: float = 0.0                   # [0.0, 1.0]
    inference_evidence: List[str] = field(default_factory=list)
    total_loc: int = 0
    total_complexity: int = 0
    internal_dependencies: List[str] = field(default_factory=list) # Target internal modules
    external_dependencies: List[str] = field(default_factory=list) # Third-party / stdlib packages

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LayerDefinition:
    """Architectural layer boundary with ordinal level and allowed/forbidden dependencies."""
    name: str                                           # e.g., "Presentation"
    level: int                                          # Ordinal level (1 = highest abstraction)
    modules: List[str] = field(default_factory=list)    # Member module names
    allowed_dependencies: List[str] = field(default_factory=list)
    forbidden_dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnresolvedImport:
    """Diagnostic record for an import that cannot be resolved to disk or manifests."""
    source_file: str
    line_number: int
    raw_statement: str
    target_module: str
    reason: str  # "MODULE_NOT_FOUND_ON_DISK", "BROKEN_RELATIVE_PATH", etc.

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceCoverage:
    """Quantified data coverage across all analytical dimensions."""
    overall_coverage: float             # [0.0, 1.0]
    analysis_state: AnalysisState
    ast_coverage: float                 # D_ast
    graph_available: bool               # D_graph
    churn_available: bool               # D_churn
    temporal_coupling_available: bool   # D_temp_coup
    structural_coupling_available: bool # D_struct_coup
    class_graph_coverage: float         # D_class_graph
    missing_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["analysis_state"] = self.analysis_state.value
        return data


@dataclass
class ConformanceViolation:
    """Represents a specific architectural rule violation on an import."""
    violation_type: str                 # "UPWARD_LAYER_LEAK", "FORBIDDEN_IMPORT", "LAYER_SKIPPING"
    severity: ViolationSeverity
    source_file: str
    target_file: str
    source_module: str
    target_module: str
    source_layer: str
    target_layer: str
    line_number: int
    import_statement: str
    rule_description: str
    weight: float

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass
class ConformanceReport:
    """Comprehensive architecture conformance analysis results and metrics."""
    conformance_index: float                        # ACI in [0.0, 100.0]
    conformance_numerator: float                    # Sum of max edge violation weights
    total_evaluated_edges: int                      # Count of unique directed cross-module file edges
    violations: List[ConformanceViolation]          # Detailed line-level violations
    violating_edges_count: int                      # Count of unique file edges with violations
    package_cycles: List[List[str]] = field(default_factory=list) # Independent ADP package cycles (directed paths)
    package_sccs: List[List[str]] = field(default_factory=list)   # Strongly connected component clusters

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conformance_index": self.conformance_index,
            "conformance_numerator": self.conformance_numerator,
            "total_evaluated_edges": self.total_evaluated_edges,
            "violations": [v.to_dict() for v in self.violations],
            "violating_edges_count": self.violating_edges_count,
            "package_cycles": self.package_cycles,
            "package_sccs": self.package_sccs,
        }


@dataclass
class HotspotItem:
    """Detailed multi-signal maintenance risk assessment for an entity (module, file, or class)."""
    entity_path: str                              # Relative file path or module name
    entity_type: str                              # "module", "file", "class"
    hotspot_score: float                          # Final clamped score in [0.0, 1.0]
    base_score: float                             # Weighted linear combination before multiplier
    multiplier: float                             # Non-linear interaction multiplier in [1.0, 1.5]
    archetype: HotspotArchetype                   # Categorized debt archetype
    raw_metrics: Dict[str, Any] = field(default_factory=dict) # Physical measurements (raw_ccn, churn, etc.)
    normalized_signals: Dict[str, Optional[float]] = field(default_factory=dict) # [0.0, 1.0]
    effective_weights: Dict[str, float] = field(default_factory=dict) # Active signal weights
    signal_availability: Dict[str, bool] = field(default_factory=dict)
    confidence: float = 1.0                       # 1.0 for confirmed, 0.5 for candidate
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["archetype"] = self.archetype.value
        return data


@dataclass
class HotspotReport:
    """Repository-wide hotspot detection and evidence coverage report."""
    hotspots: List[HotspotItem] = field(default_factory=list)
    evidence_coverage: Optional[EvidenceCoverage] = None
    analysis_state: AnalysisState = AnalysisState.FULL_EVIDENCE
    total_entities_analyzed: int = 0
    top_hotspot_mean: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hotspots": [h.to_dict() for h in self.hotspots],
            "evidence_coverage": self.evidence_coverage.to_dict() if self.evidence_coverage else None,
            "analysis_state": self.analysis_state.value,
            "total_entities_analyzed": self.total_entities_analyzed,
            "top_hotspot_mean": self.top_hotspot_mean,
        }
