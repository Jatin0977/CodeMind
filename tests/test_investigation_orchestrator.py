"""
Unit and integration tests for InvestigationOrchestrator in CodeMind (Phase 6, Milestone 4).
Tests sequential execution, dependency handling, error isolation, deferred tool handling,
parameter resolution, and evidence aggregation.
"""

from typing import Dict, Any
import pytest

from codemind.investigation.models import (
    InvestigationPlan,
    InvestigationStatus,
    PlanStep,
    ToolStatus,
    ToolAvailability,
    ToolDefinition,
)
from codemind.investigation.tools.base import BaseTool, ToolResult, DeferredTool
from codemind.investigation.tools.registry import ToolRegistry
from codemind.investigation.orchestrator import InvestigationOrchestrator


class MockSuccessTool(BaseTool):
    """Tool that returns deterministic success output."""

    def __init__(self, name: str = "mock_success"):
        self._name = name
        self._def = ToolDefinition(
            tool_name=name,
            description="Mock successful tool",
            input_schema={"type": "object"},
            availability=ToolAvailability.AVAILABLE,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._def.description

    @property
    def definition(self) -> ToolDefinition:
        return self._def

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"result": "success", "echo": arguments.get("input_val")},
            message="Execution succeeded",
        )


class MockFailTool(BaseTool):
    """Tool that returns an error status."""

    def __init__(self, name: str = "mock_fail"):
        self._name = name
        self._def = ToolDefinition(
            tool_name=name,
            description="Mock failing tool",
            availability=ToolAvailability.AVAILABLE,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._def.description

    @property
    def definition(self) -> ToolDefinition:
        return self._def

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            status=ToolStatus.ERROR,
            data=None,
            message="Controlled tool failure occurred.",
        )


