"""
Unit tests for CodeMind Phase 8 Milestone 8.1:
Core Change Impact Engine, Target Resolution, and Subgraph Centrality.
"""

import unittest
import networkx as nx

from codemind.graph.models import NodeType, EdgeType
from codemind.impact.models import (
    AmbiguousTargetError,
    TargetNotFoundError,
    ImpactAnalysisConfig,
)
from codemind.impact.resolver import ChangeTargetResolver
from codemind.impact.engine import ChangeImpactEngine


class TestMilestone81ImpactEngine(unittest.TestCase):
    """Test suite for Milestone 8.1 Core Change Impact Engine and Target Resolution."""

    def setUp(self):
        """Construct a representative heterogeneous test graph."""
        self.graph = nx.DiGraph()

        # Files
        self.graph.add_node("file:auth.py", name="auth.py", node_type=NodeType.FILE, relative_path="auth.py")
        self.graph.add_node("file:api.py", name="api.py", node_type=NodeType.FILE, relative_path="api.py")
        self.graph.add_node("file:worker.py", name="worker.py", node_type=NodeType.FILE, relative_path="worker.py")
        self.graph.add_node("file:models.py", name="models.py", node_type=NodeType.FILE, relative_path="models.py")

        # Classes
        self.graph.add_node(
            "class:models.py:BaseEntity",
            name="BaseEntity",
            node_type=NodeType.CLASS,
            relative_path="models.py",
            metadata={"class_name": "BaseEntity"},
        )
        self.graph.add_node(
            "class:models.py:User",
            name="User",
            node_type=NodeType.CLASS,
            relative_path="models.py",
            metadata={"class_name": "User"},
        )

        # Functions & Methods
        self.graph.add_node(
            "function:auth.py:verify_token",
            name="verify_token",
            node_type=NodeType.FUNCTION,
            relative_path="auth.py",
            metadata={"complexity": 5},
        )
        self.graph.add_node(
            "function:api.py:login_route",
            name="login_route",
            node_type=NodeType.FUNCTION,
            relative_path="api.py",
            metadata={"complexity": 3},
        )
        self.graph.add_node(
            "method:models.py:User.save",
            name="save",
            node_type=NodeType.METHOD,
            relative_path="models.py",
            metadata={"class_name": "User", "complexity": 4},
        )
        self.graph.add_node(
            "function:worker.py:save",
            name="save",
            node_type=NodeType.FUNCTION,
            relative_path="worker.py",
            metadata={"complexity": 2},
        )

        # Non-code nodes (Commit)
        self.graph.add_node("commit:c12345", name="c12345", node_type=NodeType.COMMIT)

        # Container Edges (CONTAINS)
        self.graph.add_edge("file:auth.py", "function:auth.py:verify_token", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:api.py", "function:api.py:login_route", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:models.py", "class:models.py:BaseEntity", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:models.py", "class:models.py:User", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("class:models.py:User", "method:models.py:User.save", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:worker.py", "function:worker.py:save", edge_type=EdgeType.CONTAINS)

        # Code Dependency Edges
        # login_route CALLS verify_token
        self.graph.add_edge("function:api.py:login_route", "function:auth.py:verify_token", edge_type=EdgeType.CALLS)
        # api.py IMPORTS auth.py
        self.graph.add_edge("file:api.py", "file:auth.py", edge_type=EdgeType.IMPORTS)
        # User INHERITS BaseEntity
        self.graph.add_edge("class:models.py:User", "class:models.py:BaseEntity", edge_type=EdgeType.INHERITS)

        # Temporal Edges
        # auth.py CO_CHANGED_WITH worker.py (reciprocal)
        self.graph.add_edge("file:auth.py", "file:worker.py", edge_type=EdgeType.CO_CHANGED_WITH)
        self.graph.add_edge("file:worker.py", "file:auth.py", edge_type=EdgeType.CO_CHANGED_WITH)
        # worker.py CO_CHANGED_WITH models.py (reciprocal)
        self.graph.add_edge("file:worker.py", "file:models.py", edge_type=EdgeType.CO_CHANGED_WITH)
        self.graph.add_edge("file:models.py", "file:worker.py", edge_type=EdgeType.CO_CHANGED_WITH)

        # Commit Edge (CHANGED_IN)
        self.graph.add_edge("file:auth.py", "commit:c12345", edge_type=EdgeType.CHANGED_IN)

        self.resolver = ChangeTargetResolver(self.graph)
        self.engine = ChangeImpactEngine(self.graph)

    def test_target_resolution_canonical_id(self):
        """Stage 1: Resolve exact canonical node ID."""
        target = self.resolver.resolve("function:auth.py:verify_token")
        self.assertEqual(target.node_id, "function:auth.py:verify_token")
        self.assertEqual(target.name, "verify_token")
        self.assertEqual(target.entity_type, NodeType.FUNCTION)
        self.assertEqual(target.resolution_method, "canonical_id")

    def test_target_resolution_file_path(self):
        """Stage 2: Resolve exact file path."""
        target = self.resolver.resolve("auth.py")
        self.assertEqual(target.node_id, "file:auth.py")
        self.assertEqual(target.entity_type, NodeType.FILE)
        self.assertEqual(target.resolution_method, "file_path")

    def test_target_resolution_qualified_symbol(self):
        """Stage 3: Resolve qualified symbol path."""
        target = self.resolver.resolve("models.py::User::save")
        self.assertEqual(target.node_id, "method:models.py:User.save")
        self.assertEqual(target.name, "save")
        self.assertEqual(target.entity_type, NodeType.METHOD)
        self.assertEqual(target.resolution_method, "qualified_symbol")

    def test_target_resolution_unqualified_unique(self):
        """Stage 4a: Resolve unique unqualified symbol."""
        target = self.resolver.resolve("verify_token")
        self.assertEqual(target.node_id, "function:auth.py:verify_token")
        self.assertEqual(target.resolution_method, "unqualified_symbol")

    def test_target_resolution_unqualified_ambiguous_raises(self):
        """Stage 4b: Ambiguous unqualified symbol raises AmbiguousTargetError."""
        with self.assertRaises(AmbiguousTargetError) as ctx:
            self.resolver.resolve("save")

        err = ctx.exception
        self.assertEqual(err.query, "save")
        self.assertEqual(len(err.candidates), 2)
        candidate_ids = {c["node_id"] for c in err.candidates}
        self.assertIn("method:models.py:User.save", candidate_ids)
        self.assertIn("function:worker.py:save", candidate_ids)

    def test_target_resolution_not_found_with_suggestions(self):
        """Stage 5: Target not found raises TargetNotFoundError with suggestions."""
        with self.assertRaises(TargetNotFoundError) as ctx:
            self.resolver.resolve("verfy_token")

        err = ctx.exception
        self.assertEqual(err.query, "verfy_token")
        self.assertTrue(len(err.suggestions) > 0)
        self.assertIn("verify_token", err.suggestions)

    def test_subgraph_isolation(self):
        """Verify code dependency subgraph isolates pure code entities and dependency edges."""
        g_code = self.engine.code_subgraph

        # Excludes commits
        self.assertNotIn("commit:c12345", g_code)

        # Includes code entities
        self.assertIn("file:auth.py", g_code)
        self.assertIn("function:auth.py:verify_token", g_code)
        self.assertIn("function:api.py:login_route", g_code)

        # Excludes CONTAINS edges from dependency calculation
        self.assertFalse(g_code.has_edge("file:auth.py", "function:auth.py:verify_token"))
        # Excludes temporal CO_CHANGED_WITH edges
        self.assertFalse(g_code.has_edge("file:auth.py", "file:worker.py"))
        # Preserves CALLS, INHERITS, IMPORTS
        self.assertTrue(g_code.has_edge("function:api.py:login_route", "function:auth.py:verify_token"))
        self.assertTrue(g_code.has_edge("file:api.py", "file:auth.py"))
        self.assertTrue(g_code.has_edge("class:models.py:User", "class:models.py:BaseEntity"))

    def test_centrality_metrics(self):
        """Verify in-degree and PageRank centrality computation on code subgraph."""
        centrality = self.engine.compute_centrality("function:auth.py:verify_token")
        self.assertGreater(centrality.in_degree_centrality, 0.0)
        self.assertGreater(centrality.pagerank, 0.0)
        self.assertGreater(centrality.composite_centrality, 0.0)
        self.assertIsNone(centrality.betweenness_centrality)

        # Diagnostic betweenness on-demand
        diag_b = self.engine.compute_diagnostic_betweenness("function:auth.py:verify_token")
        self.assertIsInstance(diag_b, float)

    def test_blast_radius_reverse_calls_and_granularity_lifting(self):
        """
        Verify reverse dependency blast radius for verify_token:
        1. Direct CALLER: login_route (CALLS)
        2. Hierarchical Granularity Lifting: parent file auth.py imported by api.py (COARSE_FILE_DEPENDENT)
        3. Strictly 1-hop temporal co-change: worker.py (TEMPORAL_CO_CHANGE)
        4. Non-transitivity: models.py is coupled to worker.py, but MUST NOT be in blast radius of auth.py!
        """
        target = self.resolver.resolve("verify_token")
        report = self.engine.analyze_blast_radius(target, max_depth=3, include_temporal=True)

        self.assertEqual(report.target.node_id, "function:auth.py:verify_token")
        impacted_ids = {n.node_id for n in report.impacted_nodes}

        # login_route is direct caller
        self.assertIn("function:api.py:login_route", impacted_ids)
        caller_node = next(n for n in report.impacted_nodes if n.node_id == "function:api.py:login_route")
        self.assertEqual(caller_node.depth, 1)
        self.assertIn("DIRECT_CALLER", caller_node.tags)

        # api.py is coarse file dependent via import of auth.py
        self.assertIn("file:api.py", impacted_ids)
        imp_node = next(n for n in report.impacted_nodes if n.node_id == "file:api.py")
        self.assertIn("COARSE_FILE_DEPENDENT", imp_node.tags)

        # worker.py is strictly 1-hop temporal co-change
        self.assertIn("file:worker.py", impacted_ids)
        temp_node = next(n for n in report.impacted_nodes if n.node_id == "file:worker.py")
        self.assertEqual(temp_node.depth, 1)
        self.assertIn("TEMPORAL_CO_CHANGE", temp_node.tags)

        # CRITICAL TEST: models.py is coupled with worker.py (2 hops away),
        # but logical coupling MUST NOT be transitively expanded!
        self.assertNotIn("file:models.py", impacted_ids)

    def test_blast_radius_container_downward_propagation(self):
        """Verify modifying a container (BaseEntity class or models.py file) propagates to contained members."""
        target = self.resolver.resolve("BaseEntity")
        report = self.engine.analyze_blast_radius(target, max_depth=3)

        impacted_ids = {n.node_id for n in report.impacted_nodes}
        # Subclass User is impacted via INHERITS
        self.assertIn("class:models.py:User", impacted_ids)
        subclass_node = next(n for n in report.impacted_nodes if n.node_id == "class:models.py:User")
        self.assertIn("SUBCLASS", subclass_node.tags)


if __name__ == "__main__":
    unittest.main()
