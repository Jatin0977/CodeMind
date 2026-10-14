"""
Unit tests for CodeMind FastAPI Web API and Explorer endpoints.
Prepared for College Evaluation 1 (Technical Phases 1 and 2).
"""

import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from codemind.web.app import create_app, GLOBAL_STATE
from codemind.embeddings.mock_provider import MockEmbeddingProvider
from codemind.retrieval.retriever import SemanticRetriever


class TestWebAPI(unittest.TestCase):
    """Test suite for CodeMind web endpoints (Evaluation 1 & 2)."""

    @classmethod
    def setUpClass(cls):
        # Configure test client
        app = create_app()
        cls.client = TestClient(app)

        # Use fast mock embedding provider for tests
        GLOBAL_STATE.retriever = SemanticRetriever(
            embedding_provider=MockEmbeddingProvider(dimension=64)
        )

        # Set up a temporary test repository
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = Path(cls.temp_dir.name)

        # Create sample files
        calculator_py = cls.repo_path / "calculator.py"
        calculator_py.write_text(
            '"""Calculator module for basic arithmetic."""\n\n'
            "import math\n\n"
            "class Calculator:\n"
            '    """A simple calculator class."""\n\n'
            "    def add(self, a: float, b: float) -> float:\n"
            '        """Add two numbers."""\n'
            "        return a + b\n\n"
            "    def multiply(self, a: float, b: float) -> float:\n"
            '        """Multiply two numbers."""\n'
            "        return a * b\n\n"
            "def sqrt_val(x: float) -> float:\n"
            '    """Return square root of x."""\n'
            "    return math.sqrt(x)\n",
            encoding="utf-8",
        )

        readme_md = cls.repo_path / "README.md"
        readme_md.write_text(
            "# Math Project\n\nThis project provides arithmetic calculation utilities.\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_health_endpoint(self):
        """Test GET /api/health returns system status and evaluation phase."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["version"], "0.1.0")
        self.assertIn("evaluation_phase", data)
        self.assertIn("is_scanned", data)
        self.assertIn("has_gemini_key", data)
        self.assertIn("embedding_model", data)

    def test_root_serves_html(self):
        """Test GET / returns HTML dashboard."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("CodeMind", response.text)

    def test_scan_repository_success(self):
        """Test POST /api/scan with valid repo path."""
        response = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("repository", data)
        self.assertEqual(data["total_files"], 2)
        self.assertIn("ast_metrics", data)
        self.assertEqual(data["ast_metrics"]["classes"], 1)
        self.assertEqual(data["ast_metrics"]["functions"], 1)
        self.assertEqual(data["ast_metrics"]["methods"], 2)
        self.assertEqual(data["ast_metrics"]["imports"], 1)
        self.assertIn("file_analysis", data)
        self.assertEqual(len(data["file_analysis"]), 2)
        self.assertEqual(len(data["files"]), 2)
        self.assertGreater(data["total_chunks"], 0)
        self.assertGreater(data["indexed_chunks"], 0)
        self.assertIn("chunk_breakdown", data)

    def test_scan_invalid_path_returns_404(self):
        """Test POST /api/scan with invalid directory returns 404."""
        response = self.client.post("/api/scan", json={"repo_path": "/invalid/nonexistent/path/999"})
        self.assertEqual(response.status_code, 404)

    def test_get_file_content(self):
        """Test GET /api/file returns content and symbols."""
        # Ensure scanned
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        response = self.client.get("/api/file?path=calculator.py")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["relative_path"], "calculator.py")
        self.assertEqual(data["language"], "python")
        self.assertIn("Calculator", data["content"])
        self.assertIsNotNone(data["symbols"])
        self.assertEqual(len(data["symbols"]["classes"]), 1)

    def test_get_file_not_found(self):
        """Test GET /api/file with non-existent file returns 404."""
        response = self.client.get("/api/file?path=nonexistent.py")
        self.assertEqual(response.status_code, 404)

    def test_get_symbols(self):
        """Test GET /api/symbols returns parsed AST symbol data."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        response = self.client.get("/api/symbols?path=calculator.py")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["relative_path"], "calculator.py")
        self.assertEqual(len(data["classes"]), 1)
        self.assertEqual(data["classes"][0]["name"], "Calculator")
        self.assertEqual(len(data["classes"][0]["methods"]), 2)
        self.assertEqual(len(data["functions"]), 1)
        self.assertEqual(data["functions"][0]["name"], "sqrt_val")

    def test_ask_mock_grounded_rag(self):
        """Test POST /api/ask with mock mode returns grounded response."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        response = self.client.post(
            "/api/ask",
            json={
                "question": "How does the calculator add numbers?",
                "top_k": 3,
                "mock": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answer", data)
        self.assertTrue(data["is_sufficient"])
        self.assertGreater(len(data["citations"]), 0)
        self.assertGreater(len(data["sources"]), 0)
        # Check citations format
        for cit in data["citations"]:
            self.assertIn(":", cit)
            self.assertIn("-", cit)

    def test_ask_out_of_scope_insufficient_context(self):
        """Test POST /api/ask with irrelevant question returns insufficient context."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        response = self.client.post(
            "/api/ask",
            json={
                "question": "Quantum gravity quantum black hole entanglement dynamics?",
                "top_k": 3,
                "mock": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["is_sufficient"])
        self.assertIn("insufficient context", data["answer"].lower())
        self.assertEqual(len(data["citations"]), 0)

    def test_ask_without_scan_returns_400(self):
        """Test POST /api/ask before scanning a repository returns 400."""
        prev_repo = GLOBAL_STATE.repo
        GLOBAL_STATE.repo = None
        try:
            response = self.client.post(
                "/api/ask",
                json={"question": "What does this repo do?", "mock": True},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("No repository scanned yet", response.json()["detail"])
        finally:
            GLOBAL_STATE.repo = prev_repo

    def test_get_graph_endpoint(self):
        """Test GET /api/graph returns nodes, edges and graph summary."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        response = self.client.get("/api/graph")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("summary", data)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertGreater(data["total_nodes"], 0)
        self.assertGreater(data["total_edges"], 0)

        # Check node types present
        node_types = {n["node_type"] for n in data["nodes"]}
        self.assertIn("file", node_types)
        self.assertIn("class", node_types)
        self.assertIn("method", node_types)
        self.assertIn("function", node_types)

    def test_get_graph_filter_by_type(self):
        """Test GET /api/graph?node_type=class returns only class nodes."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        response = self.client.get("/api/graph?node_type=class")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        for node in data["nodes"]:
            self.assertEqual(node["node_type"], "class")

    def test_get_graph_impact_endpoint(self):
        """Test GET /api/graph/impact traces structural reachability."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        # Trace impact of Calculator class
        target_id = "class:calculator.py:Calculator"
        response = self.client.get(f"/api/graph/impact?node_id={target_id}&max_depth=2")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["found"])
        self.assertEqual(data["analysis_type"], "Structural Reachability")
        self.assertIn("disclaimer", data)
        self.assertIn("impacted_entities", data)

    def test_get_graph_node_details(self):
        """Test GET /api/graph/node returns callers, callees, dependencies."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        target_id = "class:calculator.py:Calculator"
        response = self.client.get(f"/api/graph/node?node_id={target_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("node", data)
        self.assertEqual(data["node"]["id"], target_id)
        self.assertIn("callers", data)
        self.assertIn("callees", data)
        self.assertIn("dependencies", data)
        self.assertIn("dependents", data)
        self.assertIn("dependency_depth", data)

    def test_get_graph_cycles(self):
        """Test GET /api/graph/cycles returns cycle detection report."""
        self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})

        response = self.client.get("/api/graph/cycles")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("has_cycles", data)
        self.assertIn("cycle_count", data)
        self.assertIn("cycles", data)


if __name__ == "__main__":
    unittest.main()