class MockExceptionTool(BaseTool):
    """Tool that crashes with an unexpected exception."""

    def __init__(self, name: str = "mock_crash"):
        self._name = name
        self._def = ToolDefinition(
            tool_name=name,
            description="Mock crashing tool",
            availability=ToolAvailability.AVAILABLE,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._def.description

    @property
    def definition(self) -> ToolDefinition:
        return self._def

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        raise RuntimeError("Simulated unhandled fatal exception in tool logic!")


def test_successful_sequential_execution():
    """Verify clean sequential execution of valid independent and dependent steps."""
    registry = ToolRegistry()
    t1 = MockSuccessTool("tool_1")
    t2 = MockSuccessTool("tool_2")
    registry.register(t1)
    registry.register(t2)

    plan = InvestigationPlan(
        plan_id="plan_test_1",
        original_query="test query",
        intent="understand",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="tool_1",
                purpose="First step",
                input_parameters={"input_val": "alpha"},
                is_required=True,
            ),
            PlanStep(
                step_id="step_2",
                tool_name="tool_2",
                purpose="Second step",
                input_parameters={"input_val": "$step_1.echo"},
                dependencies=["step_1"],
                is_required=True,
            ),
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.SUCCESS
    assert len(result.step_results) == 2
    assert result.step_results[0].status == ToolStatus.SUCCESS
    assert result.step_results[0].output["echo"] == "alpha"
    assert result.step_results[1].status == ToolStatus.SUCCESS
    assert result.step_results[1].output["echo"] == "alpha"


def test_dependency_ordering_and_skipping():
    """Verify dependent step is skipped when upstream required step fails."""
    registry = ToolRegistry()
    registry.register(MockFailTool("failing_tool"))
    registry.register(MockSuccessTool("dependent_tool"))

    plan = InvestigationPlan(
        plan_id="plan_test_2",
        original_query="test failure cascading",
        intent="understand",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="failing_tool",
                purpose="Will fail",
                input_parameters={},
                is_required=True,
            ),
            PlanStep(
                step_id="step_2",
                tool_name="dependent_tool",
                purpose="Depends on step_1",
                input_parameters={},
                dependencies=["step_1"],
                is_required=False,
            ),
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.FAILED
    assert result.step_results[0].status == ToolStatus.ERROR
    assert result.step_results[1].status == ToolStatus.SKIPPED
    assert "required upstream dependency" in result.step_results[1].warning.lower()


def test_independent_step_continues_after_failure():
    """Verify an independent step continues execution even if a sibling step fails."""
    registry = ToolRegistry()
    registry.register(MockFailTool("failing_tool"))
    registry.register(MockSuccessTool("independent_tool"))

    plan = InvestigationPlan(
        plan_id="plan_test_3",
        original_query="test independent resilience",
        intent="understand",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="failing_tool",
                purpose="Fails but is isolated",
                input_parameters={},
                dependencies=[],
                is_required=False,
            ),
            PlanStep(
                step_id="step_2",
                tool_name="independent_tool",
                purpose="Independent step",
                input_parameters={"input_val": "resilient"},
                dependencies=[],
                is_required=True,
            ),
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    # Some step succeeded and produced results, while one optional step failed
    assert result.overall_status == InvestigationStatus.PARTIAL_SUCCESS
    assert result.step_results[0].status == ToolStatus.ERROR
    assert result.step_results[1].status == ToolStatus.SUCCESS
    assert result.step_results[1].output["echo"] == "resilient"


def test_deferred_tool_handling():
    """Verify deferred tools are captured as UNAVAILABLE_DEFERRED without being run."""
    registry = ToolRegistry()
    registry.register(MockSuccessTool("active_tool"))
    def_tool = DeferredTool(
        name="git_commit_history",
        description="Deferred git tool",
        target_phase="Phase 7: Git Temporal Intelligence",
    )
    registry.register(def_tool)

    plan = InvestigationPlan(
        plan_id="plan_test_4",
        original_query="analyze commit history",
        intent="evolution",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="active_tool",
                purpose="Active step",
                is_required=True,
            ),
            PlanStep(
                step_id="step_2",
                tool_name="git_commit_history",
                purpose="Deferred step",
                is_required=False,
            ),
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.PARTIAL_SUCCESS
    assert result.step_results[0].status == ToolStatus.SUCCESS
    assert result.step_results[1].status == ToolStatus.UNAVAILABLE_DEFERRED
    assert result.step_results[1].output is None
    assert "deferred" in result.step_results[1].warning.lower()

    # Evidence collector records deferred capability
    deferred_evidence = [e for e in result.evidence if e["category"] == "deferred"]
    assert len(deferred_evidence) == 1
    assert deferred_evidence[0]["source_tool"] == "git_commit_history"
    assert deferred_evidence[0]["target_phase"] == "Phase 7: Git Temporal Intelligence"


def test_purely_deferred_plan_status():
    """Verify that a plan consisting only of deferred tools yields DEFERRED status."""
    registry = ToolRegistry()
    def_tool = DeferredTool(
        name="git_code_churn",
        description="Deferred churn tool",
        target_phase="Phase 7: Git Temporal Intelligence",
    )
    registry.register(def_tool)

    plan = InvestigationPlan(
        plan_id="plan_test_deferred_only",
        original_query="calculate churn",
        intent="evolution",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="git_code_churn",
                purpose="Deferred churn",
                is_required=True,
            )
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.DEFERRED
    assert result.step_results[0].status == ToolStatus.UNAVAILABLE_DEFERRED


def test_ambiguous_symbol_search_skips_dependent_step():
    """Verify ambiguous symbol search results cause dependent step to be skipped safely."""
    registry = ToolRegistry()

    class AmbiguousSearchTool(BaseTool):
        @property
        def name(self) -> str:
            return "search_symbols"

        @property
        def description(self) -> str:
            return "Mock search tool returning multiple matches"

        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(tool_name="search_symbols", description="Mock")

        def _run(self, arguments: Dict[str, Any]) -> ToolResult:
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "is_ambiguous": True,
                    "total_matches": 2,
                    "primary_node_id": "fn:mod1.py:run",
                    "matches": [
                        {"id": "fn:mod1.py:run", "name": "run", "relative_path": "mod1.py"},
                        {"id": "fn:mod2.py:run", "name": "run", "relative_path": "mod2.py"},
                    ],
                },
            )

    registry.register(AmbiguousSearchTool())
    registry.register(MockSuccessTool("get_node_details"))
    registry.register(MockSuccessTool("hybrid_search"))

    plan = InvestigationPlan(
        plan_id="plan_ambiguous",
        original_query="explain run",
        intent="understand",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="search_symbols",
                purpose="Locate symbol",
                input_parameters={"query": "run"},
                is_required=True,
            ),
            PlanStep(
                step_id="step_2",
                tool_name="get_node_details",
                purpose="Get node details for ambiguous symbol",
                input_parameters={"node_id": "$step_1.primary_node_id"},
                dependencies=["step_1"],
                is_required=False,
            ),
            PlanStep(
                step_id="step_3",
                tool_name="hybrid_search",
                purpose="Independent retrieval",
                input_parameters={"query": "explain run"},
                dependencies=[],
                is_required=True,
            ),
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    # Step 1 succeeded (with ambiguous matches)
    assert result.step_results[0].status == ToolStatus.SUCCESS
    # Step 2 skipped due to ambiguity
    assert result.step_results[1].status == ToolStatus.SKIPPED
    assert "ambiguous" in result.step_results[1].warning.lower()
    # Step 3 succeeded independently
    assert result.step_results[2].status == ToolStatus.SUCCESS
    # Overall status is PARTIAL_SUCCESS because an optional step was skipped
    assert result.overall_status == InvestigationStatus.PARTIAL_SUCCESS

    # Candidate matches from step 1 are preserved in evidence
    code_evidence = [e for e in result.evidence if e["category"] == "code"]
    assert len(code_evidence) == 2
    assert {e["relative_path"] for e in code_evidence} == {"mod1.py", "mod2.py"}


