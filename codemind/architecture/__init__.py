"""
CodeMind Architecture & Risk Insights Subsystem (Phase 9).
Provides AST-based cyclomatic complexity analysis, package hierarchy discovery,
architecture conformance checking, and multi-signal maintenance hotspot detection.
"""

from .models import (
    ViolationSeverity,
    AnalysisState,
    HotspotArchetype,
    SymbolComplexity,
    ComplexityMetrics,
    ModuleEntity,
    LayerDefinition,
    UnresolvedImport,
    EvidenceCoverage,
    ConformanceViolation,
    ConformanceReport,
    HotspotItem,
    HotspotReport,
)
from .complexity import ComplexityAnalyzer, SubtreeComplexityVisitor
from .discovery import (
    ArchitectureDiscoveryEngine,
    SourceRootResolver,
    DependencyManifestParser,
    normalize_dependency_name,
    KNOWN_MODULE_DISCREPANCIES,
)
from .conformance import ArchitectureConformanceEngine
from .hotspots import (
    MaintenanceHotspotScorer,
    MaintenanceHotspotDetector,
    deterministic_pagerank,
    normalize_95th_percentile,
)

__all__ = [
    "ViolationSeverity",
    "AnalysisState",
    "HotspotArchetype",
    "SymbolComplexity",
    "ComplexityMetrics",
    "ModuleEntity",
    "LayerDefinition",
    "UnresolvedImport",
    "EvidenceCoverage",
    "ConformanceViolation",
    "ConformanceReport",
    "HotspotItem",
    "HotspotReport",
    "ComplexityAnalyzer",
    "SubtreeComplexityVisitor",
    "ArchitectureDiscoveryEngine",
    "SourceRootResolver",
    "DependencyManifestParser",
    "normalize_dependency_name",
    "KNOWN_MODULE_DISCREPANCIES",
    "ArchitectureConformanceEngine",
    "MaintenanceHotspotScorer",
    "MaintenanceHotspotDetector",
    "deterministic_pagerank",
    "normalize_95th_percentile",
]
