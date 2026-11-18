"""
Unit tests for variable-reference resolver in CodeMind Agentic Investigation Engine (Phase 6, Milestone 4).
Tests safe path navigation, type preservation, ambiguity detection, and strict expression evaluation prevention.
"""

import pytest
from codemind.investigation.models import StepResult, ToolStatus
from codemind.investigation.resolver import (
    ReferenceResolver,
    resolve_step_parameters,
    MalformedReferenceError,
    StepNotFoundError,
    StepNotSuccessfulError,
    FieldNotFoundError,
    AmbiguousSymbolError,
    UnavailableValueError,
)


def test_valid_simple_reference():
    """Verify simple reference resolution like '$step_1.primary_node_id'."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={
                "is_ambiguous": False,
                "total_matches": 1,
                "primary_node_id": "function:codemind/auth.py:verify_token",
            },
        )
    }

    res = resolve_step_parameters({"node_id": "$step_1.primary_node_id"}, completed)
    assert res.is_success is True
    assert res.resolved_parameters["node_id"] == "function:codemind/auth.py:verify_token"


def test_nested_dictionary_reference():
    """Verify nested dictionary resolution like '$step_1.details.metadata.author'."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="custom_tool",
            status=ToolStatus.SUCCESS,
            output={"details": {"metadata": {"author": "Alice", "version": 2}}},
        )
    }

    res = resolve_step_parameters(
        {"author": "$step_1.details.metadata.author", "version": "$step_1.details.metadata.version"},
        completed,
    )
    assert res.is_success is True
    assert res.resolved_parameters["author"] == "Alice"
    assert res.resolved_parameters["version"] == 2
    assert isinstance(res.resolved_parameters["version"], int)


def test_list_indexing_reference():
    """Verify indexed array access like '$step_1.matches[0].name'."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={
                "is_ambiguous": False,
                "total_matches": 1,
                "matches": [{"id": "fn_1", "name": "process_data", "line": 42}],
            },
        )
    }

    res = resolve_step_parameters(
        {"target_name": "$step_1.matches[0].name", "line": "$step_1.matches[0].line"},
        completed,
    )
    assert res.is_success is True
    assert res.resolved_parameters["target_name"] == "process_data"
    assert res.resolved_parameters["line"] == 42
    assert isinstance(res.resolved_parameters["line"], int)


def test_missing_step_reference():
    """Verify missing step results in clear is_missing failure."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={"primary_node_id": "node_123"},
        )
    }

    res = resolve_step_parameters({"node_id": "$step_99.primary_node_id"}, completed)
    assert res.is_success is False
    assert res.is_missing is True
    assert res.missing_step_id == "step_99"
    assert "step_99" in res.error_message


def test_missing_output_field():
    """Verify missing field in output fails resolution."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={"primary_node_id": "node_123"},
        )
    }

    res = resolve_step_parameters({"target": "$step_1.nonexistent_field"}, completed)
    assert res.is_success is False
    assert res.is_missing is True
    assert "nonexistent_field" in res.error_message


def test_malformed_reference_syntax():
    """Verify malformed reference strings are rejected without evaluation."""
    resolver = ReferenceResolver()
    completed = {}

    malformed_examples = [
        "step_1.primary_node_id",  # Missing leading $
        "$step_1",                 # Missing path
        "$step_1..field",          # Double dot
        "$step_1.field.",          # Trailing dot
        "$step_1.field[abc]",      # Non-integer index
        "$step_1.field[]",         # Empty index
        "$",                       # Bare dollar
    ]

    for expr in malformed_examples:
        with pytest.raises(MalformedReferenceError):
            resolver.parse_reference(expr)


def test_null_output_values():
    """Verify null or None outputs are treated as unavailable."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="custom_tool",
            status=ToolStatus.SUCCESS,
            output={"nullable_field": None},
        )
    }

    res = resolve_step_parameters({"val": "$step_1.nullable_field"}, completed)
    assert res.is_success is False
    assert res.is_missing is True
    assert "None" in res.error_message


