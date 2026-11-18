"""
Unit tests for EvidenceCollector in CodeMind Agentic Investigation Engine (Phase 6, Milestone 4).
Tests evidence extraction, provenance preservation, deduplication, and serialization.
"""

from codemind.investigation.models import StepResult, ToolStatus, ToolDefinition, ToolAvailability
from codemind.investigation.collector import EvidenceItem, EvidenceCollector


def test_code_evidence_search_symbols():
    """Verify code evidence extraction from search_symbols output."""
    collector = EvidenceCollector()
    step_res = StepResult(
        step_id="step_1",
        tool_name="search_symbols",
        status=ToolStatus.SUCCESS,
        output={
            "query": "AuthService",
            "is_ambiguous": False,
            "total_matches": 1,
            "matches": [
                {
                    "id": "class:codemind/auth.py:AuthService",
                    "name": "AuthService",
                    "relative_path": "codemind/auth.py",
                    "start_line": 10,
                    "end_line": 50,
                    "node_type": "class",
                }
            ],
        },
    )

    added = collector.collect_from_step(step_res)
    assert added == 1
    assert len(collector) == 1
    item = collector.items[0]
    assert item.category == "code"
    assert item.source_tool == "search_symbols"
    assert item.source_step_id == "step_1"
    assert item.symbol_name == "AuthService"
    assert item.relative_path == "codemind/auth.py"
    assert item.start_line == 10
    assert item.end_line == 50
    assert item.provenance == "symbol_search"
    assert item.metadata.get("node_id") == "class:codemind/auth.py:AuthService"


def test_code_evidence_file_content():
    """Verify code evidence extraction from get_file_content."""
    collector = EvidenceCollector()
    step_res = StepResult(
        step_id="step_2",
        tool_name="get_file_content",
        status=ToolStatus.SUCCESS,
        output={
            "relative_path": "codemind/config.py",
            "start_line": 1,
            "end_line": 20,
            "total_lines": 20,
            "line_count_returned": 20,
            "content": "class Config:\n    DEBUG = True",
        },
    )

    collector.collect_from_step(step_res)
    assert len(collector) == 1
    item = collector.items[0]
    assert item.category == "code"
    assert item.source_tool == "get_file_content"
    assert item.relative_path == "codemind/config.py"
    assert item.start_line == 1
    assert item.end_line == 20
    assert "DEBUG = True" in item.content
    assert item.provenance == "file_content"


def test_graph_evidence_callers_and_callees():
    """Verify graph evidence extraction and provenance for get_callers and get_callees."""
    collector = EvidenceCollector()

    # Callers step
    res_callers = StepResult(
        step_id="step_1",
        tool_name="get_callers",
        status=ToolStatus.SUCCESS,
        output={
            "node_id": "function:codemind/auth.py:verify_token",
            "callers": [
                {
                    "id": "function:codemind/api.py:login_endpoint",
                    "name": "login_endpoint",
                    "relative_path": "codemind/api.py",
                    "start_line": 25,
                    "end_line": 35,
                    "node_type": "function",
                }
            ],
        },
    )
    collector.collect_from_step(res_callers)

    # Callees step
    res_callees = StepResult(
        step_id="step_2",
        tool_name="get_callees",
        status=ToolStatus.SUCCESS,
        output={
            "node_id": "function:codemind/auth.py:verify_token",
            "callees": [
                {
                    "id": "function:codemind/crypto.py:decode_jwt",
                    "name": "decode_jwt",
                    "relative_path": "codemind/crypto.py",
                    "start_line": 5,
                    "end_line": 15,
                    "node_type": "function",
                }
            ],
        },
    )
    collector.collect_from_step(res_callees)

    assert len(collector) == 2
    graph_items = collector.filter_by_category("graph")
    assert len(graph_items) == 2

    # Check caller provenance
    caller_item = graph_items[0]
    assert caller_item.source_tool == "get_callers"
    assert caller_item.graph_source == "function:codemind/api.py:login_endpoint"
    assert caller_item.graph_target == "function:codemind/auth.py:verify_token"
    assert caller_item.relationship_type == "CALLS"
    assert caller_item.provenance == "graph_caller"

    # Check callee provenance
    callee_item = graph_items[1]
    assert callee_item.source_tool == "get_callees"
    assert callee_item.graph_source == "function:codemind/auth.py:verify_token"
    assert callee_item.graph_target == "function:codemind/crypto.py:decode_jwt"
    assert callee_item.relationship_type == "CALLS"
    assert callee_item.provenance == "graph_callee"


