"""
Graph tools for CodeMind Agentic Investigation Engine (Phase 6, Milestone 2).
Provides standardized BaseTool wrappers for callers, callees, dependencies, dependents,
cycle detection, and structural impact analysis using the existing GraphQueryEngine.
"""

from typing import Dict, Any, Optional, List

from .base import BaseTool, ToolResult
from ..models import ToolStatus, ToolAvailability, ToolDefinition
from ...graph.query import GraphQueryEngine
from ...graph.models import EdgeType


class GetCallersTool(BaseTool):
    """Find all callers invoking a given function or method node."""

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="get_callers",
            description="Find all functions and methods that call the specified function or method node.",
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Canonical node identifier of the callee (e.g., 'function:codemind/auth.py:verify_token')",
                    }
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "get_callers"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        node_id = str(arguments.get("node_id", "")).strip()
        if not node_id:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'node_id' cannot be empty.")

        if node_id not in self.query_engine.graph:
            return ToolResult(
                status=ToolStatus.ERROR,
                data={"node_id": node_id, "total_callers": 0, "callers": []},
                message=f"Node '{node_id}' not found in knowledge graph.",
                metadata={"node_id": node_id, "found": False},
            )

        callers = self.query_engine.get_callers(node_id)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "node_id": node_id,
                "total_callers": len(callers),
                "callers": callers,
            },
            message=f"Found {len(callers)} caller(s) for '{node_id}'.",
            metadata={"node_id": node_id, "relationship": EdgeType.CALLS},
        )


class GetCalleesTool(BaseTool):
    """Find all callees invoked by a given function or method node."""

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="get_callees",
            description="Find all functions and methods invoked by the specified function or method node.",
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Canonical node identifier of the caller (e.g., 'function:codemind/cli.py:main')",
                    }
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "get_callees"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        node_id = str(arguments.get("node_id", "")).strip()
        if not node_id:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'node_id' cannot be empty.")

        if node_id not in self.query_engine.graph:
            return ToolResult(
                status=ToolStatus.ERROR,
                data={"node_id": node_id, "total_callees": 0, "callees": []},
                message=f"Node '{node_id}' not found in knowledge graph.",
                metadata={"node_id": node_id, "found": False},
            )

        callees = self.query_engine.get_callees(node_id)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "node_id": node_id,
                "total_callees": len(callees),
                "callees": callees,
            },
            message=f"Found {len(callees)} callee(s) for '{node_id}'.",
            metadata={"node_id": node_id, "relationship": EdgeType.CALLS},
        )


class GetDependenciesTool(BaseTool):
    """Find outgoing dependencies (IMPORTS, CALLS, INHERITS) for a given node."""

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="get_dependencies",
            description="Find outgoing dependencies (modules imported, functions called, base classes) for a node.",
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Source node identifier",
                    },
                    "direct_only": {
                        "type": "boolean",
                        "default": True,
                        "description": "If True, only direct dependencies; if False, transitive dependencies",
                    },
                    "edge_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional edge types filter (e.g. ['IMPORTS', 'CALLS', 'INHERITS'])",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "get_dependencies"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        node_id = str(arguments.get("node_id", "")).strip()
        if not node_id:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'node_id' cannot be empty.")

        if node_id not in self.query_engine.graph:
            return ToolResult(
                status=ToolStatus.ERROR,
                data={"node_id": node_id, "total_dependencies": 0, "dependencies": []},
                message=f"Node '{node_id}' not found in knowledge graph.",
                metadata={"node_id": node_id, "found": False},
            )

        direct_only = bool(arguments.get("direct_only", True))
        edge_types = arguments.get("edge_types")

        deps = self.query_engine.get_dependencies(
            node_id=node_id,
            edge_types=edge_types,
            direct_only=direct_only,
        )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "node_id": node_id,
                "direct_only": direct_only,
                "total_dependencies": len(deps),
                "dependencies": deps,
            },
            message=f"Found {len(deps)} {'direct' if direct_only else 'transitive'} dependency/dependencies for '{node_id}'.",
            metadata={"node_id": node_id, "direct_only": direct_only},
        )


