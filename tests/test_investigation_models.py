"""
Unit tests for CodeMind Phase 6 Milestone 1 Core Models.
Verifies InvestigationIntent, ToolStatus, ToolAvailability, PlanStep,
InvestigationPlan, StepResult, ToolDefinition, and InvestigationResult.
"""

import unittest
from codemind.investigation.models import (
    InvestigationIntent,
    ToolStatus,
    ToolAvailability,
    ToolDefinition,
    PlanStep,
    InvestigationPlan,
    StepResult,
    InvestigationResult,
)


class TestInvestigationModels(unittest.TestCase):
    """Test suite verifying validation, enum values, and serialization of core models."""

    def test_01_all_five_investigation_intent_values(self):
        """Verify all five InvestigationIntent values exist and compare properly."""
        expected_intents = {"understand", "structure", "impact", "evolution", "insights"}
        actual_intents = {i.value for i in InvestigationIntent}
        self.assertEqual(actual_intents, expected_intents)

        # Direct attribute checks
        self.assertEqual(InvestigationIntent.UNDERSTAND, "understand")
        self.assertEqual(InvestigationIntent.STRUCTURE, "structure")
        self.assertEqual(InvestigationIntent.IMPACT, "impact")
        self.assertEqual(InvestigationIntent.EVOLUTION, "evolution")
        self.assertEqual(InvestigationIntent.INSIGHTS, "insights")

        # Case-insensitive equality
        self.assertEqual(InvestigationIntent.UNDERSTAND, "UNDERSTAND")
        self.assertEqual(InvestigationIntent.STRUCTURE, "STRUCTURE")
        self.assertEqual(InvestigationIntent.IMPACT, "IMPACT")
        self.assertEqual(InvestigationIntent.EVOLUTION, "EVOLUTION")
        self.assertEqual(InvestigationIntent.INSIGHTS, "INSIGHTS")

        # Enum instantiation from string
        self.assertEqual(InvestigationIntent("understand"), InvestigationIntent.UNDERSTAND)
        self.assertEqual(InvestigationIntent("structure"), InvestigationIntent.STRUCTURE)
        self.assertEqual(InvestigationIntent("impact"), InvestigationIntent.IMPACT)
        self.assertEqual(InvestigationIntent("evolution"), InvestigationIntent.EVOLUTION)
        self.assertEqual(InvestigationIntent("insights"), InvestigationIntent.INSIGHTS)

    def test_02_tool_status_and_tool_availability_values(self):
        """Verify ToolStatus and ToolAvailability values and comparisons."""
        # ToolStatus
        expected_statuses = {"SUCCESS", "ERROR", "UNAVAILABLE_DEFERRED"}
        actual_statuses = {s.value for s in ToolStatus}
        self.assertEqual(actual_statuses, expected_statuses)

        self.assertEqual(ToolStatus.SUCCESS, "SUCCESS")
        self.assertEqual(ToolStatus.ERROR, "ERROR")
        self.assertEqual(ToolStatus.UNAVAILABLE_DEFERRED, "UNAVAILABLE_DEFERRED")

        # Case-insensitive equality
        self.assertEqual(ToolStatus.SUCCESS, "success")
        self.assertEqual(ToolStatus.ERROR, "error")
        self.assertEqual(ToolStatus.UNAVAILABLE_DEFERRED, "unavailable_deferred")

        # ToolAvailability
        expected_avail = {"AVAILABLE", "DEFERRED"}
        actual_avail = {a.value for a in ToolAvailability}
        self.assertEqual(actual_avail, expected_avail)

        self.assertEqual(ToolAvailability.AVAILABLE, "AVAILABLE")
        self.assertEqual(ToolAvailability.DEFERRED, "DEFERRED")
        self.assertEqual(ToolAvailability.AVAILABLE, "available")
        self.assertEqual(ToolAvailability.DEFERRED, "deferred")

    def test_03_plan_step_construction_and_serialization(self):
        """Verify PlanStep initialization, parameter handling, and round-trip serialization."""
        step = PlanStep(
            step_id="step_1",
            tool_name="search_symbols",
            purpose="Find UserService definition in codebase",
            input_parameters={"query": "UserService", "node_type": "class"},
            dependencies=[],
            is_required=True,
        )

        self.assertEqual(step.step_id, "step_1")
        self.assertEqual(step.tool_name, "search_symbols")
        self.assertEqual(step.purpose, "Find UserService definition in codebase")
        self.assertEqual(step.input_parameters["query"], "UserService")
        self.assertEqual(step.dependencies, [])
        self.assertTrue(step.is_required)

        # Serialization to dictionary
        d = step.to_dict()
        self.assertEqual(d["step_id"], "step_1")
        self.assertEqual(d["tool_name"], "search_symbols")
        self.assertEqual(d["is_required"], True)

        # Deserialization from dictionary
        round_trip = PlanStep.from_dict(d)
        self.assertEqual(round_trip.step_id, step.step_id)
        self.assertEqual(round_trip.tool_name, step.tool_name)
        self.assertEqual(round_trip.input_parameters, step.input_parameters)
        self.assertEqual(round_trip.dependencies, step.dependencies)

        # Validation: empty step_id or tool_name must fail
        with self.assertRaises(ValueError):
            PlanStep(step_id="", tool_name="search_symbols")
        with self.assertRaises(ValueError):
            PlanStep(step_id="step_1", tool_name="")

    def test_04_investigation_plan_construction_and_serialization(self):
        """Verify InvestigationPlan initialization with steps and round-trip serialization."""
        step1 = PlanStep(step_id="step_1", tool_name="search_symbols", input_parameters={"query": "Auth"})
        step2 = PlanStep(
            step_id="step_2",
            tool_name="get_dependents",
            input_parameters={"node_id": "$step_1.nodes[0].id"},
            dependencies=["step_1"],
        )

        plan = InvestigationPlan(
            plan_id="plan_001",
            original_query="Which components depend on Auth?",
            intent=InvestigationIntent.STRUCTURE,
            extracted_entities={"symbols": ["Auth"], "intent_confidence": 0.95},
            steps=[step1, step2],
            creation_metadata={"generator": "InvestigationPlanner", "version": "1.0"},
        )

        self.assertEqual(plan.plan_id, "plan_001")
        self.assertEqual(plan.intent, InvestigationIntent.STRUCTURE)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[1].dependencies, ["step_1"])

        # Serialization
        d = plan.to_dict()
        self.assertEqual(d["plan_id"], "plan_001")
        self.assertEqual(d["intent"], "structure")
        self.assertEqual(len(d["steps"]), 2)
        self.assertEqual(d["steps"][1]["dependencies"], ["step_1"])

        # Round-trip deserialization
        round_trip = InvestigationPlan.from_dict(d)
        self.assertEqual(round_trip.plan_id, plan.plan_id)
        self.assertEqual(round_trip.intent, InvestigationIntent.STRUCTURE)
        self.assertEqual(len(round_trip.steps), 2)
        self.assertEqual(round_trip.steps[1].tool_name, "get_dependents")

        # Validation: empty plan_id or original_query
        with self.assertRaises(ValueError):
            InvestigationPlan(plan_id="", original_query="Test query", intent=InvestigationIntent.UNDERSTAND)
        with self.assertRaises(ValueError):
            InvestigationPlan(plan_id="p1", original_query="", intent=InvestigationIntent.UNDERSTAND)

    def test_05_step_result_success_and_error_representations(self):
        """Verify StepResult for successful, error, and deferred executions."""
        # Success result
        success_res = StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={"matches": ["class:auth.py:AuthService"]},
            execution_timing={"latency_ms": 12.5},
        )
        self.assertTrue(success_res.is_success)
        self.assertFalse(success_res.is_error)
        self.assertFalse(success_res.is_deferred)
        self.assertEqual(success_res.to_dict()["status"], "SUCCESS")

        # Error result
        error_res = StepResult(
            step_id="step_2",
            tool_name="get_node",
            status=ToolStatus.ERROR,
            error_message="Node 'non_existent' not found in graph.",
            execution_timing={"latency_ms": 3.2},
        )
        self.assertTrue(error_res.is_error)
        self.assertFalse(error_res.is_success)
        self.assertEqual(error_res.to_dict()["error_message"], "Node 'non_existent' not found in graph.")

        # Deferred result
        deferred_res = StepResult(
            step_id="step_3",
            tool_name="git_commit_history",
            status=ToolStatus.UNAVAILABLE_DEFERRED,
            warning="Git temporal intelligence is scheduled for Phase 7.",
        )
        self.assertTrue(deferred_res.is_deferred)
        self.assertFalse(deferred_res.is_success)

        # Round-trip deserialization
        round_trip = StepResult.from_dict(error_res.to_dict())
        self.assertEqual(round_trip.step_id, "step_2")
        self.assertEqual(round_trip.status, ToolStatus.ERROR)
        self.assertEqual(round_trip.error_message, "Node 'non_existent' not found in graph.")

    def test_06_tool_definition_validation(self):
        """Verify ToolDefinition schema validation and rejection of invalid configurations."""
        # Valid available tool definition
        avail_def = ToolDefinition(
            tool_name="search_symbols",
            description="Search symbols in the software knowledge graph",
            input_schema={"type": "object", "required": ["query"]},
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )
        self.assertEqual(avail_def.tool_name, "search_symbols")
        self.assertEqual(avail_def.availability, ToolAvailability.AVAILABLE)
        self.assertEqual(avail_def.target_phase, None)

        d = avail_def.to_dict()
        self.assertEqual(d["availability"], "AVAILABLE")
        round_trip = ToolDefinition.from_dict(d)
        self.assertEqual(round_trip.tool_name, avail_def.tool_name)

        # Valid deferred tool definition
        deferred_def = ToolDefinition(
            tool_name="git_code_churn",
            description="Mine Git commit log to compute file churn statistics",
            availability=ToolAvailability.DEFERRED,
            target_phase="Phase 7: Git Temporal Intelligence",
        )
        self.assertEqual(deferred_def.availability, ToolAvailability.DEFERRED)
        self.assertEqual(deferred_def.target_phase, "Phase 7: Git Temporal Intelligence")

        # Validation: empty tool_name or description
        with self.assertRaises(ValueError):
            ToolDefinition(tool_name="", description="Valid description")
        with self.assertRaises(ValueError):
            ToolDefinition(tool_name="valid_name", description="")

        # Validation: deferred tool must specify target_phase
        with self.assertRaises(ValueError):
            ToolDefinition(
                tool_name="deferred_tool",
                description="A deferred capability",
                availability=ToolAvailability.DEFERRED,
                target_phase=None,
            )

    def test_07_investigation_result_construction_and_serialization(self):
        """Verify InvestigationResult construction with optional and populated fields."""
        # Minimal result
        minimal_res = InvestigationResult(query="How does authentication work?")
        self.assertEqual(minimal_res.query, "How does authentication work?")
        self.assertEqual(minimal_res.overall_status, ToolStatus.SUCCESS)
        self.assertIsNone(minimal_res.plan)
        self.assertEqual(minimal_res.step_results, [])

        d_minimal = minimal_res.to_dict()
        self.assertEqual(d_minimal["query"], "How does authentication work?")
        self.assertIsNone(d_minimal["plan"])

        # Comprehensive result with populated components
        step = PlanStep(step_id="step_1", tool_name="search_symbols", input_parameters={"query": "auth"})
        plan = InvestigationPlan(
            plan_id="plan_1",
            original_query="How does authentication work?",
            intent=InvestigationIntent.UNDERSTAND,
            steps=[step],
        )
        step_res = StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={"matches": ["class:auth.py:Auth"]},
        )

        full_res = InvestigationResult(
            query="How does authentication work?",
            intent=InvestigationIntent.UNDERSTAND,
            plan=plan,
            step_results=[step_res],
            evidence=[{"content": "def authenticate(): ...", "citation": "auth.py:10-25"}],
            final_answer="Authentication uses the Auth class [auth.py:10-25].",
            overall_status=ToolStatus.SUCCESS,
            metadata={"total_latency_ms": 145.0},
        )

        self.assertEqual(full_res.intent, InvestigationIntent.UNDERSTAND)
        self.assertEqual(len(full_res.step_results), 1)
        self.assertEqual(len(full_res.evidence), 1)
        self.assertIn("[auth.py:10-25]", full_res.final_answer)

        # Round-trip serialization
        d_full = full_res.to_dict()
        self.assertEqual(d_full["intent"], "understand")
        self.assertEqual(d_full["overall_status"], "SUCCESS")
        self.assertIsNotNone(d_full["plan"])

        round_trip = InvestigationResult.from_dict(d_full)
        self.assertEqual(round_trip.query, full_res.query)
        self.assertEqual(round_trip.intent, InvestigationIntent.UNDERSTAND)
        self.assertEqual(len(round_trip.step_results), 1)
        self.assertEqual(round_trip.step_results[0].tool_name, "search_symbols")


if __name__ == "__main__":
    unittest.main()