def test_graph_evidence_dependencies_and_dependents():
    """Verify graph evidence for get_dependencies, get_dependents, and cycles."""
    collector = EvidenceCollector()

    res_deps = StepResult(
        step_id="step_1",
        tool_name="get_dependencies",
        status=ToolStatus.SUCCESS,
        output={
            "node_id": "file:codemind/main.py",
            "dependencies": [
                {
                    "id": "file:codemind/cli.py",
                    "name": "cli.py",
                    "relative_path": "codemind/cli.py",
                    "relationship": "IMPORTS",
                    "node_type": "file",
                }
            ],
        },
    )
    collector.collect_from_step(res_deps)

    res_cycles = StepResult(
        step_id="step_2",
        tool_name="detect_cycles",
        status=ToolStatus.SUCCESS,
        output={
            "cycles": [["file:a.py", "file:b.py", "file:a.py"]],
        },
    )
    collector.collect_from_step(res_cycles)

    assert len(collector) == 2
    dep_item = collector.items[0]
    assert dep_item.relationship_type == "IMPORTS"
    assert dep_item.graph_source == "file:codemind/main.py"
    assert dep_item.graph_target == "file:codemind/cli.py"

    cycle_item = collector.items[1]
    assert cycle_item.relationship_type == "CYCLE"
    assert cycle_item.provenance == "cycle_detection"


def test_retrieval_evidence():
    """Verify retrieval evidence provenance and score preservation."""
    collector = EvidenceCollector()

    res_hybrid = StepResult(
        step_id="step_1",
        tool_name="hybrid_search",
        status=ToolStatus.SUCCESS,
        output={
            "query": "authentication workflow",
            "results": [
                {
                    "chunk": {
                        "id": "chk_101",
                        "relative_path": "codemind/auth.py",
                        "start_line": 20,
                        "end_line": 40,
                        "content": "def authenticate(user, pwd): ...",
                    },
                    "score": 0.8921,
                    "provenance": "graph_expanded",
                    "relationship_type": "CALLS",
                }
            ],
        },
    )
    collector.collect_from_step(res_hybrid)

    assert len(collector) == 1
    item = collector.items[0]
    assert item.category == "retrieval"
    assert item.source_tool == "hybrid_search"
    assert item.score == 0.8921
    assert item.provenance == "graph_expanded"
    assert item.relationship_type == "CALLS"
    assert item.relative_path == "codemind/auth.py"
    assert item.start_line == 20
    assert item.end_line == 40
    assert item.content == "def authenticate(user, pwd): ..."


def test_deferred_capability_evidence():
    """Verify deferred tool records are accurately recorded as deferred evidence."""
    collector = EvidenceCollector()
    tool_def = ToolDefinition(
        tool_name="git_commit_history",
        description="Mines Git history",
        availability=ToolAvailability.DEFERRED,
        target_phase="Phase 7: Git Temporal Intelligence",
    )
    step_res = StepResult(
        step_id="step_3",
        tool_name="git_commit_history",
        status=ToolStatus.UNAVAILABLE_DEFERRED,
        output=None,
        warning="Deferred tool",
    )

    collector.collect_from_step(step_res, tool_def)
    assert len(collector) == 1
    item = collector.items[0]
    assert item.category == "deferred"
    assert item.source_tool == "git_commit_history"
    assert item.target_phase == "Phase 7: Git Temporal Intelligence"
    assert item.provenance == "deferred_placeholder"


def test_deduplication():
    """Verify deduplication avoids inserting duplicate identical items."""
    collector = EvidenceCollector()
    item1 = EvidenceItem(
        category="code",
        source_tool="search_symbols",
        source_step_id="step_1",
        relative_path="codemind/a.py",
        start_line=10,
        end_line=20,
        symbol_name="foo",
    )
    item2 = EvidenceItem(
        category="code",
        source_tool="get_node_details",
        source_step_id="step_2",
        relative_path="codemind/a.py",
        start_line=10,
        end_line=20,
        symbol_name="foo",
    )

    added1 = collector.add_item(item1)
    added2 = collector.add_item(item2)

    assert added1 is True
    assert added2 is False  # Deduplicated based on code location and symbol
    assert len(collector) == 1


def test_evidence_serialization():
    """Verify to_list, to_dict, and from_dict round-trip serialization."""
    item = EvidenceItem(
        category="code",
        source_tool="get_file_content",
        source_step_id="step_1",
        content="print('hello')",
        relative_path="main.py",
        start_line=1,
        end_line=1,
        symbol_name=None,
        score=0.95,
        metadata={"custom": "val"},
    )
    d = item.to_dict()
    assert d["category"] == "code"
    assert d["score"] == 0.95
    assert d["content"] == "print('hello')"

    item_reconstructed = EvidenceItem.from_dict(d)
    assert item_reconstructed.category == item.category
    assert item_reconstructed.source_tool == item.source_tool
    assert item_reconstructed.metadata == item.metadata
