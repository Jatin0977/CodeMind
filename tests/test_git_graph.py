"""
Unit tests for Milestone 4: Temporal Knowledge Graph Materialization & Queries.
Verifies commit node creation, CHANGED_IN and CO_CHANGED_WITH edges,
metric orientation, window decoupling, and AST isolation.
"""

from datetime import datetime, timezone
import pytest
import networkx as nx
from codemind.graph.models import NodeType, EdgeType, Node, Edge
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.graph.query import GraphQueryEngine
from codemind.git.models import (
    CommitRecord,
    FileChange,
    FileChangeStatus,
)
from codemind.git.coupling import LogicalCoupling


def _make_dummy_commit(
    full_hash: str,
    subject: str,
    date: datetime,
    file_changes: list[FileChange],
) -> CommitRecord:
    return CommitRecord(
        full_hash=full_hash,
        short_hash=full_hash[:7],
        author_name="Alice Dev",
        author_email="alice@example.com",
        author_date=date,
        subject=subject,
        parents=["parent123"],
        is_merge=False,
        files_changed=file_changes,
    )


def test_commit_node_materialization_and_pii_protection():
    """Verify commit node creation, properties, and that author email is excluded for PII protection."""
    builder = KnowledgeGraphBuilder()
    commit = _make_dummy_commit(
        "abc1234567890def1234567890def1234567890",
        "feat: initial temporal intelligence",
        datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        [
            FileChange(status="M", path="src/main.py", additions=10, deletions=2),
            FileChange(status="A", path="src/utils.py", additions=25, deletions=0),
        ],
    )

    builder.materialize_temporal_graph([commit], [])
    node_id = f"commit:{commit.full_hash}"

    assert node_id in builder.graph
    node_data = builder.graph.nodes[node_id]

    assert node_data["node_type"] == NodeType.COMMIT
    assert node_data["name"] == commit.short_hash

    meta = node_data["metadata"]
    assert meta["full_hash"] == commit.full_hash
    assert meta["short_hash"] == commit.short_hash
    assert meta["author_name"] == "Alice Dev"
    assert "2026-03-01" in meta["author_date"]
    assert meta["subject"] == "feat: initial temporal intelligence"
    assert meta["is_merge"] is False

    # PII verification: author_email must NOT exist in node data or metadata
    assert "author_email" not in meta
    assert "author_email" not in node_data


def test_changed_in_edge_creation():
    """Verify File -> Commit directed CHANGED_IN edges with change metadata."""
    builder = KnowledgeGraphBuilder()
    commit = _make_dummy_commit(
        "commit1111111111111111111111111111111111",
        "refactor: rename config",
        datetime(2026, 3, 1, 11, 0, 0, tzinfo=timezone.utc),
        [
            FileChange(
                status="R",
                path="config/new.json",
                old_path="config/old.json",
                additions=5,
                deletions=1,
            )
        ],
    )

    builder.materialize_temporal_graph([commit], [])

    file_id = "file:config/new.json"
    commit_id = f"commit:{commit.full_hash}"

    assert builder.graph.has_edge(file_id, commit_id)
    edge_data = builder.graph.get_edge_data(file_id, commit_id)

    assert edge_data["edge_type"] == EdgeType.CHANGED_IN
    meta = edge_data["metadata"]
    assert meta["change_type"] == "R"
    assert meta["insertions"] == 5
    assert meta["deletions"] == 1
    assert meta["old_path"] == "config/old.json"
    assert meta["is_temporal"] is True


def test_reciprocal_co_changed_with_edges():
    """Verify reciprocal CO_CHANGED_WITH edges with identical canonical metadata."""
    builder = KnowledgeGraphBuilder()
    coupling = LogicalCoupling(
        canonical_file_a="src/auth.py",
        canonical_file_b="tests/test_auth.py",
        support_count=8,
        jaccard_similarity=0.8,
        confidence_a_to_b=0.8,
        confidence_b_to_a=1.0,
        last_co_change_date="2026-03-01T12:00:00+00:00",
    )

    builder.materialize_temporal_graph([], [coupling])

    node_a = "file:src/auth.py"
    node_b = "file:tests/test_auth.py"

    assert builder.graph.has_edge(node_a, node_b)
    assert builder.graph.has_edge(node_b, node_a)

    edge_ab = builder.graph.get_edge_data(node_a, node_b)
    edge_ba = builder.graph.get_edge_data(node_b, node_a)

    assert edge_ab["edge_type"] == EdgeType.CO_CHANGED_WITH
    assert edge_ba["edge_type"] == EdgeType.CO_CHANGED_WITH

    # Identical canonical metadata
    meta_ab = edge_ab["metadata"]
    meta_ba = edge_ba["metadata"]
    assert meta_ab == meta_ba
    assert meta_ab["canonical_file_a"] == "src/auth.py"
    assert meta_ab["canonical_file_b"] == "tests/test_auth.py"
    assert meta_ab["support_count"] == 8
    assert meta_ab["jaccard_similarity"] == 0.8
    assert meta_ab["confidence_a_to_b"] == 0.8
    assert meta_ab["confidence_b_to_a"] == 1.0
    assert meta_ab["is_temporal"] is True


