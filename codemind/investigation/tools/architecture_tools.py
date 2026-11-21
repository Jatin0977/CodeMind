"""
Architecture & Risk Investigation Tools for CodeMind Agentic Investigation Engine (Phase 9, Milestone 4).
Provides standardized BaseTool implementations for architecture overview, module hierarchy,
layer-conformance checking, package cycle detection, maintenance hotspots, and evidence coverage.
"""

from typing import Dict, Any, Optional, List, Union
import logging
import networkx as nx

from .base import BaseTool, ToolResult
from ..models import ToolStatus, ToolAvailability, ToolDefinition
from ...architecture.models import (
    ModuleEntity,
    LayerDefinition,
    ConformanceReport,
    HotspotReport,
    EvidenceCoverage,
    AnalysisState,
    HotspotArchetype,
)
from ...architecture.discovery import ArchitectureDiscoveryEngine
from ...architecture.conformance import ArchitectureConformanceEngine
from ...architecture.hotspots import (
    MaintenanceHotspotDetector,
    MaintenanceHotspotScorer,
    compute_evidence_coverage,
)
from ...ingestion.models import IngestedRepository

logger = logging.getLogger(__name__)


class GetArchitectureOverviewTool(BaseTool):
    """
    Inspect repository architecture overview, logical module hierarchy, source roots,
    and inferred architectural layers.
    """

    def __init__(
        self,
        discovery_engine: Optional[ArchitectureDiscoveryEngine] = None,
        modules: Optional[Dict[str, ModuleEntity]] = None,
        layers: Optional[Dict[str, LayerDefinition]] = None,
        repo: Optional[IngestedRepository] = None,
        parsed_files: Optional[Dict[str, Any]] = None,
        quotient_graph: Optional[Any] = None,
    ):
        self.discovery_engine = discovery_engine
        self._modules = modules
        self._layers = layers
        self.repo = repo
        self.parsed_files = parsed_files
        self._quotient_graph = quotient_graph

        self._definition = ToolDefinition(
            tool_name="get_architecture_overview",
            description="Inspect high-level architecture overview, module hierarchy, source roots, and inferred architectural layer boundaries.",
            input_schema={
                "type": "object",
                "properties": {
                    "module_name": {"type": "string", "description": "Optional specific module name to filter details"},
                    "layer_name": {"type": "string", "description": "Optional layer name to filter member modules"},
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["module_discovery", "layer_inference"],
        )

    @property
    def name(self) -> str:
        return "get_architecture_overview"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        mod_filter = arguments.get("module_name")
        layer_filter = arguments.get("layer_name")

        modules_map = self._modules
        layers_map = self._layers
        source_roots: List[str] = []
        q_nodes = 0
        q_edges = 0

        # Lazy discovery if not pre-provided
        if modules_map is None and self.discovery_engine is not None:
            if self.parsed_files:
                modules_map = self.discovery_engine.discover_modules(self.parsed_files)
            else:
                modules_map = self.discovery_engine.modules
            layers_map = self.discovery_engine.layers
            source_roots = self.discovery_engine.source_roots
            q_nodes = self.discovery_engine.quotient_graph.number_of_nodes()
            q_edges = self.discovery_engine.quotient_graph.number_of_edges()
        elif modules_map is None and self.repo is not None:
            engine = ArchitectureDiscoveryEngine(repo_root=self.repo.repo_path)
            if self.parsed_files:
                modules_map = engine.discover_modules(self.parsed_files)
            else:
                modules_map = engine.modules
            layers_map = engine.layers
            source_roots = engine.source_roots
            q_nodes = engine.quotient_graph.number_of_nodes()
            q_edges = engine.quotient_graph.number_of_edges()

        modules_map = modules_map or {}
        layers_map = layers_map or {}

        # Filter modules if requested
        formatted_modules = []
        for m_name, m_entity in sorted(modules_map.items()):
            if mod_filter and mod_filter.lower() not in m_name.lower():
                continue
            if layer_filter and layer_filter.lower() != m_entity.inferred_layer.lower():
                continue

            formatted_modules.append({
                "name": m_entity.name,
                "relative_dir": m_entity.relative_dir,
                "layer": m_entity.inferred_layer,
                "confidence": round(m_entity.inference_confidence, 2),
                "files_count": len(m_entity.files),
                "total_loc": m_entity.total_loc,
                "total_complexity": m_entity.total_complexity,
                "files": list(m_entity.files)[:20],
                "internal_dependencies": list(m_entity.internal_dependencies),
                "external_dependencies": list(m_entity.external_dependencies),
            })

        formatted_layers = []
        for l_name, l_def in sorted(layers_map.items(), key=lambda kv: kv[1].level):
            formatted_layers.append({
                "name": l_def.name,
                "level": l_def.level,
                "modules": list(l_def.modules),
                "allowed_dependencies": list(l_def.allowed_dependencies),
                "forbidden_dependencies": list(l_def.forbidden_dependencies),
            })

        data = {
            "source_roots": source_roots,
            "total_modules": len(modules_map),
            "matched_modules_count": len(formatted_modules),
            "total_layers": len(layers_map),
            "modules": formatted_modules,
            "layers": formatted_layers,
            "quotient_graph": {
                "nodes_count": q_nodes,
                "edges_count": q_edges,
            },
        }

        msg = (
            f"Architecture overview: {len(modules_map)} logical modules across "
            f"{len(layers_map)} architectural layers."
        )
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=data,
            message=msg,
            metadata={"matched_modules": len(formatted_modules)},
        )


class CheckArchitectureConformanceTool(BaseTool):
    """
    Validate architectural layering and dependency conformance against configured architectural
    boundaries, calculating the Architecture Conformance Index (ACI) and line-level violations.
    """

    def __init__(
        self,
        conformance_engine: Optional[ArchitectureConformanceEngine] = None,
        discovery_engine: Optional[ArchitectureDiscoveryEngine] = None,
        parsed_files: Optional[Dict[str, Any]] = None,
        layers: Optional[Dict[str, LayerDefinition]] = None,
        modules: Optional[Dict[str, ModuleEntity]] = None,
        quotient_graph: Optional[Any] = None,
    ):
        self.conformance_engine = conformance_engine
        self.discovery_engine = discovery_engine
        self.parsed_files = parsed_files
        self._layers = layers
        self._modules = modules
        self._quotient_graph = quotient_graph

        self._definition = ToolDefinition(
            tool_name="check_architecture_conformance",
            description="Validate architectural layering and dependency conformance against configured architectural boundaries, calculating the Architecture Conformance Index (ACI).",
            input_schema={
                "type": "object",
                "properties": {
                    "strict_layering": {
                        "type": "boolean",
                        "default": False,
                        "description": "If True, flags non-adjacent layer skipping as WARNING violations",
                    },
                    "module": {
                        "type": "string",
                        "description": "Optional module name filter to inspect violations involving specific module",
                    },
                    "severity": {
                        "type": "string",
                        "description": "Optional severity filter ('CRITICAL', 'WARNING', 'INFO')",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["conformance_engine", "layer_definitions"],
        )

    @property
    def name(self) -> str:
        return "check_architecture_conformance"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        strict_layering = bool(arguments.get("strict_layering", False))
        mod_filter = arguments.get("module")
        severity_filter = arguments.get("severity")

        engine = self.conformance_engine
        if engine is None:
            # Initialize from discovery engine or explicit modules/layers/quotient_graph
            modules_map = self._modules or (self.discovery_engine.modules if self.discovery_engine else None)
            layers_map = self._layers or (self.discovery_engine.layers if self.discovery_engine else None)
            q_graph = self._quotient_graph or (self.discovery_engine.quotient_graph if self.discovery_engine else None)
            engine = ArchitectureConformanceEngine(
                layers=layers_map,
                modules_map=modules_map,
                quotient_graph=q_graph,
            )

        report: ConformanceReport = engine.evaluate(
            parsed_files=self.parsed_files,
            strict_layering=strict_layering,
        )

        # Filter violations
        filtered_violations = []
        for v in report.violations:
            if mod_filter:
                f_low = mod_filter.lower()
                if f_low not in v.source_module.lower() and f_low not in v.target_module.lower():
                    continue
            if severity_filter:
                sev_val = v.severity.value if hasattr(v.severity, "value") else str(v.severity)
                if sev_val.upper() != severity_filter.upper():
                    continue

            filtered_violations.append({
                "violation_type": v.violation_type,
                "severity": v.severity.value if hasattr(v.severity, "value") else str(v.severity),
                "source_file": v.source_file,
                "target_file": v.target_file,
                "source_module": v.source_module,
                "target_module": v.target_module,
                "source_layer": v.source_layer,
                "target_layer": v.target_layer,
                "line_number": v.line_number,
                "statement": v.import_statement,
                "rule_description": v.rule_description,
                "weight": v.weight,
            })

        data = {
            "conformance_index": report.conformance_index,
            "conformance_numerator": report.conformance_numerator,
            "total_evaluated_edges": report.total_evaluated_edges,
            "violating_edges_count": report.violating_edges_count,
            "is_compliant": (len(report.violations) == 0),
            "violations_count": len(filtered_violations),
            "total_violations_in_repo": len(report.violations),
            "violations": filtered_violations,
            "package_cycles": report.package_cycles,
        }

        msg = (
            f"Architecture conformance index (ACI): {report.conformance_index:.2f}%. "
            f"Found {len(filtered_violations)} violation(s) across {report.total_evaluated_edges} cross-module edges."
        )
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=data,
            message=msg,
            metadata={
                "conformance_index": report.conformance_index,
                "violating_edges_count": report.violating_edges_count,
            },
        )


class DetectPackageCyclesTool(BaseTool):
    """
    Detect circular dependencies between logical packages and modules using Tarjan's strongly
    connected components algorithm on the module quotient graph G_M.
    """

    def __init__(
        self,
        conformance_engine: Optional[ArchitectureConformanceEngine] = None,
        quotient_graph: Optional[nx.DiGraph] = None,
        modules: Optional[Any] = None,
    ):
        self.conformance_engine = conformance_engine
        self.quotient_graph = quotient_graph
        self.modules = modules

        self._definition = ToolDefinition(
            tool_name="detect_package_cycles",
            description="Detect cyclic dependencies between logical packages and modules using Tarjan's strongly connected components algorithm on the module quotient graph.",
            input_schema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "Optional module name filter to locate cycles involving this package"},
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["cycle_detector", "quotient_graph"],
        )

    @property
    def name(self) -> str:
        return "detect_package_cycles"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        mod_filter = arguments.get("module")

        engine = self.conformance_engine
        if engine is None:
            engine = ArchitectureConformanceEngine(quotient_graph=self.quotient_graph)

        cycles = engine.detect_package_cycles()
        sccs = engine.detect_package_sccs()

        # Apply module filter if present
        if mod_filter:
            m_low = mod_filter.lower()
            cycles = [c for c in cycles if any(m_low in str(m).lower() for m in c)]
            sccs = [s for s in sccs if any(m_low in str(m).lower() for m in s)]

        formatted_cycles = [
            {"cycle_path": c, "length": len(c), "modules": c}
            for c in cycles
        ]
        formatted_sccs = [
            {"component": s, "size": len(s)}
            for s in sccs
        ]

        data = {
            "total_cycles": len(formatted_cycles),
            "total_sccs": len(formatted_sccs),
            "has_cycles": len(formatted_cycles) > 0,
            "cycles": formatted_cycles,
            "strongly_connected_components": formatted_sccs,
        }

        msg = f"Detected {len(formatted_cycles)} package cycle(s) across {len(formatted_sccs)} strongly connected component(s)."
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=data,
            message=msg,
            metadata={"cycle_count": len(formatted_cycles)},
        )


class DetectMaintenanceHotspotsTool(BaseTool):
    """
    Identify maintenance hotspots by cross-referencing code churn, cyclomatic complexity,
    dependency centrality, and hybrid coupling, classifying debt archetypes.
    """

    def __init__(
        self,
        hotspot_detector: Optional[MaintenanceHotspotDetector] = None,
        modules: Optional[Union[Dict[str, ModuleEntity], List[ModuleEntity]]] = None,
        quotient_graph: Optional[nx.DiGraph] = None,
        commits: Optional[List[Any]] = None,
        churn_summary: Optional[Any] = None,
        temporal_couplings: Optional[List[Any]] = None,
        total_source_files: int = 0,
        valid_ast_files: int = 0,
        discovery_engine: Optional[Any] = None,
        parsed_files: Optional[Dict[str, Any]] = None,
        churn_analyzer: Optional[Any] = None,
        coupling_analyzer: Optional[Any] = None,
    ):
        self.hotspot_detector = hotspot_detector or MaintenanceHotspotDetector()
        self.modules = modules
        self.quotient_graph = quotient_graph
        self.commits = commits
        self.churn_summary = churn_summary
        self.temporal_couplings = temporal_couplings
        self.total_source_files = total_source_files
        self.valid_ast_files = valid_ast_files
        self.discovery_engine = discovery_engine
        self.parsed_files = parsed_files
        self.churn_analyzer = churn_analyzer
        self.coupling_analyzer = coupling_analyzer

        self._definition = ToolDefinition(
            tool_name="detect_maintenance_hotspots",
            description="Identify maintenance hotspots by cross-referencing code churn, cyclomatic complexity, and centrality.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10, "description": "Maximum hotspots to return"},
                    "archetype": {"type": "string", "description": "Optional archetype filter (e.g. 'Brain Module', 'Volatile Fragile Hotspot')"},
                    "module": {"type": "string", "description": "Optional module name filter"},
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["hotspot_detector", "complexity_analyzer", "churn_analyzer"],
        )

    @property
    def name(self) -> str:
        return "detect_maintenance_hotspots"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        limit = int(arguments.get("limit", 10))
        archetype_filter = arguments.get("archetype")
        mod_filter = arguments.get("module")

        modules_input = self.modules
        if modules_input is None and self.discovery_engine is not None:
            modules_input = self.discovery_engine.modules
        if modules_input is None:
            modules_input = {}

        q_graph = self.quotient_graph
        if q_graph is None and self.discovery_engine is not None:
            q_graph = self.discovery_engine.quotient_graph

        report: HotspotReport = self.hotspot_detector.detect_hotspots(
            modules=modules_input,
            quotient_graph=q_graph,
            commits=self.commits,
            churn_summary=self.churn_summary,
            temporal_couplings=self.temporal_couplings,
            total_source_files=self.total_source_files,
            valid_ast_files=self.valid_ast_files,
        )

        filtered_hotspots = []
        for h in report.hotspots:
            if mod_filter and mod_filter.lower() not in h.entity_path.lower():
                continue
            arch_str = h.archetype.value if hasattr(h.archetype, "value") else str(h.archetype)
            if archetype_filter and archetype_filter.lower() not in arch_str.lower():
                continue

            filtered_hotspots.append({
                "entity_path": h.entity_path,
                "entity_type": h.entity_type,
                "hotspot_score": h.hotspot_score,
                "base_score": h.base_score,
                "multiplier": h.multiplier,
                "archetype": arch_str,
                "confidence": h.confidence,
                "raw_metrics": h.raw_metrics,
                "normalized_signals": h.normalized_signals,
                "effective_weights": h.effective_weights,
                "signal_availability": h.signal_availability,
                "rationale": h.rationale,
            })

        data = {
            "total_analyzed": report.total_entities_analyzed,
            "matched_hotspots_count": len(filtered_hotspots),
            "top_hotspot_mean": report.top_hotspot_mean,
            "repository_risk_score": report.top_hotspot_mean,
            "analysis_state": report.analysis_state.value if hasattr(report.analysis_state, "value") else str(report.analysis_state),
            "hotspots": filtered_hotspots[:limit],
            "evidence_coverage": report.evidence_coverage.to_dict() if report.evidence_coverage else None,
        }

        msg = (
            f"Hotspot analysis: {len(filtered_hotspots)} hotspot(s) identified "
            f"(Top Mean: {report.top_hotspot_mean:.2f}). State: {data['analysis_state']}."
        )
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=data,
            message=msg,
            metadata={
                "top_hotspot_mean": report.top_hotspot_mean,
                "analysis_state": data["analysis_state"],
            },
        )


