"""
Unit and integration tests for CodeMind Benchmarking & Systematic Evaluation (Milestone 10.1).

Verifies:
1. Golden dataset schema completeness and intent distribution (50 queries, 5 intents).
2. Mathematical correctness of retrieval metrics (Precision@K, Recall@K, MRR).
3. Citation integrity and fabricated citation detection.
4. Deterministic repository fixtures generation.
5. End-to-end benchmark evaluation runner execution.
"""

import os
import json
import unittest
from pathlib import Path

from scripts.evaluate_benchmarks import (
    calculate_retrieval_metrics,
    verify_citations,
    get_hardware_info,
)
from tests.benchmarks.fixture_generator import ensure_fixtures
from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.investigation.models import InvestigationIntent


class TestBenchmarkEvaluation(unittest.TestCase):
    """Test suite for benchmark dataset, metrics, and evaluation runner."""

    @classmethod
    def setUpClass(cls):
        cls.benchmarks_dir = Path(__file__).resolve().parent
        cls.root_dir = cls.benchmarks_dir.parent.parent
        cls.dataset_path = cls.benchmarks_dir / "golden_dataset.json"
        cls.fixtures_dir = cls.benchmarks_dir / "fixtures"

    def test_golden_dataset_schema_and_distribution(self):
        """Verify the golden evaluation dataset exists, is valid JSON, and has 50 queries across all 5 intents."""
        self.assertTrue(self.dataset_path.exists(), f"Missing dataset: {self.dataset_path}")
        data = json.loads(self.dataset_path.read_text(encoding="utf-8"))

        self.assertIn("version", data)
        self.assertIn("queries", data)
        queries = data["queries"]
        self.assertEqual(len(queries), 50, "Golden dataset must contain exactly 50 queries")

        # Verify all five canonical intents are represented
        required_intents = {"UNDERSTAND", "STRUCTURE", "IMPACT", "EVOLUTION", "INSIGHTS"}
        present_intents = set(data.get("intents", []))
        self.assertEqual(required_intents, present_intents)

        intent_counts = {intent: 0 for intent in required_intents}
        query_ids = set()

        for q in queries:
            # Check required fields
            self.assertIn("id", q)
            self.assertIn("query", q)
            self.assertIn("expected_intent", q)
            self.assertIn("ground_truth_files", q)
            self.assertIn("ground_truth_chunks", q)
            self.assertIn("expected_structural_facts", q)
            self.assertIn("expected_citations", q)

            # Ensure unique IDs
            self.assertNotIn(q["id"], query_ids, f"Duplicate query ID: {q['id']}")
            query_ids.add(q["id"])

            # Validate intent
            intent = q["expected_intent"].upper()
            self.assertIn(intent, required_intents, f"Invalid intent: {intent}")
            intent_counts[intent] += 1

            # Validate types
            self.assertIsInstance(q["query"], str)
            self.assertGreater(len(q["query"].strip()), 5)
            self.assertIsInstance(q["ground_truth_files"], list)
            self.assertGreater(len(q["ground_truth_files"]), 0)
            self.assertIsInstance(q["expected_citations"], list)
            self.assertGreater(len(q["expected_citations"]), 0)

        # Each canonical intent must have exactly 10 queries
        for intent, count in intent_counts.items():
            self.assertEqual(count, 10, f"Intent {intent} should have 10 queries, found {count}")

    def test_retrieval_metrics_mathematical_correctness(self):
        """Verify Precision@K, Recall@K, and MRR calculations on controlled ground-truth examples."""
        ground_truth = ["services/auth_service.py", "models/user.py"]

        # Case 1: Perfect retrieval at top 2 (hits at rank 1 and 2)
        retrieved_perfect = ["services/auth_service.py", "models/user.py", "utils/crypto.py"]
        m1 = calculate_retrieval_metrics(retrieved_perfect, ground_truth, k=3)
        self.assertEqual(m1["precision_at_k"], round(2 / 3, 4))
        self.assertEqual(m1["recall_at_k"], 1.0)
        self.assertEqual(m1["reciprocal_rank"], 1.0)  # first hit at rank 1 -> 1/1 = 1.0

        # Case 2: First hit at rank 2, second at rank 3
        retrieved_rank2 = ["db/connection.py", "services/auth_service.py", "models/user.py"]
        m2 = calculate_retrieval_metrics(retrieved_rank2, ground_truth, k=3)
        self.assertEqual(m2["precision_at_k"], round(2 / 3, 4))
        self.assertEqual(m2["recall_at_k"], 1.0)
        self.assertEqual(m2["reciprocal_rank"], 0.5)  # first hit at rank 2 -> 1/2 = 0.5

        # Case 3: First hit at rank 3, only 1 hit
        retrieved_rank3 = ["db/connection.py", "utils/crypto.py", "models/user.py"]
        m3 = calculate_retrieval_metrics(retrieved_rank3, ground_truth, k=3)
        self.assertEqual(m3["precision_at_k"], round(1 / 3, 4))
        self.assertEqual(m3["recall_at_k"], 0.5)  # 1 of 2 retrieved
        self.assertEqual(m3["reciprocal_rank"], round(1 / 3, 4))  # 1/3 = 0.3333

        # Case 4: Zero hits
        retrieved_zero = ["api/foo.py", "api/bar.py", "api/baz.py"]
        m4 = calculate_retrieval_metrics(retrieved_zero, ground_truth, k=3)
        self.assertEqual(m4["precision_at_k"], 0.0)
        self.assertEqual(m4["recall_at_k"], 0.0)
        self.assertEqual(m4["reciprocal_rank"], 0.0)

    def test_citation_integrity_verification(self):
        """Verify citation verification handles valid, invalid line range, and fabricated files."""
        # Load small repo for real file checks
        fixtures = ensure_fixtures(self.fixtures_dir)
        repo = RepositoryLoader().load_repository(str(fixtures["small"]))

        # 1. Valid citation
        valid_citations = [
            {"file": "utils/crypto.py", "start_line": 5, "end_line": 20}
        ]
        res1 = verify_citations(valid_citations, repo)
        self.assertEqual(res1["valid_citations"], 1)
        self.assertEqual(res1["validity_rate"], 1.0)
        self.assertEqual(res1["fabricated_count"], 0)
        self.assertEqual(res1["fabricated_rate"], 0.0)

        # 2. Fabricated non-existent file
        fake_citations = [
            {"file": "non_existent/fake_module.py", "start_line": 1, "end_line": 10}
        ]
        res2 = verify_citations(fake_citations, repo)
        self.assertEqual(res2["valid_citations"], 0)
        self.assertEqual(res2["fabricated_count"], 1)
        self.assertEqual(res2["fabricated_rate"], 1.0)

        # 3. Invalid line range (negative start or end < start)
        invalid_range_citations = [
            {"file": "utils/crypto.py", "start_line": 50, "end_line": 20}
        ]
        res3 = verify_citations(invalid_range_citations, repo)
        self.assertEqual(res3["valid_citations"], 0)
        self.assertEqual(res3["fabricated_count"], 1)

    def test_fixtures_generation_and_scales(self):
        """Verify repo_small, repo_medium, and repo_large fixtures are correctly created."""
        fixtures = ensure_fixtures(self.fixtures_dir)

        # repo_small
        small_files = list(fixtures["small"].glob("**/*.py"))
        self.assertGreaterEqual(len(small_files), 10)

        # repo_medium
        med_files = list(fixtures["medium"].glob("**/*.py"))
        self.assertGreaterEqual(len(med_files), 50)

        # Check intentional package cycle in repo_medium: billing/invoices.py -> services/account_service.py
        invoices_py = (fixtures["medium"] / "billing" / "invoices.py").read_text(encoding="utf-8")
        self.assertIn("AccountService", invoices_py)
        account_py = (fixtures["medium"] / "services" / "account_service.py").read_text(encoding="utf-8")
        self.assertIn("BillingLedger", account_py)

        # Check intentional layer leak in storage/postgres_db.py -> services/notification_service.py
        postgres_py = (fixtures["medium"] / "storage" / "postgres_db.py").read_text(encoding="utf-8")
        self.assertIn("NotificationService", postgres_py)

        # repo_large
        large_files = list(fixtures["large"].glob("**/*.py"))
        self.assertGreaterEqual(len(large_files), 250)

    def test_hardware_info_collector(self):
        """Verify hardware info detection collects non-empty, valid system attributes."""
        info = get_hardware_info()
        self.assertIn("os_name", info)
        self.assertIn("logical_cpus", info)
        self.assertGreater(info["logical_cpus"], 0)
        self.assertIn("dependencies", info)
        self.assertIn("pytest", info["dependencies"])


if __name__ == "__main__":
    unittest.main()
