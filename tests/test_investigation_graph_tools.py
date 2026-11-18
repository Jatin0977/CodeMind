"""
Unit tests for CodeMind Phase 6 Milestone 2 Graph Tools.
Verifies GetCallersTool, GetCalleesTool, GetDependenciesTool, GetDependentsTool,
TraceStructuralImpactTool, and DetectCyclesTool.
"""

import unittest
import networkx as nx

from codemind.investigation.models import ToolStatus, ToolAvailability
from codemind.investigation.tools.graph_tools import (
    GetCallersTool,
    GetCalleesTool,
    GetDependenciesTool,
    GetDependentsTool,
    TraceStructuralImpactTool,
    DetectCyclesTool,
)
from codemind.graph.models import Node, NodeType, EdgeType
from codemind.graph.query import GraphQueryEngine


class TestInvestigationGraphTools(unittest.TestCase):
    """Test suite verifying graph query tools, relationship preservation, and disclaimer integrity."""

    def setUp(self):
        # Build a controlled multi-relational graph:
        # A (main) -> CALLS -> B (auth) -> CALLS -> C (db)
        # D (admin) -> CALLS -> B (auth)
        # B -> IMPORTS -> E (config)
        # F (subclass) -> INHERITS -> B
        # Cycle: C -> CALLS -> G -> CALLS -> C
        self.graph = nx.DiGraph()
        self.nodes = {
            "func:main": Node("func:main", "main", NodeType.FUNCTION, "main.py", 1, 20),
            "class:auth": Node("class:auth", "AuthService", NodeType.CLASS, "auth.py", 10, 50),
            "func:db": Node("func:db", "query_db", NodeType.FUNCTION, "db.py", 5, 25),
            "func:admin": Node("func:admin", "admin_login", NodeType.FUNCTION, "admin.py", 1, 15),
            "file:config": Node("file:config", "config.py", NodeType.FILE, "config.py", 1, 30),
            "class:custom_auth": Node("class:custom_auth", "CustomAuth", NodeType.CLASS, "custom.py", 1, 40),
            "func:g": Node("func:g", "helper_g", NodeType.FUNCTION, "helper.py", 1, 10),
        }
        for nid, node in self.nodes.items():
            self.graph.add_node(nid, **node.to_dict())

        # Edges
        self.graph.add_edge("func:main", "class:auth", edge_type=EdgeType.CALLS, metadata={"line": 15})
        self.graph.add_edge("func:admin", "class:auth", edge_type=EdgeType.CALLS, metadata={"line": 8})
        self.graph.add_edge("class:auth", "func:db", edge_type=EdgeType.CALLS, metadata={"line": 35})
        self.graph.add_edge("class:auth", "file:config", edge_type=EdgeType.IMPORTS, metadata={"line": 12})
        self.graph.add_edge("class:custom_auth", "class:auth", edge_type=EdgeType.INHERITS, metadata={"line": 2})

        # Cycle: func:db -> func:g -> func:db
        self.graph.add_edge("func:db", "func:g", edge_type=EdgeType.CALLS, metadata={})
        self.graph.add_edge("func:g", "func:db", edge_type=EdgeType.CALLS, metadata={})

        self.query_engine = GraphQueryEngine(self.graph, self.nodes)

    def test_get_callers_tool(self):
        """Verify GetCallersTool finds incoming callers with call metadata."""
        tool = GetCallersTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "get_callers")
        self.assertEqual(tool.availability, ToolAvailability.AVAILABLE)

        res = tool.execute({"node_id": "class:auth"})
        self.assertTrue(res.is_success)
        self.assertEqual(res.data["total_callers"], 2)
        caller_ids = {c["id"] for c in res.data["callers"]}
        self.assertEqual(caller_ids, {"func:main", "func:admin"})

        # Node with no callers
        res_no_callers = tool.execute({"node_id": "func:main"})
        self.assertTrue(res_no_callers.is_success)
        self.assertEqual(res_no_callers.data["total_callers"], 0)

        # Missing node
        res_missing = tool.execute({"node_id": "func:missing"})
        self.assertTrue(res_missing.is_error)
        self.assertIn("not found in knowledge graph", res_missing.message)

    def test_get_callees_tool(self):
        """Verify GetCalleesTool finds outgoing invoked callees."""
        tool = GetCalleesTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "get_callees")

        res = tool.execute({"node_id": "class:auth"})
        self.assertTrue(res.is_success)
        self.assertEqual(res.data["total_callees"], 1)
        self.assertEqual(res.data["callees"][0]["id"], "func:db")

        # Missing node
        res_missing = tool.execute({"node_id": "func:missing"})
        self.assertTrue(res_missing.is_error)

    def test_get_dependencies_tool(self):
        """Verify GetDependenciesTool retrieves outgoing dependency edges."""
        tool = GetDependenciesTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "get_dependencies")

        # class:auth depends directly on func:db (CALLS) and file:config (IMPORTS)
        res_direct = tool.execute({"node_id": "class:auth", "direct_only": True})
        self.assertTrue(res_direct.is_success)
        self.assertEqual(res_direct.data["total_dependencies"], 2)
        dep_ids = {d["id"] for d in res_direct.data["dependencies"]}
        self.assertEqual(dep_ids, {"func:db", "file:config"})

        # Transitive dependencies from func:main: main -> auth -> db, config, g
        res_trans = tool.execute({"node_id": "func:main", "direct_only": False})
        self.assertTrue(res_trans.is_success)
        trans_ids = {d["id"] for d in res_trans.data["dependencies"]}
        self.assertIn("class:auth", trans_ids)
        self.assertIn("func:db", trans_ids)
        self.assertIn("file:config", trans_ids)

    def test_get_dependents_tool(self):
        """Verify GetDependentsTool retrieves incoming dependent edges."""
        tool = GetDependentsTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "get_dependents")

        # Dependents of class:auth: main (CALLS), admin (CALLS), custom_auth (INHERITS)
        res = tool.execute({"node_id": "class:auth", "direct_only": True})
        self.assertTrue(res.is_success)
        self.assertEqual(res.data["total_dependents"], 3)
        dep_ids = {d["id"] for d in res.data["dependents"]}
        self.assertEqual(dep_ids, {"func:main", "func:admin", "class:custom_auth"})

    def test_trace_structural_impact_tool(self):
        """Verify TraceStructuralImpactTool blast radius reachability and disclaimers."""
        tool = TraceStructuralImpactTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "trace_structural_impact")

        # Changing func:db impacts class:auth, and transitively func:main, func:admin, class:custom_auth
        res = tool.execute({"target_node_id": "func:db", "max_depth": 3})
        self.assertTrue(res.is_success)
        self.assertGreater(res.data["total_impacted"], 0)

        # Crucial verification: disclaimer preservation
        disclaimer = res.data.get("disclaimer", "")
        self.assertIn("deterministic static relationships", disclaimer)
        self.assertIn("does not represent runtime execution probability", disclaimer)

        # Missing target node
        res_missing = tool.execute({"target_node_id": "func:missing"})
        self.assertTrue(res_missing.is_error)

    def test_detect_cycles_tool(self):
        """Verify DetectCyclesTool circular dependency detection."""
        tool = DetectCyclesTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "detect_cycles")

        res = tool.execute({"max_cycles": 10})
        self.assertTrue(res.is_success)
        self.assertTrue(res.data["has_cycles"])
        self.assertGreater(res.data["cycle_count"], 0)

        # At least one cycle involves func:db and func:g
        cycles = res.data["cycles"]
        has_expected_cycle = any("func:db" in c and "func:g" in c for c in cycles)
        self.assertTrue(has_expected_cycle)

    def test_uninitialized_query_engine_returns_error(self):
        """Verify all graph tools cleanly report error when query_engine is None."""
        tools = [
            GetCallersTool(None),
            GetCalleesTool(None),
            GetDependenciesTool(None),
            GetDependentsTool(None),
            TraceStructuralImpactTool(None),
            DetectCyclesTool(None),
        ]
        for t in tools:
            res = t.execute({"node_id": "func:main", "target_node_id": "func:main"})
            self.assertTrue(res.is_error, f"{t.name} did not return ERROR when uninitialized")
            self.assertIn("not initialized", res.message)


if __name__ == "__main__":
    unittest.main()
