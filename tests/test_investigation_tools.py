"""
Unit tests for CodeMind Phase 6 Milestone 1 Base Tool Abstraction & ToolRegistry.
Verifies BaseTool, ToolResult, DeferredTool, and ToolRegistry integrity and error handling.
"""

import unittest
from typing import Dict, Any, Optional

from codemind.investigation.models import (
    ToolStatus,
    ToolAvailability,
    ToolDefinition,
)
from codemind.investigation.tools.base import (
    BaseTool,
    ToolResult,
    DeferredTool,
)
from codemind.investigation.tools.registry import ToolRegistry


class DummyConcreteTool(BaseTool):
    """Concrete tool implementation for testing BaseTool contract."""

    def __init__(self, name: str = "dummy_tool", should_fail: bool = False):
        self._name = name
        self._should_fail = should_fail
        self._definition = ToolDefinition(
            tool_name=self._name,
            description="A dummy tool for unit testing",
            input_schema={
                "type": "object",
                "required": ["target"],
                "properties": {"target": {"type": "string"}},
            },
            availability=ToolAvailability.AVAILABLE,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A dummy tool for unit testing"

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self._should_fail:
            raise RuntimeError("Deliberate internal execution failure")

        target = arguments["target"]
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"echo": target, "length": len(target)},
            message=f"Processed target: {target}",
        )


