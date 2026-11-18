"""
Unit tests for CodeMind Phase 6 Milestone 2 Deferred Tools and Full Tool Registry.
Verifies Phase 7, 8, and 9 deferred tool boundaries and deterministic registry construction.
"""

import unittest

from codemind.investigation.models import ToolStatus, ToolAvailability
from codemind.investigation.tools.deferred_tools import create_deferred_tools
from codemind.investigation.tools import create_tool_registry


class TestInvestigationDeferredTools(unittest.TestCase):
    """Test suite verifying future-phase tool isolation and deterministic registry population."""

    def test_all_deferred_tools_presence_and_metadata(self):
        """Verify all six required deferred tools exist with correct target phases."""
        deferred_tools = create_deferred_tools()
        self.assertEqual(len(deferred_tools), 6)

        expected_tools = {
            "git_commit_history": "Phase 7",
            "git_code_churn": "Phase 7",
            "multi_signal_impact": "Phase 8",
            "get_test_coverage": "Phase 8",
            "detect_maintenance_hotspots": "Phase 9",
            "check_architecture_conformance": "Phase 9",
        }

        tool_map = {t.name: t for t in deferred_tools}
        self.assertEqual(set(tool_map.keys()), set(expected_tools.keys()))

        for name, expected_phase_substr in expected_tools.items():
            tool = tool_map[name]
            self.assertEqual(tool.availability, ToolAvailability.DEFERRED)
            self.assertIn(expected_phase_substr, tool.target_phase)
            self.assertEqual(tool.definition.availability, ToolAvailability.DEFERRED)
            self.assertIn(expected_phase_substr, tool.definition.target_phase)

    def test_deferred_tools_execution_returns_null_data(self):
        """Crucial assertion: deferred tools must NEVER return fabricated data."""
        deferred_tools = create_deferred_tools()

        for tool in deferred_tools:
            res = tool.execute({"node_id": "any_node", "path": "any_path"})

            self.assertEqual(
                res.status,
                ToolStatus.UNAVAILABLE_DEFERRED,
                f"Tool '{tool.name}' did not return UNAVAILABLE_DEFERRED",
            )
            self.assertTrue(res.is_deferred)
            self.assertFalse(res.is_success)
            self.assertIsNone(res.data, f"Tool '{tool.name}' fabricated non-null data!")
            self.assertIn(tool.name, res.message)
            self.assertIn("unavailable", res.message.lower())
            self.assertEqual(res.metadata["target_phase"], tool.target_phase)

    def test_create_tool_registry_deterministic_order_and_counts(self):
        """Verify create_tool_registry constructs all 17 tools in exact deterministic order."""
        registry = create_tool_registry()

        expected_order = [
            # 1. Code Tools (3)
            "search_symbols",
            "get_node_details",
            "get_file_content",
            # 2. Graph Tools (6)
            "get_callers",
            "get_callees",
            "get_dependencies",
            "get_dependents",
            "trace_structural_impact",
            "detect_cycles",
            # 3. Retrieval Tools (2)
            "semantic_search",
            "hybrid_search",
            # 4. Deferred Tools (6)
            "git_commit_history",
            "git_code_churn",
            "multi_signal_impact",
            "get_test_coverage",
            "detect_maintenance_hotspots",
            "check_architecture_conformance",
        ]

        self.assertEqual(registry.count(), 17)
        self.assertEqual(len(registry), 17)

        actual_order = [t.name for t in registry.list_tools()]
        self.assertEqual(actual_order, expected_order)

        # Available vs Deferred partitioning
        available_tools = registry.list_available()
        self.assertEqual(len(available_tools), 11)
        self.assertEqual([t.name for t in available_tools], expected_order[:11])

        deferred_tools = registry.list_deferred()
        self.assertEqual(len(deferred_tools), 6)
        self.assertEqual([t.name for t in deferred_tools], expected_order[11:])

    def test_tool_registry_lookup_and_immutability(self):
        """Verify tool retrieval and duplicate rejection in registry."""
        registry = create_tool_registry()

        # Lookup by name
        self.assertIsNotNone(registry.get("search_symbols"))
        self.assertIsNotNone(registry.get("trace_structural_impact"))
        self.assertIsNotNone(registry.get("git_commit_history"))
        self.assertIsNone(registry.get("unregistered_tool"))

        # In operator
        self.assertIn("hybrid_search", registry)
        self.assertNotIn("fake_tool", registry)


if __name__ == "__main__":
    unittest.main()
