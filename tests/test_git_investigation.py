"""
Unit and integration tests for Milestone 5: Investigation Engine Git Integration.
Verifies active Git tools, deferred tool exclusion, intent classification,
query-dependent sub-intent planning, evidence collection, and report synthesis.
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock

from codemind.investigation.tools import create_tool_registry
from codemind.investigation.tools.git_tools import (
    GitCommitHistoryTool,
    GitCodeChurnTool,
    GitLogicalCouplingTool,
)
from codemind.investigation.models import ToolStatus, ToolAvailability
from codemind.investigation.intent import InvestigationIntentClassifier, InvestigationIntent
from codemind.investigation.planner import InvestigationPlanner
from codemind.investigation.collector import EvidenceCollector, EvidenceItem
from codemind.investigation.synthesizer import InvestigationSynthesizer
from codemind.investigation.models import StepResult, InvestigationResult, InvestigationStatus
from codemind.git.models import CommitRecord, FileChange, FileChangeStatus
from codemind.git.churn import FileChurnMetrics, RepositoryChurnSummary
from codemind.git.coupling import LogicalCoupling


def test_tool_registry_has_active_git_tools_and_no_deferred_git():
    """Verify Git tools are registered as active AVAILABLE tools and not in deferred tools."""
    registry = create_tool_registry(enable_git=True)

    assert registry.has_tool("git_commit_history")
    assert registry.has_tool("git_code_churn")
    assert registry.has_tool("git_logical_coupling")

    # Availability must be AVAILABLE, not UNAVAILABLE_DEFERRED
    hist_tool = registry.get_tool("git_commit_history")
    churn_tool = registry.get_tool("git_code_churn")
    coup_tool = registry.get_tool("git_logical_coupling")

    assert hist_tool.availability == ToolAvailability.AVAILABLE
    assert churn_tool.availability == ToolAvailability.AVAILABLE
    assert coup_tool.availability == ToolAvailability.AVAILABLE

    # Deferred tools should now only contain Phase 8 & 9 tools
    deferred = registry.list_deferred()
    deferred_names = [d.name for d in deferred]
    assert "git_commit_history" not in deferred_names
    assert "git_code_churn" not in deferred_names
    assert "git_logical_coupling" not in deferred_names
    assert "multi_signal_impact" in deferred_names
    assert "get_test_coverage" in deferred_names
    assert "detect_maintenance_hotspots" in deferred_names
    assert "check_architecture_conformance" in deferred_names


def test_git_tools_execution_with_mock_subsystem():
    """Verify execution of active Git tools returning structured ToolResult."""
    mock_miner = MagicMock()
    mock_commit = CommitRecord(
        full_hash="1234567890abcdef1234567890abcdef12345678",
        short_hash="1234567",
        author_name="Bob Engineer",
        author_email="bob@example.com",
        author_date=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        subject="feat: add telemetry",
        parents=["parent123"],
        is_merge=False,
        files_changed=[FileChange(status="M", path="src/telemetry.py", additions=15, deletions=2)],
    )
    mock_miner.mine_commits.return_value = [mock_commit]

    # 1. Test GitCommitHistoryTool
    hist_tool = GitCommitHistoryTool(git_miner=mock_miner)
    res_hist = hist_tool.execute({"path": "src/telemetry.py", "limit": 10})
    assert res_hist.is_success
    assert res_hist.data["total_commits"] == 1
    assert res_hist.data["commits"][0]["short_hash"] == "1234567"

    # 2. Test GitCodeChurnTool
    mock_churn_analyzer = MagicMock()
    mock_churn_metric = FileChurnMetrics(
        path="src/telemetry.py",
        commit_frequency=5,
        additions=100,
        deletions=20,
        total_churn=120,
        distinct_author_count=2,
    )
    mock_churn_analyzer.get_top_churn_files.return_value = [mock_churn_metric]
    mock_churn_analyzer.summary = RepositoryChurnSummary(
        total_commits_analyzed=10,
        total_files_analyzed=1,
        total_additions=100,
        total_deletions=20,
    )

    churn_tool = GitCodeChurnTool(churn_analyzer=mock_churn_analyzer)
    res_churn = churn_tool.execute({"limit": 5, "sort_by": "commits"})
    assert res_churn.is_success
    assert res_churn.data["total_returned"] == 1
    assert res_churn.data["hotspots"][0]["path"] == "src/telemetry.py"
    assert res_churn.data["hotspots"][0]["commits_count"] == 5

    # 3. Test GitLogicalCouplingTool
    mock_coupling_analyzer = MagicMock()
    mock_coupling = LogicalCoupling(
        canonical_file_a="src/db.py",
        canonical_file_b="src/telemetry.py",
        support_count=4,
        jaccard_similarity=0.8,
        confidence_a_to_b=0.8,
        confidence_b_to_a=1.0,
        last_co_change_date="2026-03-01T10:00:00+00:00",
    )
    mock_coupling_analyzer.get_top_couplings.return_value = [mock_coupling]
    mock_coupling_analyzer.get_couplings_for_file.return_value = [mock_coupling.oriented_for("src/db.py")]

    coup_tool = GitLogicalCouplingTool(coupling_analyzer=mock_coupling_analyzer)
    res_coup_repo = coup_tool.execute({"limit": 10})
    assert res_coup_repo.is_success
    assert res_coup_repo.data["total_couplings"] == 1

    res_coup_file = coup_tool.execute({"file_path": "src/db.py", "limit": 10})
    assert res_coup_file.is_success
    assert res_coup_file.data["focal_file"] == "src/db.py"
    assert res_coup_file.data["couplings"][0]["target_file"] == "src/telemetry.py"


def test_intent_classification_for_evolution_and_coupling():
    """Verify intent classifier routes history, churn, and logical coupling queries to EVOLUTION."""
    classifier = InvestigationIntentClassifier()

    queries = [
        ("Show commit history of src/auth.py", InvestigationIntent.EVOLUTION),
        ("Who modified the tokenizer recently?", InvestigationIntent.EVOLUTION),
        ("What is the code churn of the repository?", InvestigationIntent.EVOLUTION),
        ("Which files frequently change together with src/models.py?", InvestigationIntent.EVOLUTION),
        ("Show logical coupling for parser.py", InvestigationIntent.EVOLUTION),
        ("Which files are co-changed with utils.py?", InvestigationIntent.EVOLUTION),
    ]

    for q, expected_intent in queries:
        result = classifier.classify(q)
        assert result.intent == expected_intent, f"Query '{q}' classified as {result.intent}, expected {expected_intent}"


def test_query_dependent_planner_sub_intent_routing():
    """Verify planner routes history, churn, coupling, and general evolution to distinct tool sets."""
    registry = create_tool_registry(enable_git=True)
    planner = InvestigationPlanner()

    # 1. History sub-intent
    plan_hist = planner.plan("Show commit history of src/auth.py", registry=registry)
    hist_tool_names = [s.tool_name for s in plan_hist.steps]
    assert "git_commit_history" in hist_tool_names
    assert "git_logical_coupling" not in hist_tool_names

    # 2. Churn sub-intent
    plan_churn = planner.plan("Show top code churn hotspots", registry=registry)
    churn_tool_names = [s.tool_name for s in plan_churn.steps]
    assert "git_code_churn" in churn_tool_names
    assert "git_logical_coupling" not in churn_tool_names

    # 3. Coupling sub-intent
    plan_coup = planner.plan("Which files co-change together with src/auth.py?", registry=registry)
    coup_tool_names = [s.tool_name for s in plan_coup.steps]
    assert "git_logical_coupling" in coup_tool_names
    assert "git_commit_history" not in coup_tool_names

    # 4. General evolution query -> composite
    plan_gen = planner.plan("How has src/auth.py evolved over time?", registry=registry)
    gen_tool_names = [s.tool_name for s in plan_gen.steps]
    assert "git_commit_history" in gen_tool_names
    assert "git_code_churn" in gen_tool_names
    assert "git_logical_coupling" in gen_tool_names


def test_evidence_collector_and_synthesizer_temporal():
    """Verify EvidenceCollector parses temporal tool results and Synthesizer renders temporal report."""
    collector = EvidenceCollector()

    # Step 1: Commit history step
    sr1 = StepResult(
        step_id="step_hist",
        tool_name="git_commit_history",
        status=ToolStatus.SUCCESS,
        output={
            "commits": [
                {
                    "full_hash": "a1b2c3d4e5f67890123456789012345678901234",
                    "short_hash": "a1b2c3d",
                    "author_name": "Charlie",
                    "author_date": "2026-03-01T12:00:00+00:00",
                    "subject": "refactor: simplify pipeline",
                    "files_changed": [{"path": "src/pipe.py", "status": "M"}],
                }
            ],
            "total_commits": 1,
            "filtered_path": "src/pipe.py",
        },
    )
    added1 = collector.extract_from_step_result(sr1)
    assert added1 == 1

    # Step 2: Logical coupling step
    sr2 = StepResult(
        step_id="step_coup",
        tool_name="git_logical_coupling",
        status=ToolStatus.SUCCESS,
        output={
            "focal_file": "src/pipe.py",
            "couplings": [
                {
                    "source_file": "src/pipe.py",
                    "target_file": "tests/test_pipe.py",
                    "support_count": 7,
                    "jaccard_similarity": 0.85,
                    "confidence": 0.90,
                    "last_co_change_date": "2026-03-01T12:00:00+00:00",
                }
            ],
            "total_couplings": 1,
        },
    )
    added2 = collector.extract_from_step_result(sr2)
    assert added2 == 1

    assert len(collector) == 2
    summary = collector.summary()
    assert summary.get("temporal", 0) == 2

    # Synthesize findings
    synthesizer = InvestigationSynthesizer()
    inv_result = InvestigationResult(
        query="How does src/pipe.py evolve?",
        intent=InvestigationIntent.EVOLUTION,
        plan=None,
        step_results=[sr1, sr2],
        evidence=collector.to_list(),
        overall_status=InvestigationStatus.SUCCESS,
    )

    report = synthesizer.synthesize(inv_result)
    assert "Direct Answer" in report
    assert "Key Findings" in report
    assert "Commit Revision" in report
    assert "Logical Coupling" in report
    assert "a1b2c3d" in report
    assert "test_pipe.py" in report
    assert "Limitations & Uncertainty" in report
    assert "Git Temporal Intelligence Boundary" in report