def test_window_decoupling_and_duplicate_prevention():
    """Verify that max_materialize_commits caps graph nodes even if miner provides more."""
    builder = KnowledgeGraphBuilder()
    commits = [
        _make_dummy_commit(
            f"hash{i:036d}",
            f"commit {i}",
            datetime(2026, 3, 1, i % 24, 0, 0, tzinfo=timezone.utc),
            [FileChange(status="M", path="src/app.py", additions=1, deletions=1)],
        )
        for i in range(150)
    ]

    # Materialize with bound of 100
    builder.materialize_temporal_graph(commits, [], max_materialize_commits=100)

    summary = builder.get_summary()
    assert summary.node_type_counts.get(NodeType.COMMIT, 0) == 100

    # Repeat materialization to test idempotence / duplicate prevention
    builder.materialize_temporal_graph(commits, [], max_materialize_commits=100)
    summary2 = builder.get_summary()
    assert summary2.node_type_counts.get(NodeType.COMMIT, 0) == 100


def test_graph_query_engine_temporal_queries():
    """Verify get_file_commits, get_commit_files, and get_logically_coupled_files with orientation."""
    builder = KnowledgeGraphBuilder()

    commit1 = _make_dummy_commit(
        "1111111111111111111111111111111111111111",
        "first commit",
        datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc),
        [
            FileChange(status="A", path="src/service.py", additions=50, deletions=0),
            FileChange(status="A", path="src/db.py", additions=30, deletions=0),
        ],
    )
    commit2 = _make_dummy_commit(
        "2222222222222222222222222222222222222222",
        "second commit",
        datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
        [
            FileChange(status="M", path="src/service.py", additions=5, deletions=2),
            FileChange(status="A", path="tests/test_service.py", additions=20, deletions=0),
        ],
    )

    coupling = LogicalCoupling(
        canonical_file_a="src/db.py",
        canonical_file_b="src/service.py",
        support_count=5,
        jaccard_similarity=0.75,
        confidence_a_to_b=0.85,
        confidence_b_to_a=0.60,
        last_co_change_date="2026-03-01T09:00:00+00:00",
    )

    builder.materialize_temporal_graph([commit1, commit2], [coupling])
    engine = GraphQueryEngine(builder.graph, builder.nodes_by_id)

    # 1. get_file_commits
    commits_svc = engine.get_file_commits("src/service.py")
    assert len(commits_svc) == 2
    # Verify chronological descending order: commit2 then commit1
    assert commits_svc[0]["short_hash"] == commit2.short_hash
    assert commits_svc[1]["short_hash"] == commit1.short_hash
    assert commits_svc[0]["insertions"] == 5
    assert commits_svc[0]["deletions"] == 2

    # 2. get_commit_files
    files_c1 = engine.get_commit_files(commit1.full_hash)
    assert len(files_c1) == 2
    paths = [f["path"] for f in files_c1]
    assert "src/db.py" in paths
    assert "src/service.py" in paths

    # Query with short hash
    files_c2 = engine.get_commit_files(commit2.short_hash)
    assert len(files_c2) == 2

    # 3. get_logically_coupled_files with perspective orientation
    # From perspective of file_a ("src/db.py"): confidence should be confidence_a_to_b (0.85)
    coupled_from_a = engine.get_logically_coupled_files("src/db.py")
    assert len(coupled_from_a) == 1
    assert coupled_from_a[0]["target_file"] == "src/service.py"
    assert pytest.approx(coupled_from_a[0]["confidence"], 0.01) == 0.85
    assert pytest.approx(coupled_from_a[0]["jaccard_similarity"], 0.01) == 0.75

    # From perspective of file_b ("src/service.py"): confidence should be confidence_b_to_a (0.60)
    coupled_from_b = engine.get_logically_coupled_files("src/service.py")
    assert len(coupled_from_b) == 1
    assert coupled_from_b[0]["target_file"] == "src/db.py"
    assert pytest.approx(coupled_from_b[0]["confidence"], 0.01) == 0.60
    assert pytest.approx(coupled_from_b[0]["jaccard_similarity"], 0.01) == 0.75


def test_ast_graph_isolation():
    """Verify that temporal nodes and edges do not alter AST edges or cycle checks."""
    builder = KnowledgeGraphBuilder()

    # Create dummy AST file node and function nodes
    file_node = Node(id="file:src/math.py", name="math.py", node_type=NodeType.FILE, relative_path="src/math.py")
    fn1 = Node(id="fn:src/math.py:add", name="add", node_type=NodeType.FUNCTION, relative_path="src/math.py")
    fn2 = Node(id="fn:src/math.py:calc", name="calc", node_type=NodeType.FUNCTION, relative_path="src/math.py")

    builder._add_node(file_node)
    builder._add_node(fn1)
    builder._add_node(fn2)
    builder._add_edge(file_node.id, fn1.id, EdgeType.CONTAINS)
    builder._add_edge(file_node.id, fn2.id, EdgeType.CONTAINS)
    builder._add_edge(fn2.id, fn1.id, EdgeType.CALLS)

    # Add temporal intelligence
    commit = _make_dummy_commit(
        "9999999999999999999999999999999999999999",
        "update math",
        datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        [FileChange(status="M", path="src/math.py", additions=1, deletions=1)],
    )
    builder.materialize_temporal_graph([commit], [])

    summary = builder.get_summary()
    assert summary.node_type_counts[NodeType.FILE] == 1
    assert summary.node_type_counts[NodeType.FUNCTION] == 2
    assert summary.node_type_counts[NodeType.COMMIT] == 1

    assert summary.edge_type_counts[EdgeType.CONTAINS] == 2
    assert summary.edge_type_counts[EdgeType.CALLS] == 1
    assert summary.edge_type_counts[EdgeType.CHANGED_IN] == 1

    # Cycle check should remain false and ignore CHANGED_IN edges
    assert summary.has_cycles is False
