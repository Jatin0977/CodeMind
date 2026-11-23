"""
Unit and integration tests for CodeMind Phase 10.5 Architecture & Risk Intelligence Dashboard.
Verifies the web endpoints, static UI assets, and client-facing API responses.
"""

import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from codemind.web.app import create_app, GLOBAL_STATE
from codemind.embeddings.mock_provider import MockEmbeddingProvider
from codemind.retrieval.retriever import SemanticRetriever


class TestWebArchitectureDashboard(unittest.TestCase):
    """Test suite for Architecture Intelligence web dashboard endpoints and assets."""

    @classmethod
    def setUpClass(cls):
        app = create_app()
        cls.client = TestClient(app)

        # Use fast mock retriever for scanning
        GLOBAL_STATE.retriever = SemanticRetriever(
            embedding_provider=MockEmbeddingProvider(dimension=64)
        )

        # Create temporary structured codebase
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = Path(cls.temp_dir.name)

        # Create package layers:
        # Layer 1: web (app.py)
        # Layer 2: service (calc_service.py)
        # Layer 3: data (storage.py)
        pkg_web = cls.repo_path / "web"
        pkg_web.mkdir(parents=True, exist_ok=True)
        (pkg_web / "__init__.py").write_text("", encoding="utf-8")
        (pkg_web / "app.py").write_text(
            '"""Web presentation layer."""\n'
            "from service.calc_service import CalcService\n\n"
            "class WebApp:\n"
            "    def __init__(self):\n"
            "        self.svc = CalcService()\n"
            "    def run(self):\n"
            "        return self.svc.compute(10)\n",
            encoding="utf-8",
        )

        pkg_svc = cls.repo_path / "service"
        pkg_svc.mkdir(parents=True, exist_ok=True)
        (pkg_svc / "__init__.py").write_text("", encoding="utf-8")
        (pkg_svc / "calc_service.py").write_text(
            '"""Domain service layer."""\n'
            "from data.storage import DataStore\n\n"
            "class CalcService:\n"
            "    def __init__(self):\n"
            "        self.store = DataStore()\n"
            "    def compute(self, n: int) -> int:\n"
            "        res = n * 2\n"
            "        self.store.save(res)\n"
            "        return res\n",
            encoding="utf-8",
        )

        pkg_data = cls.repo_path / "data"
        pkg_data.mkdir(parents=True, exist_ok=True)
        (pkg_data / "__init__.py").write_text("", encoding="utf-8")
        (pkg_data / "storage.py").write_text(
            '"""Data access layer."""\n\n'
            "class DataStore:\n"
            "    def __init__(self):\n"
            "        self.records = []\n"
            "    def save(self, item):\n"
            "        self.records.append(item)\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_benchmark_summary_endpoint(self):
        """Test GET /api/benchmarks/summary returns 200 and complete evaluation metrics."""
        response = self.client.get("/api/benchmarks/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("dataset", data)
        self.assertEqual(data["dataset"]["total_queries"], 50)
        self.assertIn("retrieval_metrics", data)
        self.assertIn("mean_precision_at_3", data["retrieval_metrics"])
        self.assertIn("mean_recall_at_3", data["retrieval_metrics"])
        self.assertIn("mean_reciprocal_rank_mrr", data["retrieval_metrics"])

        # Check precision@3 honest status
        self.assertEqual(data["retrieval_metrics"]["mean_precision_at_3"], 0.5133)
        self.assertIn("NOT MET", data["retrieval_metrics"]["precision_at_3_status"])

        # Check recall@3 honest status
        self.assertEqual(data["retrieval_metrics"]["mean_recall_at_3"], 0.7117)
        self.assertEqual(data["retrieval_metrics"]["recall_at_3_status"], "NOT MET")

        # Check MRR met status
        self.assertEqual(data["retrieval_metrics"]["mean_reciprocal_rank_mrr"], 0.8333)
        self.assertIn("MET", data["retrieval_metrics"]["mrr_status"])

        # Check indexing scale profiles and baseline comparison
        self.assertIn("scale_profiles", data)
        self.assertIn("repo_small", data["scale_profiles"])
        self.assertIn("repo_medium", data["scale_profiles"])
        self.assertIn("repo_large", data["scale_profiles"])
        self.assertIn("baseline_comparison", data)
        self.assertIn("performance_targets", data)

    def test_static_html_has_architecture_dashboard(self):
        """Test that static index.html includes the architecture tab and containers."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text

        self.assertIn('id="tabArchitectureBtn"', html)
        self.assertIn('id="tabArchitecture"', html)
        self.assertIn('id="archAciVal"', html)
        self.assertIn('id="archCyclesVal"', html)
        self.assertIn('id="archRiskScoreVal"', html)
        self.assertIn('id="archCoverageVal"', html)
        self.assertIn('id="archLayersContainer"', html)
        self.assertIn('id="archViolationsTableBody"', html)
        self.assertIn('id="archCyclesContainer"', html)
        self.assertIn('id="archHotspotsTableBody"', html)
        self.assertIn('id="archBenchmarksTableBody"', html)
        self.assertIn('value="God Class"', html)
        self.assertIn('value="Brain Module"', html)
        self.assertIn('value="Volatile Fragile"', html)
        self.assertIn('value="Shotgun Surgery"', html)
        self.assertIn('value="Stable Core"', html)
        self.assertIn('value="Normal Component"', html)

    def test_static_css_has_architecture_styles(self):
        """Test that static style.css contains architecture visual classes."""
        response = self.client.get("/static/style.css")
        self.assertEqual(response.status_code, 200)
        css = response.text

        self.assertIn(".arch-layer-card", css)
        self.assertIn(".archetype-pill", css)
        self.assertIn(".violation-pill-leak", css)
        self.assertIn(".status-badge-met", css)
        self.assertIn(".status-badge-not-met", css)

    def test_static_js_has_architecture_logic(self):
        """Test that static app.js defines dashboard logic functions."""
        response = self.client.get("/static/app.js")
        self.assertEqual(response.status_code, 200)
        js = response.text

        self.assertIn("loadArchitectureDashboard", js)
        self.assertIn("renderArchTopCards", js)
        self.assertIn("renderArchLayers", js)
        self.assertIn("renderArchViolations", js)
        self.assertIn("renderArchCycles", js)
        self.assertIn("renderArchHotspots", js)
        self.assertIn("renderArchBenchmarks", js)
        self.assertIn("triggerArchInvestigation", js)

    def test_architecture_endpoints_flow(self):
        """Test complete scan and architecture intelligence endpoints."""
        scan_res = self.client.post("/api/scan", json={"repo_path": str(self.repo_path)})
        self.assertEqual(scan_res.status_code, 200)

        # 1. Overview
        overview_res = self.client.get("/api/architecture/overview")
        self.assertEqual(overview_res.status_code, 200)
        overview_data = overview_res.json()
        self.assertIn("modules", overview_data)
        self.assertIn("layers", overview_data)
        self.assertIn("quotient_graph", overview_data)

        # 2. Conformance
        conf_res = self.client.get("/api/architecture/conformance")
        self.assertEqual(conf_res.status_code, 200)
        conf_data = conf_res.json()
        self.assertIn("conformance_index", conf_data)
        self.assertIn("violations", conf_data)
        self.assertGreaterEqual(conf_data["conformance_index"], 0.0)

        # 3. Strict conformance
        strict_res = self.client.get("/api/architecture/conformance?strict_layering=true")
        self.assertEqual(strict_res.status_code, 200)

        # 4. Cycles
        cycles_res = self.client.get("/api/architecture/cycles")
        self.assertEqual(cycles_res.status_code, 200)
        cycles_data = cycles_res.json()
        self.assertIn("has_cycles", cycles_data)
        self.assertIn("cycles", cycles_data)
        self.assertIn("cycle_count", cycles_data)

        # 5. Hotspots
        hotspots_res = self.client.get("/api/architecture/hotspots")
        self.assertEqual(hotspots_res.status_code, 200)
        hotspots_data = hotspots_res.json()
        self.assertIn("hotspots", hotspots_data)
        self.assertIn("repository_risk_score", hotspots_data)
        self.assertIn("analysis_state", hotspots_data)


if __name__ == "__main__":
    unittest.main()
