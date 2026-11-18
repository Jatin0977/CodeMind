"""
Unit and integration tests for InvestigationEngine in CodeMind (Phase 6, Milestone 5).
Tests the unified pipeline: query validation, classification, planning, orchestration,
evidence aggregation, answer synthesis, statelessness, and dependency injection.
"""

from typing import Dict, Any, Optional
import pytest

from codemind.investigation.models import (
    InvestigationResult,
    InvestigationStatus,
    InvestigationPlan,
    PlanStep,
    ToolStatus,
    ToolAvailability,
    ToolDefinition,
)
from codemind.investigation.tools.base import BaseTool, ToolResult, DeferredTool
from codemind.investigation.tools.registry import ToolRegistry
from codemind.investigation.intent import InvestigationIntentClassifier
from codemind.investigation.planner import InvestigationPlanner
from codemind.investigation.orchestrator import InvestigationOrchestrator
from codemind.investigation.synthesizer import InvestigationSynthesizer
from codemind.investigation.engine import (
    InvestigationEngine,
    create_investigation_engine,
)
from codemind.rag.providers.base import BaseLLMProvider


class MockSearchTool(BaseTool):
    """Stub search_symbols tool for engine tests."""

    def __init__(self, target_entity: str = "AuthService", ambiguous: bool = False):
        self._target_entity = target_entity
        self._ambiguous = ambiguous
        self._def = ToolDefinition(
            tool_name="search_symbols",
            description="Mock search_symbols",
            input_schema={"type": "object"},
            availability=ToolAvailability.AVAILABLE,
        )

    @property
    def name(self) -> str:
        return "search_symbols"

    @property
    def description(self) -> str:
        return self._def.description

    @property
    def definition(self) -> ToolDefinition:
        return self._def

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self._ambiguous:
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "is_ambiguous": True,
                    "total_matches": 2,
                    "primary_node_id": f"class:codemind/auth.py:{self._target_entity}",
                    "matches": [
                        {"id": f"class:codemind/auth.py:{self._target_entity}", "name": self._target_entity, "relative_path": "codemind/auth.py", "start_line": 10, "end_line": 40},
                        {"id": f"class:codemind/auth_v2.py:{self._target_entity}", "name": self._target_entity, "relative_path": "codemind/auth_v2.py", "start_line": 10, "end_line": 40},
                    ],
                },
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "is_ambiguous": False,
                "total_matches": 1,
                "primary_node_id": f"class:codemind/auth.py:{self._target_entity}",
                "primary_relative_path": "codemind/auth.py",
                "matches": [
                    {
                        "id": f"class:codemind/auth.py:{self._target_entity}",
                        "name": self._target_entity,
                        "relative_path": "codemind/auth.py",
                        "start_line": 10,
                        "end_line": 50,
                        "node_type": "class",
                    }
                ],
            },
        )


class MockDetailsTool(BaseTool):
    """Stub get_node_details tool."""

    @property
    def name(self) -> str:
        return "get_node_details"

    @property
    def description(self) -> str:
        return "Mock get_node_details"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(tool_name="get_node_details", description="Mock")

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        node_id = arguments.get("node_id", "unknown")
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "id": node_id,
                "name": "AuthService",
                "relative_path": "codemind/auth.py",
                "start_line": 10,
                "end_line": 50,
                "found": True,
            },
        )


class MockCallersTool(BaseTool):
    """Stub get_callers tool."""

    @property
    def name(self) -> str:
        return "get_callers"

    @property
    def description(self) -> str:
        return "Mock get_callers"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(tool_name="get_callers", description="Mock")

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "node_id": arguments.get("node_id"),
                "total_callers": 1,
                "callers": [
                    {
                        "id": "function:codemind/api.py:login",
                        "name": "login",
                        "relative_path": "codemind/api.py",
                        "start_line": 20,
                        "end_line": 30,
                    }
                ],
            },
        )


def _build_test_registry(ambiguous_search: bool = False) -> ToolRegistry:
    """Helper to build a registry with mock code and graph tools."""
    reg = ToolRegistry()
    reg.register(MockSearchTool("AuthService", ambiguous=ambiguous_search))
    reg.register(MockDetailsTool())
    reg.register(MockCallersTool())
    reg.register(DeferredTool(
        name="git_code_churn",
        description="Deferred churn tool",
        target_phase="Phase 7: Git Temporal Intelligence",
    ))
    return reg


def test_complete_end_to_end_pipeline():
    """Verify single call to engine.investigate() executes full pipeline cleanly."""
    registry = _build_test_registry()
    engine = InvestigationEngine(registry=registry)

    result = engine.investigate("Explain how AuthService is structured")

    assert result.overall_status == InvestigationStatus.SUCCESS
    assert result.plan is not None
    assert len(result.plan.steps) >= 2
    assert len(result.step_results) == len(result.plan.steps)
    assert all(r.status == ToolStatus.SUCCESS for r in result.step_results)
    assert len(result.evidence) >= 1
    assert result.final_answer is not None
    assert "AuthService" in result.final_answer
    assert "[codemind/auth.py:10-50]" in result.final_answer
    assert "Direct Answer" in result.final_answer
    assert "citations" in result.metadata
    assert result.metadata["engine"]["version"] == "1.0"