class GetDependentsTool(BaseTool):
    """Find incoming dependents (entities importing, calling, or inheriting) for a given node."""

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="get_dependents",
            description="Find incoming dependents (components importing, invoking, or subclassing this entity).",
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Target node identifier",
                    },
                    "direct_only": {
                        "type": "boolean",
                        "default": True,
                        "description": "If True, only direct incoming dependents; if False, transitive dependents",
                    },
                    "edge_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional edge types filter",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "get_dependents"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        node_id = str(arguments.get("node_id", "")).strip()
        if not node_id:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'node_id' cannot be empty.")

        if node_id not in self.query_engine.graph:
            return ToolResult(
                status=ToolStatus.ERROR,
                data={"node_id": node_id, "total_dependents": 0, "dependents": []},
                message=f"Node '{node_id}' not found in knowledge graph.",
                metadata={"node_id": node_id, "found": False},
            )

        direct_only = bool(arguments.get("direct_only", True))
        edge_types = arguments.get("edge_types")

        dependents = self.query_engine.get_dependents(
            node_id=node_id,
            edge_types=edge_types,
            direct_only=direct_only,
        )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "node_id": node_id,
                "direct_only": direct_only,
                "total_dependents": len(dependents),
                "dependents": dependents,
            },
            message=f"Found {len(dependents)} {'direct' if direct_only else 'transitive'} dependent(s) for '{node_id}'.",
            metadata={"node_id": node_id, "direct_only": direct_only},
        )


class TraceStructuralImpactTool(BaseTool):
    """
    Perform structural reachability blast-radius analysis starting from a target node.
    Traces incoming CALLS, INHERITS, and IMPORTS edges up to max_depth.
    Never describes static reachability as guaranteed runtime execution or predictive risk.
    """

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="trace_structural_impact",
            description="Trace multi-hop structural reachability (blast radius) via reverse dependencies.",
            input_schema={
                "type": "object",
                "required": ["target_node_id"],
                "properties": {
                    "target_node_id": {
                        "type": "string",
                        "description": "Node ID of entity to trace structural impact from",
                    },
                    "max_depth": {
                        "type": "integer",
                        "default": 3,
                        "description": "Maximum traversal depth for reverse dependencies",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "trace_structural_impact"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        target_node_id = str(arguments.get("target_node_id", "")).strip()
        if not target_node_id:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'target_node_id' cannot be empty.")

        max_depth = int(arguments.get("max_depth", 3))
        if max_depth <= 0:
            max_depth = 3

        result = self.query_engine.trace_impact(target_node_id=target_node_id, max_depth=max_depth)

        if not result.get("found", False):
            return ToolResult(
                status=ToolStatus.ERROR,
                data=result,
                message=result.get("error", f"Node '{target_node_id}' not found in knowledge graph."),
                metadata={"target_node_id": target_node_id, "found": False},
            )

        total_impacted = result.get("total_impacted", 0)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=result,
            message=(
                f"Structural reachability analysis from '{target_node_id}' reached {total_impacted} entity/entities "
                f"within {max_depth} hop(s)."
            ),
            metadata={
                "target_node_id": target_node_id,
                "max_depth": max_depth,
                "total_impacted": total_impacted,
                "methodology": result.get("methodology"),
                "disclaimer": result.get("disclaimer"),
            },
        )


class DetectCyclesTool(BaseTool):
    """Detect circular dependency loops in the software knowledge graph."""

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="detect_cycles",
            description="Detect circular dependencies (dependency loops) across imports and function calls.",
            input_schema={
                "type": "object",
                "properties": {
                    "edge_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of edge types to consider (default: IMPORTS, CALLS)",
                    },
                    "max_cycles": {
                        "type": "integer",
                        "default": 25,
                        "description": "Maximum number of cycles to return",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "detect_cycles"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        edge_types = arguments.get("edge_types")
        max_cycles = int(arguments.get("max_cycles", 25))
        if max_cycles <= 0:
            max_cycles = 25

        cycles = self.query_engine.detect_cycles(edge_types=edge_types, max_cycles=max_cycles)
        has_cycles = len(cycles) > 0

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "has_cycles": has_cycles,
                "cycle_count": len(cycles),
                "cycles": cycles,
            },
            message=f"Detected {len(cycles)} circular dependency cycle(s) in knowledge graph.",
            metadata={"has_cycles": has_cycles, "cycle_count": len(cycles)},
        )
