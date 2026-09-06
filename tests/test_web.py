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


class TestWebAPI(unittest.TestCase):
    """Test suite for CodeMind web endpoints (Evaluation 1)."""

    @classmethod
    def setUpClass(cls):
        # Configure test client
        app = create_app()
        cls.client = TestClient(app)

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

    # ============================================================================
    # Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
    # (Grounded RAG API endpoint tests)
    # ============================================================================
    # def test_ask_mock_grounded_rag(self):
    #     ...
    # def test_ask_out_of_scope_insufficient_context(self):
    #     ...
    # ============================================================================


if __name__ == "__main__":
    unittest.main()
