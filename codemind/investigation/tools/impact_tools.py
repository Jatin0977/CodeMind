"""
Impact and Test Intelligence tools for CodeMind Agentic Investigation Engine (Phase 8, Milestone 4).
Provides standardized BaseTool wrappers for multi-signal impact analysis and test mapping.
"""

from typing import Dict, Any, Optional, List
import networkx as nx

from .base import BaseTool, ToolResult
from ..models import ToolStatus, ToolAvailability, ToolDefinition
from ...impact.models import (
    AmbiguousTargetError,
    TargetNotFoundError,
    TargetResolutionError,
    ImpactAnalysisConfig,
)
from ...impact.resolver import ChangeTargetResolver
from ...impact.engine import ChangeImpactEngine
from ...impact.scorer import MultiSignalImpactScorer
from ...impact.test_intelligence import TestIntelligenceEngine


class MultiSignalImpactTool(BaseTool):
    """
    Calculate explainable Multi-Signal Impact Score combining structural reach,
    graph centrality, historical churn, logical coupling, test exposure, and complexity.
    """

    def __init__(
        self,
        graph: Optional[nx.DiGraph] = None,
        query_engine: Optional[Any] = None,
        impact_engine: Optional[ChangeImpactEngine] = None,
        scorer: Optional[MultiSignalImpactScorer] = None,
        test_engine: Optional[TestIntelligenceEngine] = None,
        coupling_analyzer: Optional[Any] = None,
        churn_analyzer: Optional[Any] = None,
        has_git: bool = False,
        total_repo_commits: int = 0,
        has_tests: bool = False,
        config: Optional[ImpactAnalysisConfig] = None,
    ):
        self.graph = graph or (getattr(query_engine, "graph", None) if query_engine else None)
        self.config = config or ImpactAnalysisConfig()

        if impact_engine:
            self.impact_engine = impact_engine
        elif self.graph is not None:
            self.impact_engine = ChangeImpactEngine(
                self.graph,
                config=self.config,
                coupling_analyzer=coupling_analyzer,
            )
        else:
            self.impact_engine = None

        if test_engine:
            self.test_engine = test_engine
        elif self.graph is not None:
            self.test_engine = TestIntelligenceEngine(
                self.graph,
                config=self.config,
                coupling_analyzer=coupling_analyzer,
            )
        else:
            self.test_engine = None

        if scorer:
            self.scorer = scorer
        else:
            self.scorer = MultiSignalImpactScorer(
                config=self.config,
                churn_analyzer=churn_analyzer,
                coupling_analyzer=coupling_analyzer,
                has_git=has_git,
                total_repo_commits=total_repo_commits,
                has_tests=has_tests,
            )

        self._resolver = ChangeTargetResolver(self.graph) if self.graph is not None else None

        self._definition = ToolDefinition(
            tool_name="multi_signal_impact",
            description="Calculate explainable Multi-Signal Impact Score combining structural reach, centrality, churn, coupling, test exposure, and complexity.",
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Target entity node ID, file path, or qualified/unqualified symbol name",
                    },
                    "max_depth": {
                        "type": "integer",
                        "default": 3,
                        "description": "Maximum traversal depth for reverse dependency reachability",
                    },
                    "include_temporal": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include strictly 1-hop logical co-change coupling",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph", "impact_engine", "multi_signal_ranker"],
        )

    @property
    def name(self) -> str:
        return "multi_signal_impact"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.graph is None or self.impact_engine is None or self._resolver is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph or ChangeImpactEngine is not initialized.",
            )

        query = str(arguments.get("node_id", "")).strip()
        if not query:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'node_id' cannot be empty.")

        max_depth = arguments.get("max_depth", self.config.default_max_depth)
        include_temporal = bool(arguments.get("include_temporal", True))

        # 1. Resolve Target
        try:
            target = self._resolver.resolve(query)
        except AmbiguousTargetError as err:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=err.to_dict(),
                message=str(err),
                metadata={"error_type": "AmbiguousTargetError", "query": query},
            )
        except TargetNotFoundError as err:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=err.to_dict(),
                message=str(err),
                metadata={"error_type": "TargetNotFoundError", "query": query},
            )
        except Exception as ex:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message=f"Target resolution failed: {str(ex)}",
            )

        # 2. Analyze Blast Radius & Centrality
        blast_radius = self.impact_engine.analyze_blast_radius(
            target=target,
            max_depth=max_depth,
            include_temporal=include_temporal,
        )
        centrality = self.impact_engine.compute_centrality(target.node_id)

        # 3. Analyze Test Intelligence
        test_report = None
        if self.test_engine:
            test_report = self.test_engine.analyze_tests(target, blast_radius)

        # 4. Synthesize Multi-Signal Impact
        impact_report = self.scorer.compute_impact(
            target=target,
            blast_radius=blast_radius,
            centrality=centrality,
            test_report=test_report,
        )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=impact_report.to_dict(),
            message=(
                f"Multi-Signal Impact for '{target.name}' resolved to risk level {impact_report.risk_level} "
                f"(composite score: {impact_report.composite_score:.2f}, "
                f"reachable dependents: {blast_radius.total_impacted})."
            ),
            metadata={
                "target_node_id": target.node_id,
                "composite_score": impact_report.composite_score,
                "risk_level": impact_report.risk_level,
                "confidence": impact_report.confidence,
            },
        )