def test_tool_exception_handling():
    """Verify tool runtime exceptions are caught cleanly without crashing orchestrator."""
    registry = ToolRegistry()
    registry.register(MockExceptionTool("crashing_tool"))

    plan = InvestigationPlan(
        plan_id="plan_crash",
        original_query="trigger crash",
        intent="understand",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="crashing_tool",
                purpose="Crashes unexpectedly",
                is_required=True,
            )
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.FAILED
    assert result.step_results[0].status == ToolStatus.ERROR
    assert "Simulated unhandled fatal exception" in result.step_results[0].error_message


def test_unknown_tool_handling():
    """Verify unknown tool names are handled gracefully."""
    registry = ToolRegistry()

    plan = InvestigationPlan(
        plan_id="plan_unknown",
        original_query="run unknown",
        intent="understand",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="completely_unknown_tool",
                purpose="Does not exist",
                is_required=True,
            )
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.FAILED
    assert result.step_results[0].status == ToolStatus.ERROR
    assert "not registered" in result.step_results[0].error_message


def test_deferred_tools_never_invoked():
    """Verify deferred tool execute / _run method is never called by orchestrator."""
    registry = ToolRegistry()

    class SpyDeferredTool(DeferredTool):
        def __init__(self):
            super().__init__(
                name="git_code_churn",
                description="Spy deferred tool",
                target_phase="Phase 7: Git Temporal Intelligence",
            )
            self.invoked = False

        def _run(self, arguments):
            self.invoked = True
            return super()._run(arguments)

        def execute(self, arguments=None):
            self.invoked = True
            return super().execute(arguments)

    spy_tool = SpyDeferredTool()
    registry.register(spy_tool)

    plan = InvestigationPlan(
        plan_id="plan_deferred_spy",
        original_query="check churn",
        intent="evolution",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="git_code_churn",
                purpose="Should be deferred",
                is_required=True,
            )
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.DEFERRED
    assert spy_tool.invoked is False, "Deferred tool execute/run was invoked!"


