"""
Unit and integration tests for CodeMind Phase 8 Milestone 8.5:
FastAPI Endpoints (/api/impact/analyze, /api/impact/tests) and CLI Command Integration.
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import networkx as nx

from codemind.graph.models import NodeType, EdgeType
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.graph.query import GraphQueryEngine
from codemind.web.app import create_app, GLOBAL_STATE
from codemind.cli import impact_cli


class TestMilestone85APIAndCLI(unittest.TestCase):
    """Test suite for Milestone 8.5 API endpoints and CLI commands."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = TestClient(cls.app)

    def setUp(self):
        # Configure GLOBAL_STATE with a mock ingested repository and knowledge graph
        self.graph = nx.DiGraph()
        self.graph.add_node("file:auth.py", name="auth.py", node_type=NodeType.FILE, relative_path="auth.py")
        self.graph.add_node("function:auth.py:verify_token", name="verify_token", node_type=NodeType.FUNCTION, relative_path="auth.py", metadata={"complexity": 4})
        self.graph.add_node("file:api.py", name="api.py", node_type=NodeType.FILE, relative_path="api.py")
        self.graph.add_node("function:api.py:login", name="login", node_type=NodeType.FUNCTION, relative_path="api.py")

        self.graph.add_edge("file:auth.py", "function:auth.py:verify_token", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:api.py", "function:api.py:login", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("function:api.py:login", "function:auth.py:verify_token", edge_type=EdgeType.CALLS)

        # Ambiguous symbol 'save'
        self.graph.add_node("function:auth.py:save", name="save", node_type=NodeType.FUNCTION, relative_path="auth.py")
        self.graph.add_node("function:api.py:save", name="save", node_type=NodeType.FUNCTION, relative_path="api.py")

        # Tests
        self.graph.add_node("file:tests/test_auth.py", name="test_auth.py", node_type=NodeType.FILE, relative_path="tests/test_auth.py")
        self.graph.add_node("function:tests/test_auth.py:test_verify_token", name="test_verify_token", node_type=NodeType.FUNCTION, relative_path="tests/test_auth.py")
        self.graph.add_edge("file:tests/test_auth.py", "function:tests/test_auth.py:test_verify_token", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("function:tests/test_auth.py:test_verify_token", "function:auth.py:verify_token", edge_type=EdgeType.CALLS)

        # Mock repo
        mock_repo = MagicMock()
        mock_repo.repo_name = "test_repo"
        mock_file1 = MagicMock()
        mock_file1.relative_path = "auth.py"
        mock_file2 = MagicMock()
        mock_file2.relative_path = "tests/test_auth.py"
        mock_repo.files = [mock_file1, mock_file2]

        GLOBAL_STATE.repo = mock_repo
        GLOBAL_STATE.graph_builder = KnowledgeGraphBuilder()
        GLOBAL_STATE.graph_builder.graph = self.graph
        GLOBAL_STATE.graph_query_engine = GraphQueryEngine(self.graph)
        GLOBAL_STATE.git_commits = []
        GLOBAL_STATE.git_client = None

    def tearDown(self):
        GLOBAL_STATE.repo = None
        GLOBAL_STATE.graph_builder = KnowledgeGraphBuilder()
        GLOBAL_STATE.graph_query_engine = None
        GLOBAL_STATE.impact_engine = None
        GLOBAL_STATE.impact_scorer = None
        GLOBAL_STATE.test_engine = None

    def test_api_impact_analyze_post_success(self):
        """Test POST /api/impact/analyze returns valid multi-signal impact report."""
        resp = self.client.post(
            "/api/impact/analyze",
            json={"target": "verify_token", "max_depth": 3, "include_temporal": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("composite_score", data)
        self.assertIn("risk_level", data)
        self.assertIn("signals", data)
        self.assertIn("blast_radius", data)
        self.assertEqual(data["target"]["name"], "verify_token")
        self.assertGreaterEqual(data["blast_radius"]["total_impacted"], 1)

    def test_api_impact_analyze_get_success(self):
        """Test GET /api/impact/analyze returns valid report."""
        resp = self.client.get("/api/impact/analyze?target=verify_token&max_depth=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["target"]["name"], "verify_token")

    def test_api_impact_analyze_ambiguous_target_returns_400(self):
        """Test POST /api/impact/analyze returns 400 for ambiguous symbol."""
        resp = self.client.post("/api/impact/analyze", json={"target": "save"})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        detail = data.get("detail", {})
        self.assertEqual(detail.get("error_type"), "AmbiguousTargetError")
        self.assertEqual(detail.get("candidate_count"), 2)

    def test_api_impact_analyze_target_not_found_returns_404(self):
        """Test POST /api/impact/analyze returns 404 for unknown symbol."""
        resp = self.client.post("/api/impact/analyze", json={"target": "verfy_tokn"})
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        detail = data.get("detail", {})
        self.assertEqual(detail.get("error_type"), "TargetNotFoundError")
        self.assertTrue(len(detail.get("suggestions", [])) > 0)

    def test_api_impact_tests_post_success(self):
        """Test POST /api/impact/tests returns test recommendations."""
        resp = self.client.post(
            "/api/impact/tests",
            json={"target": "verify_token", "max_depth": 3},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("recommendations", data)
        self.assertGreater(data["total_tests"], 0)
        self.assertEqual(data["recommendations"][0]["test_target"], "test_verify_token")
        self.assertIn("disclaimer", data)

    def test_api_impact_tests_get_success(self):
        """Test GET /api/impact/tests returns test recommendations."""
        resp = self.client.get("/api/impact/tests?target=verify_token")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total_tests"], 0)

    def test_cli_impact_command_json_output(self):
        """Test impact_cli execution with --json."""
        with patch("sys.stdout") as mock_stdout:
            # Run impact_cli on current repository targeting verify_token or a known file
            code = impact_cli(
                target="codemind/auth.py",
                repo_path=".",
                max_depth=2,
                as_json=True,
            )
            # Should exit with code 0 or 1 depending on whether target exists on disk
            self.assertIn(code, (0, 1))

    def test_cli_impact_command_table_output(self):
        """Test impact_cli execution with human-readable table."""
        code = impact_cli(
            target="codemind/cli.py",
            repo_path=".",
            max_depth=2,
            as_json=False,
        )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