class TestInvestigationTools(unittest.TestCase):
    """Test suite verifying BaseTool, DeferredTool, and ToolRegistry behavior."""

    def test_08_base_tool_abstract_interface(self):
        """Verify BaseTool cannot be instantiated directly without implementing abstract methods."""
        with self.assertRaises(TypeError):
            BaseTool()  # Abstract class instantiation must raise TypeError

    def test_09_tool_result_construction_and_serialization(self):
        """Verify ToolResult properties, helpers, and serialization."""
        # Success result
        res = ToolResult(
            status=ToolStatus.SUCCESS,
            data={"count": 42},
            message="Operation succeeded",
            metadata={"source": "test"},
        )
        self.assertTrue(res.is_success)
        self.assertFalse(res.is_error)
        self.assertFalse(res.is_deferred)

        d = res.to_dict()
        self.assertEqual(d["status"], "SUCCESS")
        self.assertEqual(d["data"]["count"], 42)

        # Round-trip deserialization
        round_trip = ToolResult.from_dict(d)
        self.assertEqual(round_trip.status, ToolStatus.SUCCESS)
        self.assertEqual(round_trip.data, {"count": 42})
        self.assertEqual(round_trip.message, "Operation succeeded")

        # Error result
        err_res = ToolResult(status=ToolStatus.ERROR, message="Failed")
        self.assertTrue(err_res.is_error)
        self.assertFalse(err_res.is_success)

        # Deferred result
        def_res = ToolResult(status=ToolStatus.UNAVAILABLE_DEFERRED, message="Deferred")
        self.assertTrue(def_res.is_deferred)

    def test_10_deferred_tool_behavior_and_phase_reporting(self):
        """Verify DeferredTool returns UNAVAILABLE_DEFERRED with null data and target phase."""
        git_tool = DeferredTool(
            name="git_commit_history",
            description="Mines Git commits for historical evolution",
            target_phase="Phase 7: Git Temporal Intelligence",
            required_capabilities=["git_cli", "commit_graph"],
            input_schema={"required": ["path"]},
        )

        self.assertEqual(git_tool.name, "git_commit_history")
        self.assertEqual(git_tool.availability, ToolAvailability.DEFERRED)
        self.assertEqual(git_tool.target_phase, "Phase 7: Git Temporal Intelligence")
        self.assertEqual(git_tool.definition.availability, ToolAvailability.DEFERRED)

        # Execute deferred tool
        result = git_tool.execute({"path": "src/auth.py"})

        # Crucial assertions:
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE_DEFERRED)
        self.assertTrue(result.is_deferred)
        self.assertIsNone(result.data, "Deferred tool must never fabricate data")
        self.assertIn("Phase 7", result.message)
        self.assertIn("git_commit_history", result.message)
        self.assertEqual(result.metadata["target_phase"], "Phase 7: Git Temporal Intelligence")

        # Rejection of invalid DeferredTool initialization
        with self.assertRaises(ValueError):
            DeferredTool(name="", description="Desc", target_phase="Phase 7")
        with self.assertRaises(ValueError):
            DeferredTool(name="test", description="Desc", target_phase="")

    def test_11_registry_registration_and_retrieval(self):
        """Verify registering and retrieving tools from ToolRegistry."""
        registry = ToolRegistry()
        self.assertEqual(registry.count(), 0)
        self.assertEqual(len(registry), 0)

        tool = DummyConcreteTool(name="tool_alpha")
        registry.register(tool)

        self.assertEqual(registry.count(), 1)
        self.assertTrue(registry.has_tool("tool_alpha"))
        self.assertIn("tool_alpha", registry)

        retrieved = registry.get("tool_alpha")
        self.assertIs(retrieved, tool)

        # get_or_raise
        self.assertIs(registry.get_or_raise("tool_alpha"), tool)

        # Non-existent tool returns None or raises KeyError
        self.assertIsNone(registry.get("non_existent"))
        with self.assertRaises(KeyError):
            registry.get_or_raise("non_existent")

    def test_12_duplicate_registration_rejection(self):
        """Verify ToolRegistry rejects registering duplicate tool names."""
        registry = ToolRegistry()
        tool1 = DummyConcreteTool(name="duplicate_tool")
        tool2 = DummyConcreteTool(name="duplicate_tool")

        registry.register(tool1)
        with self.assertRaises(ValueError) as ctx:
            registry.register(tool2)
        self.assertIn("already registered", str(ctx.exception))

    def test_13_available_and_deferred_tool_filtering(self):
        """Verify ToolRegistry accurately partitions available vs deferred tools."""
        registry = ToolRegistry()

        avail_1 = DummyConcreteTool(name="search_symbols")
        avail_2 = DummyConcreteTool(name="get_callers")
        deferred_1 = DeferredTool(name="git_churn", description="Churn", target_phase="Phase 7")
        deferred_2 = DeferredTool(name="hotspots", description="Hotspots", target_phase="Phase 9")

        registry.register(avail_1)
        registry.register(deferred_1)
        registry.register(avail_2)
        registry.register(deferred_2)

        self.assertEqual(len(registry), 4)

        available_tools = registry.list_available()
        self.assertEqual(len(available_tools), 2)
        self.assertEqual([t.name for t in available_tools], ["search_symbols", "get_callers"])

        deferred_tools = registry.list_deferred()
        self.assertEqual(len(deferred_tools), 2)
        self.assertEqual([t.name for t in deferred_tools], ["git_churn", "hotspots"])

    def test_14_deterministic_tool_listing_order(self):
        """Verify ToolRegistry preserves deterministic insertion order."""
        registry = ToolRegistry()
        tool_names = [f"tool_{i:02d}" for i in range(10)]

        for name in tool_names:
            registry.register(DummyConcreteTool(name=name))

        listed_names = [t.name for t in registry.list_tools()]
        self.assertEqual(listed_names, tool_names)

        # Iteration order
        iter_names = [t.name for t in registry]
        self.assertEqual(iter_names, tool_names)

    def test_15_invalid_tool_registration_rejection(self):
        """Verify ToolRegistry rejects non-BaseTool objects and invalid configurations."""
        registry = ToolRegistry()

        # Reject non-BaseTool objects
        with self.assertRaises(TypeError):
            registry.register("not_a_tool")  # type: ignore

        with self.assertRaises(TypeError):
            registry.register(object())  # type: ignore

        with self.assertRaises(TypeError):
            registry.register({"name": "dict_tool"})  # type: ignore

    def test_16_base_tool_argument_validation(self):
        """Verify BaseTool.execute rejects missing required arguments cleanly."""
        tool = DummyConcreteTool(name="validator_tool")

        # Missing required parameter "target"
        res_missing = tool.execute({})
        self.assertTrue(res_missing.is_error)
        self.assertIn("Missing required parameter 'target'", res_missing.message)

        # Non-dict arguments
        res_invalid_type = tool.execute("invalid")  # type: ignore
        self.assertTrue(res_invalid_type.is_error)

        # Valid arguments succeed
        res_valid = tool.execute({"target": "UserService"})
        self.assertTrue(res_valid.is_success)
        self.assertEqual(res_valid.data["echo"], "UserService")

    def test_17_base_tool_exception_handling(self):
        """Verify BaseTool.execute catches unhandled internal exceptions and returns ToolResult."""
        failing_tool = DummyConcreteTool(name="failing_tool", should_fail=True)

        # Does not crash; returns structured ERROR result
        res = failing_tool.execute({"target": "test"})
        self.assertTrue(res.is_error)
        self.assertIn("Deliberate internal execution failure", res.message)
        self.assertEqual(res.metadata["exception_type"], "RuntimeError")

    def test_18_registry_unregister_and_clear(self):
        """Verify unregistering individual tools and clearing the registry."""
        registry = ToolRegistry()
        registry.register(DummyConcreteTool(name="temp_tool"))
        self.assertTrue(registry.has_tool("temp_tool"))

        self.assertTrue(registry.unregister("temp_tool"))
        self.assertFalse(registry.has_tool("temp_tool"))
        self.assertFalse(registry.unregister("temp_tool"))

        registry.register(DummyConcreteTool(name="t1"))
        registry.register(DummyConcreteTool(name="t2"))
        self.assertEqual(registry.count(), 2)

        registry.clear()
        self.assertEqual(registry.count(), 0)


if __name__ == "__main__":
    unittest.main()