class GetEvidenceCoverageTool(BaseTool):
    """
    Inspect the multi-dimensional analytical evidence coverage matrix and operational limitations
    across AST, dependency graph, and Git temporal layers.
    """

    def __init__(
        self,
        evidence_coverage: Optional[EvidenceCoverage] = None,
        total_source_files: int = 0,
        valid_ast_files: int = 0,
        has_graph: bool = False,
        has_churn: bool = False,
        eligible_commits_count: int = 0,
        has_structural_coupling: bool = False,
        total_classes: int = 0,
        classes_with_edges: int = 0,
    ):
        self._coverage = evidence_coverage
        self.total_source_files = total_source_files
        self.valid_ast_files = valid_ast_files
        self.has_graph = has_graph
        self.has_churn = has_churn
        self.eligible_commits_count = eligible_commits_count
        self.has_structural_coupling = has_structural_coupling
        self.total_classes = total_classes
        self.classes_with_edges = classes_with_edges

        self._definition = ToolDefinition(
            tool_name="get_evidence_coverage",
            description="Inspect the multi-dimensional evidence coverage matrix, active analytical signals, and operational limitations across AST, dependency graph, and Git temporal layers.",
            input_schema={"type": "object"},
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["evidence_coverage"],
        )

    @property
    def name(self) -> str:
        return "get_evidence_coverage"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        cov = self._coverage
        if cov is None:
            cov = compute_evidence_coverage(
                total_source_files=self.total_source_files,
                valid_ast_files=self.valid_ast_files,
                has_graph=self.has_graph,
                has_churn=self.has_churn,
                eligible_commits_count=self.eligible_commits_count,
                has_structural_coupling=self.has_structural_coupling,
                total_classes=self.total_classes,
                classes_with_edges=self.classes_with_edges,
            )

        state_str = cov.analysis_state.value if hasattr(cov.analysis_state, "value") else str(cov.analysis_state)
        data = {
            "overall_coverage": cov.overall_coverage,
            "analysis_state": state_str,
            "dimensions": {
                "ast_coverage": cov.ast_coverage,
                "graph_available": cov.graph_available,
                "churn_available": cov.churn_available,
                "temporal_coupling_available": cov.temporal_coupling_available,
                "structural_coupling_available": cov.structural_coupling_available,
                "class_graph_coverage": cov.class_graph_coverage,
            },
            "missing_signals": list(cov.missing_signals),
            "is_full_evidence": (cov.analysis_state == AnalysisState.FULL_EVIDENCE),
            "is_degraded": (cov.analysis_state == AnalysisState.DEGRADED_ANALYSIS),
        }

        msg = (
            f"Evidence coverage: {cov.overall_coverage * 100:.1f}% ({state_str}). "
            f"Missing signals: {len(cov.missing_signals)}."
        )
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=data,
            message=msg,
            metadata={"analysis_state": state_str, "overall_coverage": cov.overall_coverage},
        )
