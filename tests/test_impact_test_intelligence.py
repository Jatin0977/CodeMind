"""
Unit tests for CodeMind Phase 8 Milestone 8.3:
Blast-Radius Test Intelligence Engine and Multi-Tier Test Prioritization.
"""

import unittest
from unittest.mock import MagicMock
import networkx as nx

from codemind.graph.models import NodeType, EdgeType
from codemind.impact.models import (
    ChangeTarget,
    BlastRadiusNode,
    BlastRadiusReport,
    TestEvidenceType,
)
from codemind.impact.test_intelligence import TestIntelligenceEngine


class TestMilestone83TestIntelligence(unittest.TestCase):
    """Test suite for Milestone 8.3 Blast-Radius Test Intelligence."""

    def setUp(self):
        self.graph = nx.DiGraph()

        # Source code nodes
        self.graph.add_node("file:auth.py", name="auth.py", node_type=NodeType.FILE, relative_path="auth.py")
        self.graph.add_node("function:auth.py:verify_token", name="verify_token", node_type=NodeType.FUNCTION, relative_path="auth.py")
        self.graph.add_edge("file:auth.py", "function:auth.py:verify_token", edge_type=EdgeType.CONTAINS)

        self.graph.add_node("file:api.py", name="api.py", node_type=NodeType.FILE, relative_path="api.py")
        self.graph.add_node("function:api.py:login", name="login", node_type=NodeType.FUNCTION, relative_path="api.py")
        self.graph.add_edge("file:api.py", "function:api.py:login", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("function:api.py:login", "function:auth.py:verify_token", edge_type=EdgeType.CALLS)

        # Test code nodes
        self.graph.add_node("file:tests/test_auth.py", name="test_auth.py", node_type=NodeType.FILE, relative_path="tests/test_auth.py")
        self.graph.add_node("function:tests/test_auth.py:test_verify_token", name="test_verify_token", node_type=NodeType.FUNCTION, relative_path="tests/test_auth.py")
        self.graph.add_edge("file:tests/test_auth.py", "function:tests/test_auth.py:test_verify_token", edge_type=EdgeType.CONTAINS)

        self.graph.add_node("file:tests/test_api.py", name="test_api.py", node_type=NodeType.FILE, relative_path="tests/test_api.py")
        self.graph.add_node("function:tests/test_api.py:test_login", name="test_login", node_type=NodeType.FUNCTION, relative_path="tests/test_api.py")
        self.graph.add_edge("file:tests/test_api.py", "function:tests/test_api.py:test_login", edge_type=EdgeType.CONTAINS)

        # 1. Direct invocation edge: test_verify_token CALLS verify_token
        self.graph.add_edge("function:tests/test_auth.py:test_verify_token", "function:auth.py:verify_token", edge_type=EdgeType.CALLS)
        # 2. Direct import edge: test_auth.py IMPORTS auth.py
        self.graph.add_edge("file:tests/test_auth.py", "file:auth.py", edge_type=EdgeType.IMPORTS)
        # 3. Direct invocation for api: test_login CALLS login
        self.graph.add_edge("function:tests/test_api.py:test_login", "function:api.py:login", edge_type=EdgeType.CALLS)

        self.target = ChangeTarget(
            node_id="function:auth.py:verify_token",
            name="verify_token",
            entity_type="function",
            file_path="auth.py",
            relative_path="auth.py",
        )

        # Blast radius containing login at depth 1
        bnode_login = BlastRadiusNode(
            node_id="function:api.py:login",
            name="login",
            entity_type="function",
            file_path="api.py",
            depth=1,
            direct_relationship=EdgeType.CALLS,
            path=["function:auth.py:verify_token", "function:api.py:login"],
            tags=["DIRECT_CALLER"],
        )
        self.blast_radius = BlastRadiusReport(
            target=self.target,
            max_depth=3,
            total_impacted=1,
            impacted_nodes=[bnode_login],
            impacted_edges=[],
        )

        self.engine = TestIntelligenceEngine(self.graph)

    def test_multi_tier_discovery_and_ranking(self):
        """Verify tests discovered for Tier 0 (verify_token) and Tier 1 (login)."""
        report = self.engine.analyze_tests(self.target, self.blast_radius)

        self.assertGreater(report.total_tests, 0)
        self.assertIn(0, report.tier_breakdown)
        self.assertIn(1, report.tier_breakdown)

        # Tier 0 tests should be ranked ahead of Tier 1 tests
        t0_tests = [r for r in report.recommendations if r.tier == 0]
        t1_tests = [r for r in report.recommendations if r.tier == 1]

        self.assertTrue(len(t0_tests) > 0)
        self.assertTrue(len(t1_tests) > 0)

        # Top recommendation should be Tier 0 with DIRECT_INVOCATION
        top_rec = report.recommendations[0]
        self.assertEqual(top_rec.tier, 0)
        self.assertEqual(top_rec.evidence_type, TestEvidenceType.DIRECT_INVOCATION.value)
        self.assertGreaterEqual(top_rec.rank_score, 0.90)

    def test_heuristic_mirroring_and_naming(self):
        """Verify heuristic mirroring and naming discovery without AST calls."""
        # Graph with no AST calls from test to source
        g_isolated = nx.DiGraph()
        g_isolated.add_node("file:codemind/auth.py", name="auth.py", node_type=NodeType.FILE, relative_path="codemind/auth.py")
        g_isolated.add_node("function:codemind/auth.py:authenticate", name="authenticate", node_type=NodeType.FUNCTION, relative_path="codemind/auth.py")
        g_isolated.add_edge("file:codemind/auth.py", "function:codemind/auth.py:authenticate", edge_type=EdgeType.CONTAINS)

        g_isolated.add_node("file:tests/test_auth.py", name="test_auth.py", node_type=NodeType.FILE, relative_path="tests/test_auth.py")
        g_isolated.add_node("function:tests/test_auth.py:test_authenticate", name="test_authenticate", node_type=NodeType.FUNCTION, relative_path="tests/test_auth.py")
        g_isolated.add_edge("file:tests/test_auth.py", "function:tests/test_auth.py:test_authenticate", edge_type=EdgeType.CONTAINS)

        engine = TestIntelligenceEngine(g_isolated)
        target = ChangeTarget(
            node_id="function:codemind/auth.py:authenticate",
            name="authenticate",
            entity_type="function",
            file_path="codemind/auth.py",
            relative_path="codemind/auth.py",
        )
        br = BlastRadiusReport(target=target, max_depth=3, total_impacted=0, impacted_nodes=[], impacted_edges=[])

        report = engine.analyze_tests(target, br)
        ev_types = {r.evidence_type for r in report.recommendations}
        self.assertTrue(
            TestEvidenceType.HEURISTIC_NAMING.value in ev_types or
            TestEvidenceType.HEURISTIC_MIRRORING.value in ev_types
        )

    def test_conservative_disclaimer_present(self):
        """Crucial test: report must include disclaimer rejecting coverage guarantees."""
        report = self.engine.analyze_tests(self.target, self.blast_radius)
        self.assertIn("statically derived candidates", report.disclaimer)
        self.assertIn("do not represent dynamic execution", report.disclaimer)


if __name__ == "__main__":
    unittest.main()
