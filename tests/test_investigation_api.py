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

        core_dir = cls.repo_path / "core"
        core_dir.mkdir(parents=True, exist_ok=True)
        (core_dir / "__init__.py").write_text("", encoding="utf-8")
        (core_dir / "service.py").write_text(
            "import os\nfrom util.logger import log\n\ndef process():\n    log('processing')\n",
            encoding="utf-8",
        )

        util_dir = cls.repo_path / "util"
        util_dir.mkdir(parents=True, exist_ok=True)
        (util_dir / "__init__.py").write_text("", encoding="utf-8")
        (util_dir / "logger.py").write_text(
            "def log(msg):\n    print(msg)\n",
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

    def test_investigate_architecture_overview(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post(
            "/api/investigate",
            json={"query": "Show the architecture overview and module hierarchy", "mock": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["intent"].lower(), "insights")
        self.assertIn(data["overall_status"], ["SUCCESS", "PARTIAL_SUCCESS"])
        self.assertTrue(any(sr["tool_name"] == "get_architecture_overview" for sr in data["step_results"]))
        self.assertTrue(any(e["category"] == "architecture" for e in data["evidence"]))
        self.assertTrue(len(data["final_answer"]) > 0)

    def test_investigate_architecture_conformance(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post(
            "/api/investigate",
            json={"query": "Check architecture conformance and rule violations", "mock": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["intent"].lower(), "insights")
        self.assertTrue(any(sr["tool_name"] == "check_architecture_conformance" for sr in data["step_results"]))
        self.assertTrue(any(e["category"] == "architecture" for e in data["evidence"]))

    def test_investigate_package_cycles(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post(
            "/api/investigate",
            json={"query": "Detect circular package dependencies", "mock": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["intent"].lower(), "insights")
        self.assertTrue(any(sr["tool_name"] == "detect_package_cycles" for sr in data["step_results"]))

    def test_investigate_maintenance_hotspots(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        resp = self.client.post(
            "/api/investigate",
            json={"query": "Detect maintenance hotspots and risk", "mock": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["intent"].lower(), "insights")
        self.assertTrue(any(sr["tool_name"] == "detect_maintenance_hotspots" for sr in data["step_results"]))

    def test_architecture_rest_endpoints(self):
        scan_resp = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_resp.status_code, 200)

        # 1. Overview
        resp_overview = self.client.get("/api/architecture/overview")
        self.assertEqual(resp_overview.status_code, 200)
        data_overview = resp_overview.json()
        self.assertIn("modules", data_overview)
        self.assertIn("quotient_graph", data_overview)

        # 2. Conformance
        resp_conf = self.client.get("/api/architecture/conformance")
        self.assertEqual(resp_conf.status_code, 200)
        data_conf = resp_conf.json()
        self.assertIn("conformance_index", data_conf)
        self.assertIn("violations", data_conf)

        # 3. Cycles
        resp_cycles = self.client.get("/api/architecture/cycles")
        self.assertEqual(resp_cycles.status_code, 200)
        data_cycles = resp_cycles.json()
        self.assertIn("has_cycles", data_cycles)
        self.assertIn("cycles", data_cycles)

        # 4. Hotspots
        resp_hotspots = self.client.get("/api/architecture/hotspots")
        self.assertEqual(resp_hotspots.status_code, 200)
        data_hotspots = resp_hotspots.json()
        self.assertIn("repository_risk_score", data_hotspots)
        self.assertIn("hotspots", data_hotspots)