def test_failed_upstream_step():
    """Verify that referencing an ERROR or SKIPPED step fails resolution."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.ERROR,
            output=None,
            error_message="Search failed",
        )
    }

    res = resolve_step_parameters({"node_id": "$step_1.primary_node_id"}, completed)
    assert res.is_success is False
    assert "did not complete successfully" in res.error_message


def test_deferred_upstream_step():
    """Verify referencing a deferred tool step fails resolution."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="git_code_churn",
            status=ToolStatus.UNAVAILABLE_DEFERRED,
            output=None,
        )
    }

    res = resolve_step_parameters({"churn": "$step_1.churn_score"}, completed)
    assert res.is_success is False
    assert "UNAVAILABLE_DEFERRED" in res.error_message


def test_ambiguous_symbol_results():
    """Verify ambiguous symbol search results prevent binding unique primary_node_id."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={
                "is_ambiguous": True,
                "total_matches": 3,
                "primary_node_id": "function:a.py:run",
                "matches": [
                    {"id": "function:a.py:run", "name": "run"},
                    {"id": "function:b.py:run", "name": "run"},
                    {"id": "function:c.py:run", "name": "run"},
                ],
            },
        )
    }

    res = resolve_step_parameters({"node_id": "$step_1.primary_node_id"}, completed)
    assert res.is_success is False
    assert res.is_ambiguous is True
    assert res.ambiguous_step_id == "step_1"
    assert "ambiguous" in res.error_message.lower()


def test_zero_match_symbol_results():
    """Verify zero-match symbol search results fail resolution as missing/unavailable."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="search_symbols",
            status=ToolStatus.SUCCESS,
            output={
                "is_ambiguous": False,
                "total_matches": 0,
                "primary_node_id": None,
                "matches": [],
            },
        )
    }

    res = resolve_step_parameters({"node_id": "$step_1.primary_node_id"}, completed)
    assert res.is_success is False
    assert res.is_missing is True
    assert "zero matches" in res.error_message.lower()


def test_type_preservation():
    """Verify original data types (int, float, bool, list, dict) are preserved."""
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="mock_tool",
            status=ToolStatus.SUCCESS,
            output={
                "int_val": 42,
                "float_val": 3.14159,
                "bool_val": True,
                "list_val": ["alpha", "beta"],
                "dict_val": {"nested": "value"},
            },
        )
    }

    params = {
        "count": "$step_1.int_val",
        "ratio": "$step_1.float_val",
        "flag": "$step_1.bool_val",
        "items": "$step_1.list_val",
        "conf": "$step_1.dict_val",
    }

    res = resolve_step_parameters(params, completed)
    assert res.is_success is True
    assert res.resolved_parameters["count"] == 42
    assert isinstance(res.resolved_parameters["count"], int)
    assert res.resolved_parameters["ratio"] == 3.14159
    assert isinstance(res.resolved_parameters["ratio"], float)
    assert res.resolved_parameters["flag"] is True
    assert isinstance(res.resolved_parameters["flag"], bool)
    assert res.resolved_parameters["items"] == ["alpha", "beta"]
    assert isinstance(res.resolved_parameters["items"], list)
    assert res.resolved_parameters["conf"] == {"nested": "value"}
    assert isinstance(res.resolved_parameters["conf"], dict)


def test_no_arbitrary_expression_evaluation():
    """Verify dangerous Python expressions and calls are strictly rejected without eval/exec."""
    resolver = ReferenceResolver()
    dangerous_inputs = [
        "$step_1.eval('1+1')",
        "$step_1.__import__('os').system('ls')",
        "$step_1.exec('print(1)')",
        "$step_1.data; import os",
        "$step_1.field + 1",
        "$step_1.data[__import__('sys')]",
    ]

    for expr in dangerous_inputs:
        with pytest.raises(MalformedReferenceError):
            resolver.parse_reference(expr)
