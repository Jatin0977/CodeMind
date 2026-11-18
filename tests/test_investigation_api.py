"""
Tests for CodeMind Phase 6 Milestone 6: FastAPI Investigation Endpoint (/api/investigate).
"""

import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from codemind.web.app import create_app, GLOBAL_STATE


class TestInvestigationAPI(unittest.TestCase):
    """Test suite for POST /api/investigate endpoint."""

    @classmethod
    def setUpClass(cls):
        app = create_app()
        cls.client = TestClient(app)

        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = Path(cls.temp_dir.name)

        calc_py = cls.repo_path / "calc.py"
        calc_py.write_text(
            '"""Math utilities."""\n\n'
            "class CalcService:\n"
            '    """Calculator service."""\n'
            "    def add(self, a: int, b: int) -> int:\n"
            "        return a + b\n\n"
            "def run_calc():\n"
            "    c = CalcService()\n"
            "    return c.add(1, 2)\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_investigate_without_scan_returns_400(self):
        # Temporarily clear scanned repo
        prev_repo = GLOBAL_STATE.repo
        GLOBAL_STATE.repo = None
        try:
            resp = self.client.post(
                "/api/investigate",
                json={"query": "Where is Calculator?"},
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("No repository scanned", resp.json()["detail"])
        finally:
            GLOBAL_STATE.repo = prev_repo

    def test_investigate_empty_query_returns_400(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post("/api/investigate", json={"query": "   "})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Query cannot be empty", resp.json()["detail"])

    def test_investigate_understand_intent_success(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post(
            "/api/investigate",
            json={"query": "Explain the CalcService class and its methods", "mock": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["query"], "Explain the CalcService class and its methods")
        self.assertEqual(data["intent"].lower(), "understand")
        self.assertGreater(data["confidence"], 0.5)
        self.assertIn("CalcService", data["extracted_entities"])
        self.assertIn(data["overall_status"], ["SUCCESS", "PARTIAL_SUCCESS"])
        self.assertIn("plan", data)
        self.assertIn("steps", data["plan"])
        self.assertGreater(len(data["plan"]["steps"]), 0)
        self.assertIn("step_results", data)
        self.assertIn("final_answer", data)
        self.assertTrue(len(data["final_answer"]) > 0)
        self.assertIn("evidence", data)
        self.assertIn("metadata", data)

    def test_investigate_structure_intent(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post(
            "/api/investigate",
            json={"query": "Who calls add?", "mock": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["intent"].lower(), "structure")
        self.assertIn(data["overall_status"], ["SUCCESS", "PARTIAL_SUCCESS"])
        self.assertGreater(len(data["step_results"]), 0)

    def test_investigate_deferred_intent_evolution(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post(
            "/api/investigate",
            json={"query": "Show the commit history of calc.py", "mock": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["intent"].lower(), "evolution")
        # Check deferred tool indication in step_results
        has_deferred = any(
            "DEFERRED" in sr.get("status", "") for sr in data.get("step_results", [])
        )
        self.assertTrue(has_deferred)
        self.assertIn("calc.py", data["final_answer"])

    def test_investigate_statelessness_consecutive_calls(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp1 = self.client.post(
            "/api/investigate",
            json={"query": "Explain the Calculator class and its methods", "mock": True},
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()

        resp2 = self.client.post(
            "/api/investigate",
            json={"query": "Who calls add?", "mock": True},
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()

        # Check queries and intents did not bleed
        self.assertEqual(data1["intent"].lower(), "understand")
        self.assertEqual(data2["intent"].lower(), "structure")
        self.assertNotEqual(data1["query"], data2["query"])
