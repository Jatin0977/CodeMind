"""
Unit and integration tests for CodeMind Phase 8 Milestone 8.4:
Target Resolution & Investigation Engine Integration (Active Tools, Collector, and Synthesizer).
"""

import unittest
import networkx as nx

from codemind.graph.models import NodeType, EdgeType
from codemind.graph.query import GraphQueryEngine
from codemind.investigation.models import ToolStatus, ToolAvailability, StepResult
from codemind.investigation.tools import create_tool_registry, create_deferred_tools
from codemind.investigation.tools.impact_tools import MultiSignalImpactTool, GetTestCoverageTool
from codemind.investigation.collector import EvidenceCollector
from codemind.investigation.synthesizer import InvestigationSynthesizer
from codemind.investigation.models import InvestigationResult, InvestigationIntent, InvestigationStatus


class TestMilestone84InvestigationIntegration(unittest.TestCase):
    """Test suite for Milestone 8.4 Target Resolution & Investigation Engine Integration."""

    def setUp(self):
        self.graph = nx.DiGraph()

        # Files
        self.graph.add_node("file:auth.py", name="auth.py", node_type=NodeType.FILE, relative_path="auth.py")
        self.graph.add_node("file:api.py", name="api.py", node_type=NodeType.FILE, relative_path="api.py")
        self.graph.add_node("file:tests/test_auth.py", name="test_auth.py", node_type=NodeType.FILE, relative_path="tests/test_auth.py")

        # Symbols
        self.graph.add_node("function:auth.py:verify_token", name="verify_token", node_type=NodeType.FUNCTION, relative_path="auth.py", metadata={"complexity": 4})
        self.graph.add_node("function:api.py:login", name="login", node_type=NodeType.FUNCTION, relative_path="api.py", metadata={"complexity": 2})
        self.graph.add_node("function:tests/test_auth.py:test_verify_token", name="test_verify_token", node_type=NodeType.FUNCTION, relative_path="tests/test_auth.py")

        # Ambiguous symbol 'save'
        self.graph.add_node("function:auth.py:save", name="save", node_type=NodeType.FUNCTION, relative_path="auth.py")
        self.graph.add_node("function:api.py:save", name="save", node_type=NodeType.FUNCTION, relative_path="api.py")

        # Edges
        self.graph.add_edge("file:auth.py", "function:auth.py:verify_token", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:api.py", "function:api.py:login", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:auth.py", "function:auth.py:save", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:api.py", "function:api.py:save", edge_type=EdgeType.CONTAINS)
        self.graph.add_edge("file:tests/test_auth.py", "function:tests/test_auth.py:test_verify_token", edge_type=EdgeType.CONTAINS)

        self.graph.add_edge("function:api.py:login", "function:auth.py:verify_token", edge_type=EdgeType.CALLS)
        self.graph.add_edge("function:tests/test_auth.py:test_verify_token", "function:auth.py:verify_token", edge_type=EdgeType.CALLS)

        self.query_engine = GraphQueryEngine(self.graph)

    def test_multi_signal_impact_tool_execution(self):
        """Verify MultiSignalImpactTool successfully calculates impact report."""
        tool = MultiSignalImpactTool(query_engine=self.query_engine, has_tests=True)
        res = tool.execute({"node_id": "verify_token", "max_depth": 3})

        self.assertEqual(res.status, ToolStatus.SUCCESS)
        self.assertIsNotNone(res.data)
        self.assertIn("composite_score", res.data)
        self.assertIn("risk_level", res.data)
        self.assertIn("blast_radius", res.data)
        self.assertEqual(res.data["target"]["name"], "verify_token")

    def test_multi_signal_impact_tool_ambiguous_target_error(self):
        """Verify MultiSignalImpactTool handles ambiguous symbols with structured error."""
        tool = MultiSignalImpactTool(query_engine=self.query_engine)
        res = tool.execute({"node_id": "save"})

        self.assertEqual(res.status, ToolStatus.ERROR)
        self.assertIn("ambiguous", res.message.lower())
        self.assertEqual(res.metadata.get("error_type"), "AmbiguousTargetError")
        self.assertIn("candidates", res.data)
        self.assertEqual(len(res.data["candidates"]), 2)

    def test_multi_signal_impact_tool_target_not_found(self):
        """Verify MultiSignalImpactTool handles non-existent symbols with suggestions."""
        tool = MultiSignalImpactTool(query_engine=self.query_engine)
        res = tool.execute({"node_id": "verfy_tokn"})

        self.assertEqual(res.status, ToolStatus.ERROR)
        self.assertEqual(res.metadata.get("error_type"), "TargetNotFoundError")
        self.assertIn("suggestions", res.data)

    def test_get_test_coverage_tool_execution(self):
        """Verify GetTestCoverageTool executes and discovers prioritized tests."""
        tool = GetTestCoverageTool(query_engine=self.query_engine)
        res = tool.execute({"node_id": "verify_token"})

        self.assertEqual(res.status, ToolStatus.SUCCESS)
        self.assertIsNotNone(res.data)
        self.assertIn("recommendations", res.data)
        self.assertGreater(res.data["total_tests"], 0)
        self.assertEqual(res.data["recommendations"][0]["test_target"], "test_verify_token")

    def test_tool_registry_backward_compatibility(self):
        """Default create_tool_registry() call must preserve 17 tools and deferred Phase 8 tools."""
        registry = create_tool_registry()
        self.assertEqual(registry.count(), 17)

        # multi_signal_impact and get_test_coverage must be deferred in default registry
        t_impact = registry.get("multi_signal_impact")
        t_test = registry.get("get_test_coverage")
        self.assertEqual(t_impact.availability, ToolAvailability.DEFERRED)
        self.assertEqual(t_test.availability, ToolAvailability.DEFERRED)

    def test_tool_registry_with_active_impact_tools(self):
        """When enable_impact=True, active Phase 8 tools are registered."""
        registry = create_tool_registry(
            query_engine=self.query_engine,
            enable_impact=True,
            has_tests=True,
        )

        t_impact = registry.get("multi_signal_impact")
        t_test = registry.get("get_test_coverage")

        self.assertEqual(t_impact.availability, ToolAvailability.AVAILABLE)
        self.assertEqual(t_test.availability, ToolAvailability.AVAILABLE)

        # Run active tool through registry
        res = t_impact.execute({"node_id": "verify_token"})
        self.assertEqual(res.status, ToolStatus.SUCCESS)

    def test_evidence_collector_and_synthesizer_integration(self):
        """Verify EvidenceCollector and InvestigationSynthesizer process Phase 8 tools."""
        impact_tool = MultiSignalImpactTool(query_engine=self.query_engine, has_tests=True)
        res_impact = impact_tool.execute({"node_id": "verify_token"})

        step_impact = StepResult(
            step_id="step_1",
            tool_name="multi_signal_impact",
            status=ToolStatus.SUCCESS,
            output=res_impact.data,
        )

        collector = EvidenceCollector()
        added = collector.collect_from_step(step_impact)
        self.assertGreater(added, 0)

        impact_items = collector.filter_by_category("impact")
        self.assertGreater(len(impact_items), 0)

        # Synthesizer integration
        inv_result = InvestigationResult(
            query="What will be affected if I modify verify_token?",
            intent=InvestigationIntent.IMPACT,
            overall_status=InvestigationStatus.SUCCESS,
            step_results=[step_impact],
            evidence=collector.to_list(),
        )

        synthesizer = InvestigationSynthesizer(use_fallback_only=True)
        answer = synthesizer.synthesize(inv_result)

        self.assertIn("verify_token", answer)
        self.assertIn("Risk Level", answer)
        self.assertIn("Change Impact Assessment", answer)


if __name__ == "__main__":
    unittest.main()