class GetTestCoverageTool(BaseTool):
    """
    Map code entities to direct and heuristically inferred automated test suites
    and regression paths across the blast radius.
    """

    def __init__(
        self,
        graph: Optional[nx.DiGraph] = None,
        query_engine: Optional[Any] = None,
        impact_engine: Optional[ChangeImpactEngine] = None,
        test_engine: Optional[TestIntelligenceEngine] = None,
        coupling_analyzer: Optional[Any] = None,
        config: Optional[ImpactAnalysisConfig] = None,
    ):
        self.graph = graph or (getattr(query_engine, "graph", None) if query_engine else None)
        self.config = config or ImpactAnalysisConfig()

        if impact_engine:
            self.impact_engine = impact_engine
        elif self.graph is not None:
            self.impact_engine = ChangeImpactEngine(
                self.graph,
                config=self.config,
                coupling_analyzer=coupling_analyzer,
            )
        else:
            self.impact_engine = None

        if test_engine:
            self.test_engine = test_engine
        elif self.graph is not None:
            self.test_engine = TestIntelligenceEngine(
                self.graph,
                config=self.config,
                coupling_analyzer=coupling_analyzer,
            )
        else:
            self.test_engine = None

        self._resolver = ChangeTargetResolver(self.graph) if self.graph is not None else None

        self._definition = ToolDefinition(
            tool_name="get_test_coverage",
            description="Map code entities to direct and heuristically inferred automated test suites and regression paths.",
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Target entity node ID, file path, or qualified/unqualified symbol name",
                    },
                    "max_depth": {
                        "type": "integer",
                        "default": 3,
                        "description": "Maximum traversal depth for blast radius test mapping",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph", "test_mapper", "coverage_analyzer"],
        )

    @property
    def name(self) -> str:
        return "get_test_coverage"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.graph is None or self.impact_engine is None or self.test_engine is None or self._resolver is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph or TestIntelligenceEngine is not initialized.",
            )

        query = str(arguments.get("node_id", "")).strip()
        if not query:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'node_id' cannot be empty.")

        max_depth = arguments.get("max_depth", self.config.default_max_depth)

        # 1. Resolve Target
        try:
            target = self._resolver.resolve(query)
        except AmbiguousTargetError as err:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=err.to_dict(),
                message=str(err),
                metadata={"error_type": "AmbiguousTargetError", "query": query},
            )
        except TargetNotFoundError as err:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=err.to_dict(),
                message=str(err),
                metadata={"error_type": "TargetNotFoundError", "query": query},
            )
        except Exception as ex:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message=f"Target resolution failed: {str(ex)}",
            )

        # 2. Analyze Blast Radius
        blast_radius = self.impact_engine.analyze_blast_radius(
            target=target,
            max_depth=max_depth,
        )

        # 3. Analyze Test Intelligence
        test_report = self.test_engine.analyze_tests(target, blast_radius)

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=test_report.to_dict(),
            message=(
                f"Discovered {test_report.total_tests} prioritized test recommendation(s) "
                f"for target '{target.name}' across blast radius tiers."
            ),
            metadata={
                "target_node_id": target.node_id,
                "total_tests": test_report.total_tests,
                "tier_breakdown": test_report.tier_breakdown,
            },
        )