def test_deterministic_execution():
    """Verify identical plans with identical inputs yield identical execution results."""
    registry = ToolRegistry()
    registry.register(MockSuccessTool("t1"))
    registry.register(MockSuccessTool("t2"))

    plan = InvestigationPlan(
        plan_id="plan_deterministic",
        original_query="deterministic run",
        intent="understand",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="t1",
                input_parameters={"input_val": "data_x"},
                is_required=True,
            ),
            PlanStep(
                step_id="step_2",
                tool_name="t2",
                input_parameters={"input_val": "$step_1.echo"},
                dependencies=["step_1"],
                is_required=True,
            ),
        ],
    )

    orchestrator = InvestigationOrchestrator(registry=registry)
    run_1 = orchestrator.execute(plan)
    run_2 = orchestrator.execute(plan)

    assert run_1.overall_status == run_2.overall_status
    assert len(run_1.step_results) == len(run_2.step_results)
    for r1, r2 in zip(run_1.step_results, run_2.step_results):
        assert r1.step_id == r2.step_id
        assert r1.status == r2.status
        assert r1.output == r2.output


def test_end_to_end_planner_and_orchestrator():
    """Verify complete pipeline: Intent -> Planner -> Plan -> Orchestrator -> Result."""
    from codemind.investigation.planner import InvestigationPlanner

    registry = ToolRegistry()

    class SearchStub(BaseTool):
        @property
        def name(self) -> str:
            return "search_symbols"
        @property
        def description(self) -> str:
            return "search symbols"
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(tool_name="search_symbols", description="search")
        def _run(self, args):
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "is_ambiguous": False,
                    "total_matches": 1,
                    "primary_node_id": "function:codemind/auth.py:verify_token",
                    "primary_relative_path": "codemind/auth.py",
                    "matches": [{
                        "id": "function:codemind/auth.py:verify_token",
                        "name": "verify_token",
                        "relative_path": "codemind/auth.py",
                        "start_line": 15,
                        "end_line": 30,
                        "node_type": "function",
                    }],
                },
            )

    class NodeDetailsStub(BaseTool):
        @property
        def name(self) -> str:
            return "get_node_details"
        @property
        def description(self) -> str:
            return "node details"
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(tool_name="get_node_details", description="node")
        def _run(self, args):
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "id": args.get("node_id"),
                    "name": "verify_token",
                    "relative_path": "codemind/auth.py",
                    "start_line": 15,
                    "end_line": 30,
                    "node_type": "function",
                    "found": True,
                },
            )

    class CallersStub(BaseTool):
        @property
        def name(self) -> str:
            return "get_callers"
        @property
        def description(self) -> str:
            return "get callers"
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(tool_name="get_callers", description="callers")
        def _run(self, args):
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "node_id": args.get("node_id"),
                    "total_callers": 1,
                    "callers": [{
                        "id": "function:codemind/api.py:login",
                        "name": "login",
                        "relative_path": "codemind/api.py",
                        "start_line": 10,
                        "end_line": 20,
                        "node_type": "function",
                    }],
                },
            )

    registry.register(SearchStub())
    registry.register(NodeDetailsStub())
    registry.register(CallersStub())

    planner = InvestigationPlanner()
    plan = planner.plan("Who calls verify_token?", registry=registry)

    assert len(plan.steps) >= 3
    orchestrator = InvestigationOrchestrator(registry=registry)
    result = orchestrator.execute(plan)

    assert result.overall_status == InvestigationStatus.SUCCESS
    assert len(result.step_results) == len(plan.steps)
    assert all(r.status == ToolStatus.SUCCESS for r in result.step_results)
    assert len(result.evidence) >= 2
    assert any(e["category"] == "code" for e in result.evidence)
    assert any(e["category"] == "graph" for e in result.evidence)
