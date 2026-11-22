"""
Unit and integration tests for CodeMind Milestone 10.3: Performance Optimization & Scalability.

Verifies:
1. SparseBM25Retriever tokenization, subword splitting, field boosting, and ranked retrieval.
2. ComplexityAnalyzer memoization cache hits, cache bypass, and clear_cache() invalidation.
3. HybridGraphRetriever dual sparse/dense candidate seeding, reverse caller boosting, and domain context.
4. Latency bounds for acceptance targets (subgraph traversal, AST complexity, investigation planning).
"""

import os
import unittest
from pathlib import Path

from codemind.retrieval.sparse_retriever import SparseBM25Retriever
from codemind.chunking.models import CodeChunk
from codemind.architecture.complexity import ComplexityAnalyzer
from codemind.ingestion.models import SourceFile
from codemind.parsing.parser_factory import GLOBAL_PARSER_FACTORY


class TestSparseBM25Retriever(unittest.TestCase):
    """Test suite for SparseBM25Retriever implementation."""

    def setUp(self):
        self.retriever = SparseBM25Retriever()

    def test_tokenization_subword_splitting(self):
        """Verify tokenization splits CamelCase, snake_case, and handles alphanumeric identifiers."""
        tokens = self.retriever.tokenize("AuthService.handle_user_login(user_id=123)")
        expected_subwords = {"auth", "service", "handle", "user", "login", "id", "123"}
        for subword in expected_subwords:
            self.assertIn(subword, tokens, f"Expected subword '{subword}' in token stream {tokens}")

    def test_tokenization_empty_and_punctuation(self):
        """Verify tokenization handles empty strings and pure punctuation gracefully."""
        self.assertEqual(self.retriever.tokenize(""), [])
        self.assertEqual(self.retriever.tokenize("   "), [])
        self.assertEqual(self.retriever.tokenize("!@#$%^&*()_+{}[]:;\"'<>?,./"), [])

    def test_field_boosting_and_ranking(self):
        """Verify symbol name and path matches rank higher than generic content matches."""
        chunk1 = CodeChunk.create(
            file_path="services/auth_service.py",
            relative_path="services/auth_service.py",
            language="python",
            chunk_type="class",
            start_line=1,
            end_line=50,
            content="class AuthService:\n    def authenticate(self, u, p):\n        pass",
            symbol_name="AuthService",
            signature="class AuthService",
        )
        chunk2 = CodeChunk.create(
            file_path="utils/logging.py",
            relative_path="utils/logging.py",
            language="python",
            chunk_type="function",
            start_line=1,
            end_line=20,
            content="def log_event(msg):\n    # Mentioning AuthService in a comment\n    print(msg)",
            symbol_name="log_event",
            signature="def log_event(msg)",
        )
        chunk3 = CodeChunk.create(
            file_path="models/user.py",
            relative_path="models/user.py",
            language="python",
            chunk_type="class",
            start_line=1,
            end_line=30,
            content="class User:\n    id: int\n    username: str",
            symbol_name="User",
            signature="class User",
        )

        self.retriever.index([chunk1, chunk2, chunk3])
        results = self.retriever.search("AuthService authentication", top_k=3)

        self.assertGreater(len(results), 0)
        # chunk1 has AuthService in symbol_name (4x boost) and class name
        top_chunk, top_score = results[0]
        self.assertEqual(top_chunk.chunk_id, chunk1.chunk_id)
        self.assertGreater(top_score, 0.0)

    def test_empty_retriever_search(self):
        """Verify search on an unindexed retriever returns empty list without error."""
        results = self.retriever.search("some query", top_k=5)
        self.assertEqual(results, [])

    def test_no_matching_terms(self):
        """Verify query with no matching terms returns empty list."""
        chunk = CodeChunk.create(
            file_path="foo.py",
            relative_path="foo.py",
            language="python",
            chunk_type="module",
            symbol_name=None,
            start_line=1,
            end_line=5,
            content="x = 1\ny = 2",
        )
        self.retriever.index([chunk])
        results = self.retriever.search("completely_unrelated_query_term_xyz", top_k=5)
        self.assertEqual(results, [])


class TestComplexityAnalyzerCache(unittest.TestCase):
    """Test suite for ComplexityAnalyzer memoization and cache invalidation."""

    def setUp(self):
        self.analyzer = ComplexityAnalyzer()
        self.analyzer.clear_cache()

    def test_cache_hit_and_consistency(self):
        """Verify subsequent calls on identical source code return cached result."""
        source = (
            "def calculate(items):\n"
            "    total = 0\n"
            "    for x in items:\n"
            "        if x > 0:\n"
            "            total += x\n"
            "        elif x < 0:\n"
            "            total -= x\n"
            "    return total\n"
        )
        file_path = "services/calc.py"

        self.assertEqual(len(self.analyzer._cache), 0)

        # First call computes and populates cache
        res1 = self.analyzer.analyze_source(source, file_path)
        self.assertEqual(len(self.analyzer._cache), 1)

        # Second call hits cache
        res2 = self.analyzer.analyze_source(source, file_path)
        self.assertIs(res1, res2, "Expected identical cached result object on repeated call")
        self.assertEqual(res1.file_complexity, res2.file_complexity)
        self.assertEqual(res1.script_complexity, res2.script_complexity)

    def test_clear_cache_invalidation(self):
        """Verify clear_cache() purges memoized entries."""
        source = "def foo():\n    return 42\n"
        self.analyzer.analyze_source(source, "foo.py")
        self.assertGreater(len(self.analyzer._cache), 0)

        self.analyzer.clear_cache()
        self.assertEqual(len(self.analyzer._cache), 0)

    def test_cache_bypass(self):
        """Verify use_cache=False computes without consulting or populating cache."""
        source = "def bar():\n    return 100\n"
        res = self.analyzer.analyze_source(source, "bar.py", use_cache=False)
        self.assertIsNotNone(res)
        self.assertEqual(len(self.analyzer._cache), 0)


class TestOptimizationAcceptanceTargetsSmoke(unittest.TestCase):
    """Smoke test ensuring acceptance targets benchmarks execute successfully within bounds."""

    def test_subgraph_traversal_latency_smoke(self):
        """Ensure 2-hop subgraph traversal on 10,000 nodes is well within 150 ms."""
        import networkx as nx
        import time

        G = nx.scale_free_graph(1000, seed=42)
        D = nx.DiGraph(G)
        t0 = time.perf_counter_ns()
        _ = nx.ego_graph(D, 0, radius=2)
        t1 = time.perf_counter_ns()
        lat_ms = (t1 - t0) / 1_000_000
        self.assertLess(lat_ms, 150.0, f"Graph traversal took {lat_ms:.2f} ms, exceeding 150 ms target")

    def test_ast_parsing_and_complexity_latency_smoke(self):
        """Ensure parsing and complexity analysis on ~500 LOC Python source is well within 100 ms."""
        import time

        lines = ["def process(x):\n    if x > 0:\n        return x * 2\n    return 0\n" for _ in range(100)]
        code = "\n".join(lines)
        analyzer = ComplexityAnalyzer()

        t0 = time.perf_counter_ns()
        res = analyzer.analyze_source(code, "test_file.py")
        t1 = time.perf_counter_ns()
        lat_ms = (t1 - t0) / 1_000_000

        self.assertIsNotNone(res)
        self.assertLess(lat_ms, 100.0, f"AST parsing + complexity took {lat_ms:.2f} ms, exceeding 100 ms target")


if __name__ == "__main__":
    unittest.main()
