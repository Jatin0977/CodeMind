"""
Unit tests for CodeMind Phase 6 Milestone 3 Investigation Planner.
Verifies workflow plan generation, step dependency acyclicity, deferred tool handling,
deterministic plan reproducibility, and registry validation without tool execution.
"""

import unittest
from unittest.mock import MagicMock

from codemind.investigation.models import (
    InvestigationIntent,
    ToolAvailability,
)
from codemind.investigation.planner import InvestigationPlanner
from codemind.investigation.tools import create_tool_registry
from codemind.investigation.tools.registry import ToolRegistry


class TestInvestigationPlanner(unittest.TestCase):
    """Test suite verifying InvestigationPlanner workflows, validation, and integrity."""

    def setUp(self):
        self.planner = InvestigationPlanner()
        self.registry = create_tool_registry()

    def test_01_understand_workflow_plan(self):
        """Verify plan generated for an UNDERSTAND query."""
        query = "How does authentication work in this repository?"
        plan = self.planner.plan(query=query, registry=self.registry)

        self.assertEqual(plan.intent, InvestigationIntent.UNDERSTAND)
        self.assertGreater(len(plan.steps), 0)

        tool_names = [s.tool_name for s in plan.steps]
        self.assertIn("search_symbols", tool_names)
        self.assertIn("hybrid_search", tool_names)

        # Check step IDs and ordering
        self.assertEqual(plan.steps[0].step_id, "step_1")
        self.assertEqual(plan.steps[0].tool_name, "search_symbols")

    def test_02_structure_workflow_plan_dependents(self):
        """Verify plan generated for a STRUCTURE query asking for dependents."""
        query = "Which components depend on the UserService class?"
        plan = self.planner.plan(query=query, registry=self.registry)

        self.assertEqual(plan.intent, InvestigationIntent.STRUCTURE)
        tool_names = [s.tool_name for s in plan.steps]

        self.assertIn("search_symbols", tool_names)
        self.assertIn("get_dependents", tool_names)

        # get_dependents should depend on search_symbols
        search_step = next(s for s in plan.steps if s.tool_name == "search_symbols")
        dependents_step = next(s for s in plan.steps if s.tool_name == "get_dependents")
        self.assertIn(search_step.step_id, dependents_step.dependencies)

    def test_03_impact_workflow_plan(self):
        """Verify plan generated for an IMPACT query."""
        query = "What components may be affected if UserService is modified?"
        plan = self.planner.plan(query=query, registry=self.registry)

        self.assertEqual(plan.intent, InvestigationIntent.IMPACT)
        tool_names = [s.tool_name for s in plan.steps]

        self.assertIn("search_symbols", tool_names)
        self.assertIn("trace_structural_impact", tool_names)
        self.assertIn("get_test_coverage", tool_names)

        # trace_structural_impact must depend on search_symbols
        impact_step = next(s for s in plan.steps if s.tool_name == "trace_structural_impact")
        self.assertIn("step_1", impact_step.dependencies)

    def test_04_evolution_workflow_plan(self):
        """Verify plan generated for an EVOLUTION query with deferred Git tools."""
        query = "How has the authentication module changed over time?"
        plan = self.planner.plan(query=query, registry=self.registry)

        self.assertEqual(plan.intent, InvestigationIntent.EVOLUTION)
        tool_names = [s.tool_name for s in plan.steps]

        # Must include deferred Git tools
        self.assertIn("git_commit_history", tool_names)
        self.assertIn("git_code_churn", tool_names)

        # Verify that deferred tools are confirmed deferred in the registry
        for step in plan.steps:
            tool = self.registry.get(step.tool_name)
            if step.tool_name in ["git_commit_history", "git_code_churn"]:
                self.assertEqual(tool.availability, ToolAvailability.DEFERRED)
                self.assertIn("Phase 7", tool.target_phase)

    def test_05_insights_workflow_plan(self):
        """Verify plan generated for an INSIGHTS query."""
        query = "Which modules appear to have the highest maintenance risk and circular dependencies?"
        plan = self.planner.plan(query=query, registry=self.registry)

        self.assertEqual(plan.intent, InvestigationIntent.INSIGHTS)
        tool_names = [s.tool_name for s in plan.steps]

        self.assertIn("detect_cycles", tool_names)
        self.assertIn("detect_maintenance_hotspots", tool_names)

        # detect_maintenance_hotspots must be deferred
        tool = self.registry.get("detect_maintenance_hotspots")
        self.assertEqual(tool.availability, ToolAvailability.DEFERRED)
        self.assertIn("Phase 9", tool.target_phase)

    def test_06_step_ids_are_unique_and_sequential(self):
        """Verify step IDs are step_1, step_2, ... without duplicates."""
        for q in [
            "How does file filtering work?",
            "Who calls verify_jwt?",
            "What breaks if I change FileFilter?",
            "Show git commit history of auth.py",
            "Are there cycles in the codebase?",
        ]:
            plan = self.planner.plan(query=q, registry=self.registry)
            expected_ids = [f"step_{i}" for i in range(1, len(plan.steps) + 1)]
            actual_ids = [s.step_id for s in plan.steps]
            self.assertEqual(actual_ids, expected_ids, f"Step IDs mismatch for query: {q}")

    def test_07_dependencies_reference_valid_earlier_steps(self):
        """Verify that every step dependency references a strictly earlier step."""
        for q in [
            "Which components depend on UserService?",
            "What breaks if I edit RepositoryLoader?",
            "How has auth changed over time?",
        ]:
            plan = self.planner.plan(query=q, registry=self.registry)
            step_indices = {s.step_id: idx for idx, s in enumerate(plan.steps)}

            for s in plan.steps:
                curr_idx = step_indices[s.step_id]
                for dep in s.dependencies:
                    self.assertIn(dep, step_indices, f"Step '{s.step_id}' references non-existent dep '{dep}'")
                    dep_idx = step_indices[dep]
                    self.assertLess(
                        dep_idx,
                        curr_idx,
                        f"Step '{s.step_id}' (idx {curr_idx}) references future or self dep '{dep}' (idx {dep_idx})",
                    )

    def test_08_registry_validation_and_missing_tools_handling(self):
        """Verify planner gracefully handles a registry that is missing optional tools."""
        minimal_registry = ToolRegistry()
        # Only register search_symbols and get_node_details
        minimal_registry.register(self.registry.get("search_symbols"))
        minimal_registry.register(self.registry.get("get_node_details"))

        query = "How does UserService work?"
        plan = self.planner.plan(query=query, registry=minimal_registry)

        # Plan should only include tools that exist in minimal_registry
        for step in plan.steps:
            self.assertTrue(minimal_registry.has_tool(step.tool_name))

        # Check that steps are still cleanly numbered step_1, step_2...
        self.assertEqual([s.step_id for s in plan.steps], [f"step_{i+1}" for i in range(len(plan.steps))])

    def test_09_deterministic_plans_reproducibility(self):
        """Verify identical queries generate identical plans with identical plan_ids."""
        query = "What components may be affected if UserService is modified?"
        plan1 = self.planner.plan(query=query, registry=self.registry)
        plan2 = self.planner.plan(query=query, registry=self.registry)

        self.assertEqual(plan1.plan_id, plan2.plan_id)
        self.assertEqual(plan1.intent, plan2.intent)
        self.assertEqual(len(plan1.steps), len(plan2.steps))

        for s1, s2 in zip(plan1.steps, plan2.steps):
            self.assertEqual(s1.step_id, s2.step_id)
            self.assertEqual(s1.tool_name, s2.tool_name)
            self.assertEqual(s1.input_parameters, s2.input_parameters)
            self.assertEqual(s1.dependencies, s2.dependencies)

    def test_10_no_tool_execution_during_planning(self):
        """Crucial test: planner must inspect tools without executing them."""
        # Wrap all tools with a spy mock on execute
        mock_registry = ToolRegistry()
        execute_spies = []

        for tool in self.registry.list_tools():
            tool.execute = MagicMock(name=f"{tool.name}.execute")
            execute_spies.append(tool.execute)
            mock_registry.register(tool)

        # Run planner across multiple intents
        self.planner.plan("How does auth work?", registry=mock_registry)
        self.planner.plan("What breaks if I modify UserService?", registry=mock_registry)
        self.planner.plan("Commit history of file_filter.py", registry=mock_registry)

        # None of the tools must have had execute() called!
        for spy in execute_spies:
            spy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