def test_empty_and_invalid_queries():
    """Verify empty, whitespace, and non-string queries fail safely with structured error."""
    engine = InvestigationEngine(registry=_build_test_registry())

    # Empty string
    r1 = engine.investigate("")
    assert r1.overall_status == InvestigationStatus.FAILED
    assert "cannot be empty" in r1.final_answer.lower()
    assert r1.metadata["error"] == "empty_query"

    # Whitespace only
    r2 = engine.investigate("   \t\n  ")
    assert r2.overall_status == InvestigationStatus.FAILED
    assert "cannot be empty" in r2.final_answer.lower()

    # None input
    r3 = engine.investigate(None)  # type: ignore
    assert r3.overall_status == InvestigationStatus.FAILED


def test_repeated_independent_investigations_statelessness():
    """Verify multiple investigations on the same engine instance do not contaminate each other."""
    registry = _build_test_registry()
    engine = InvestigationEngine(registry=registry)

    res1 = engine.investigate("Explain AuthService")
    res2 = engine.investigate("Who calls verify_token?")

    assert res1.query == "Explain AuthService"
    assert res2.query == "Who calls verify_token?"
    assert res1.plan.plan_id != res2.plan.plan_id
    assert res1.plan.original_query != res2.plan.original_query
    # Evidence counts and items must be cleanly isolated
    assert res1.metadata["engine"]["classification"]["extracted_entities"]["primary_entity"] == "AuthService"
    assert res2.metadata["engine"]["classification"]["extracted_entities"]["primary_entity"] == "verify_token"


def test_deferred_only_investigation():
    """Verify engine handles a purely deferred query (e.g. churn analysis) gracefully."""
    reg = ToolRegistry()
    reg.register(DeferredTool(
        name="git_code_churn",
        description="Deferred churn",
        target_phase="Phase 7: Git Temporal Intelligence",
    ))
    reg.register(DeferredTool(
        name="git_commit_history",
        description="Deferred commits",
        target_phase="Phase 7: Git Temporal Intelligence",
    ))

    engine = InvestigationEngine(registry=reg)
    result = engine.investigate("Show Git churn and commit history over time for auth.py")

    assert result.overall_status == InvestigationStatus.DEFERRED
    assert "Phase 7: Git Temporal Intelligence" in result.final_answer
    assert "No analytical outputs were simulated or fabricated" in result.final_answer


def test_partial_success_with_ambiguous_entity():
    """Verify engine handles ambiguous symbol lookup by skipping dependent step safely."""
    registry = _build_test_registry(ambiguous_search=True)
    engine = InvestigationEngine(registry=registry)

    result = engine.investigate("Who calls AuthService?")

    assert result.overall_status == InvestigationStatus.PARTIAL_SUCCESS
    # Step 1 (search) succeeded
    assert result.step_results[0].status == ToolStatus.SUCCESS
    # Step 2 (get_node_details) skipped due to ambiguity
    assert result.step_results[1].status == ToolStatus.SKIPPED
    assert "ambiguous" in result.step_results[1].warning.lower()
    # Answer mentions ambiguity
    assert "ambiguous" in result.final_answer.lower() or "candidate" in result.final_answer.lower()


def test_dependency_injection_with_custom_test_doubles():
    """Verify engine respects injected custom classifier, planner, orchestrator, synthesizer."""
    mock_registry = ToolRegistry()
    mock_classifier = InvestigationIntentClassifier()
    mock_planner = InvestigationPlanner(classifier=mock_classifier)
    mock_orchestrator = InvestigationOrchestrator(registry=mock_registry)
    mock_synthesizer = InvestigationSynthesizer(use_fallback_only=True)

    engine = InvestigationEngine(
        registry=mock_registry,
        classifier=mock_classifier,
        planner=mock_planner,
        orchestrator=mock_orchestrator,
        synthesizer=mock_synthesizer,
    )

    assert engine.registry is mock_registry
    assert engine.classifier is mock_classifier
    assert engine.planner is mock_planner
    assert engine.orchestrator is mock_orchestrator
    assert engine.synthesizer is mock_synthesizer


def test_investigation_result_serialization_round_trip():
    """Verify InvestigationResult to_dict and from_dict round-trip retains all fields."""
    registry = _build_test_registry()
    engine = InvestigationEngine(registry=registry)

    result = engine.investigate("Explain AuthService")
    d = result.to_dict()

    assert isinstance(d, dict)
    assert d["query"] == "Explain AuthService"
    assert d["overall_status"] == "SUCCESS"
    assert "citations" in d["metadata"]
    assert len(d["step_results"]) > 0

    reconstructed = InvestigationResult.from_dict(d)
    assert reconstructed.query == result.query
    assert reconstructed.overall_status == result.overall_status
    assert len(reconstructed.step_results) == len(result.step_results)


def test_convenience_factory():
    """Verify create_investigation_engine constructs a working engine."""
    engine = create_investigation_engine()
    assert isinstance(engine, InvestigationEngine)
    assert engine.registry.count() >= 17  # All 17 tools registered by default
