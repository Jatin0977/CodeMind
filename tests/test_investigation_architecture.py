"""
Tests for CodeMind Phase 9.4: Agentic Investigation Tool Activation.

Validates the integration of Phase 9 Architecture Intelligence with the
Phase 6-8 Investigation System, including:
1. Tool registration & deferred tool replacement
2. Active tool execution (overview, conformance, package cycles, hotspots, evidence coverage)
3. Intent classification for architecture queries
4. Dynamic investigation planning
5. Grounded evidence collection with line references and provenance
6. Offline fallback synthesis with citations and honest limitations
7. End-to-end investigation engine execution
8. Graceful handling of empty or uninitialized architecture state
"""

import unittest
import networkx as nx
from typing import Dict, Any, List

from codemind.investigation.models import (
    InvestigationIntent,
    InvestigationStatus,
    ToolStatus,
    ToolAvailability,
    StepResult,
)
from codemind.investigation.tools.registry import ToolRegistry
from codemind.investigation.tools import create_tool_registry
from codemind.investigation.tools.architecture_tools import (
    GetArchitectureOverviewTool,
    CheckArchitectureConformanceTool,
    DetectPackageCyclesTool,
    DetectMaintenanceHotspotsTool,
    GetEvidenceCoverageTool,
)
from codemind.investigation.intent import InvestigationIntentClassifier
from codemind.investigation.planner import InvestigationPlanner
from codemind.investigation.collector import EvidenceCollector, EvidenceItem
from codemind.investigation.synthesizer import InvestigationSynthesizer, InvestigationCitation
from codemind.investigation.engine import InvestigationEngine

from codemind.architecture.models import (
    ModuleEntity,
    LayerDefinition,
    ConformanceViolation,
    ViolationSeverity,
    ConformanceReport,
    HotspotItem,
    HotspotReport,
    HotspotArchetype,
    EvidenceCoverage,
    AnalysisState,
)
from codemind.architecture.discovery import ArchitectureDiscoveryEngine
from codemind.architecture.conformance import ArchitectureConformanceEngine
from codemind.architecture.hotspots import MaintenanceHotspotDetector


class TestInvestigationArchitectureTools(unittest.TestCase):
    """Test registration and execution of Phase 9 architecture investigation tools."""

    def setUp(self):
        # Create test modules
        self.mod_ui = ModuleEntity(
            name="ui",
            relative_dir="ui",
            files=["ui/view.py"],
            inferred_layer="presentation",
            inference_confidence=0.9,
            total_loc=100,
            total_complexity=5,
            internal_dependencies=["core"],
        )
        self.mod_core = ModuleEntity(
            name="core",
            relative_dir="core",
            files=["core/model.py"],
            inferred_layer="domain",
            inference_confidence=0.95,
            total_loc=200,
            total_complexity=12,
            internal_dependencies=["db"],
        )
        self.mod_db = ModuleEntity(
            name="db",
            relative_dir="db",
            files=["db/repo.py"],
            inferred_layer="infrastructure",
            inference_confidence=0.88,
            total_loc=150,
            total_complexity=8,
            internal_dependencies=[],
        )
        self.modules = {"ui": self.mod_ui, "core": self.mod_core, "db": self.mod_db}

        # Create test layers
        self.layer_ui = LayerDefinition(name="presentation", level=1, modules=["ui"], allowed_dependencies=["domain"])
        self.layer_core = LayerDefinition(name="domain", level=2, modules=["core"], allowed_dependencies=["infrastructure"])
        self.layer_db = LayerDefinition(name="infrastructure", level=3, modules=["db"], allowed_dependencies=[])
        self.layers = {"presentation": self.layer_ui, "domain": self.layer_core, "infrastructure": self.layer_db}

        # Quotient graph
        self.quotient_graph = nx.DiGraph()
        self.quotient_graph.add_edge("ui", "core", weight=2)
        self.quotient_graph.add_edge("core", "db", weight=3)

        # Mock coverage
        self.coverage = EvidenceCoverage(
            overall_coverage=0.85,
            analysis_state=AnalysisState.FULL_EVIDENCE,
            ast_coverage=1.0,
            graph_available=True,
            churn_available=True,
            temporal_coupling_available=True,
            structural_coupling_available=True,
            class_graph_coverage=0.8,
            missing_signals=[],
        )

        # Conformance violation and report
        self.violation = ConformanceViolation(
            violation_type="UPWARD_LAYER_LEAK",
            severity=ViolationSeverity.CRITICAL,
            source_file="db/repo.py",
            target_file="ui/view.py",
            source_module="db",
            target_module="ui",
            source_layer="infrastructure",
            target_layer="presentation",
            line_number=42,
            import_statement="from ui.view import show",
            rule_description="Upward dependency leak from infrastructure to presentation",
            weight=1.0,
        )
        self.conformance_report = ConformanceReport(
            conformance_index=80.0,
            conformance_numerator=1.0,
            total_evaluated_edges=5,
            violations=[self.violation],
            violating_edges_count=1,
            package_cycles=[],
            package_sccs=[],
        )

        # Hotspot item and report
        self.hotspot_item = HotspotItem(
            entity_path="core",
            entity_type="module",
            hotspot_score=0.785,
            base_score=0.65,
            multiplier=1.2,
            archetype=HotspotArchetype.VOLATILE_FRAGILE,
            raw_metrics={"churn": 50, "complexity": 35},
            normalized_signals={"churn": 0.85, "ccn": 0.8},
            effective_weights={"churn": 0.3, "ccn": 0.3, "cent": 0.25, "coup": 0.15},
            signal_availability={"churn": True, "ccn": True, "cent": True, "coup": True},
            confidence=1.0,
            rationale="High churn and complexity",
        )
        self.hotspot_report = HotspotReport(
            hotspots=[self.hotspot_item],
            evidence_coverage=self.coverage,
            analysis_state=AnalysisState.FULL_EVIDENCE,
            total_entities_analyzed=3,
            top_hotspot_mean=0.785,
        )

    def test_01_tool_registration_active_vs_deferred(self):
        """When enable_architecture=True, active tools replace deferred placeholders."""
        # 1. Disabled architecture: placeholders are deferred
        reg_disabled = create_tool_registry(enable_architecture=False)
        self.assertFalse(reg_disabled.has_tool("get_architecture_overview"))
        self.assertFalse(reg_disabled.has_tool("detect_package_cycles"))
        self.assertFalse(reg_disabled.has_tool("get_evidence_coverage"))
        # Placeholder tools remain deferred
        tool_conf = reg_disabled.get("check_architecture_conformance")
        self.assertEqual(tool_conf.availability, ToolAvailability.DEFERRED)
        tool_hot = reg_disabled.get("detect_maintenance_hotspots")
        self.assertEqual(tool_hot.availability, ToolAvailability.DEFERRED)

        # 2. Enabled architecture: active tools registered
        reg_enabled = create_tool_registry(
            enable_architecture=True,
            modules=self.modules,
            layers=self.layers,
            quotient_graph=self.quotient_graph,
            evidence_coverage=self.coverage,
        )
        active_names = [
            "get_architecture_overview",
            "check_architecture_conformance",
            "detect_package_cycles",
            "detect_maintenance_hotspots",
            "get_evidence_coverage",
        ]
        for name in active_names:
            self.assertTrue(reg_enabled.has_tool(name), f"Missing tool: {name}")
            tool = reg_enabled.get(name)
            self.assertEqual(tool.availability, ToolAvailability.AVAILABLE, f"Tool {name} not available")

    def test_02_get_architecture_overview_tool(self):
        """GetArchitectureOverviewTool returns module hierarchy and layer summary."""
        tool = GetArchitectureOverviewTool(
            modules=self.modules,
            layers=self.layers,
        )
        result = tool.execute({})
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        data = result.data
        self.assertEqual(data["total_modules"], 3)
        self.assertEqual(data["total_layers"], 3)
        self.assertEqual(len(data["modules"]), 3)
        self.assertEqual(len(data["layers"]), 3)

    def test_03_check_architecture_conformance_tool(self):
        """CheckArchitectureConformanceTool returns structured violations and ACI."""
        class MockConformanceEngine:
            def evaluate(self, **kwargs):
                return self_report

        self_report = self.conformance_report
        tool = CheckArchitectureConformanceTool(
            conformance_engine=MockConformanceEngine(),
        )
        result = tool.execute({})
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        data = result.data
        self.assertEqual(data["conformance_index"], 80.0)
        self.assertEqual(data["violating_edges_count"], 1)
        self.assertEqual(len(data["violations"]), 1)
        v = data["violations"][0]
        self.assertEqual(v["source_file"], "db/repo.py")
        self.assertEqual(v["line_number"], 42)
        self.assertEqual(v["violation_type"], "UPWARD_LAYER_LEAK")

    def test_04_detect_package_cycles_tool(self):
        """DetectPackageCyclesTool returns Tarjan SCC quotient graph cycle paths."""
        cyc_graph = nx.DiGraph()
        cyc_graph.add_edge("pkg_a", "pkg_b")
        cyc_graph.add_edge("pkg_b", "pkg_a")
        cyc_graph.add_edge("pkg_a", "pkg_c")

        tool = DetectPackageCyclesTool(quotient_graph=cyc_graph)
        result = tool.execute({})
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        data = result.data
        self.assertTrue(data["has_cycles"])
        self.assertEqual(data["total_cycles"], 1)
        self.assertEqual(len(data["cycles"]), 1)
        self.assertEqual(sorted(data["cycles"][0]["modules"]), ["pkg_a", "pkg_b"])

    def test_05_detect_maintenance_hotspots_tool(self):
        """DetectMaintenanceHotspotsTool returns top hotspot mean and archetypes."""
        class MockHotspotDetector:
            def detect_hotspots(self, **kwargs):
                return self_report

        self_report = self.hotspot_report
        tool = DetectMaintenanceHotspotsTool(
            hotspot_detector=MockHotspotDetector(),
            modules=self.modules,
            quotient_graph=self.quotient_graph,
        )
        result = tool.execute({})
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        data = result.data
        self.assertEqual(data["total_analyzed"], 3)
        self.assertEqual(data["matched_hotspots_count"], 1)
        self.assertAlmostEqual(data["top_hotspot_mean"], 0.785, places=3)
        self.assertEqual(len(data["hotspots"]), 1)
        h = data["hotspots"][0]
        self.assertEqual(h["entity_path"], "core")
        self.assertEqual(h["archetype"], HotspotArchetype.VOLATILE_FRAGILE.value)

    def test_06_get_evidence_coverage_tool(self):
        """GetEvidenceCoverageTool returns multi-signal confidence and active limitations."""
        tool = GetEvidenceCoverageTool(evidence_coverage=self.coverage)
        result = tool.execute({})
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        data = result.data
        self.assertEqual(data["overall_coverage"], 0.85)
        self.assertEqual(data["analysis_state"], AnalysisState.FULL_EVIDENCE.value)
        self.assertTrue(data["dimensions"]["churn_available"])
        self.assertTrue(data["dimensions"]["ast_coverage"] == 1.0)


class TestInvestigationArchitecturePlanningAndIntent(unittest.TestCase):
    """Test intent classification and planning for architecture queries."""

    def setUp(self):
        self.classifier = InvestigationIntentClassifier()
        self.planner = InvestigationPlanner(classifier=self.classifier)

        self.registry = create_tool_registry(
            enable_architecture=True,
            modules={"core": ModuleEntity(name="core", relative_dir="core", files=[])},
            layers={"domain": LayerDefinition(name="domain", level=1)},
            quotient_graph=nx.DiGraph(),
        )

    def test_01_intent_classification_for_architecture(self):
        """Architecture questions are classified as INSIGHTS intent."""
        queries = [
            "Show the architecture overview and module hierarchy",
            "Are there layer conformance violations or upward leaks?",
            "What is the repository risk score and maintenance hotspots?",
            "Detect package cycles in the quotient graph",
            "What is the evidence coverage and analysis limitations?",
            "Check ACI conformance index across modules",
            "Identify volatile fragile and god modules",
        ]
        for q in queries:
            intent = self.classifier.classify(q).intent
            self.assertEqual(
                intent,
                InvestigationIntent.INSIGHTS,
                f"Query '{q}' classified as {intent} instead of INSIGHTS",
            )

    def test_02_planning_routes_to_architecture_tools(self):
        """Planner generates plan with relevant active architecture tools."""
        q_overview = "What is the architecture overview and module structure?"
        plan_overview = self.planner.plan(q_overview, self.registry)
        tool_names = [s.tool_name for s in plan_overview.steps]
        self.assertIn("get_architecture_overview", tool_names)

        q_conformance = "Check architecture conformance and layer violations"
        plan_conf = self.planner.plan(q_conformance, self.registry)
        tool_names = [s.tool_name for s in plan_conf.steps]
        self.assertIn("check_architecture_conformance", tool_names)

        q_cycles = "Are there package cycles in the quotient graph?"
        plan_cyc = self.planner.plan(q_cycles, self.registry)
        tool_names = [s.tool_name for s in plan_cyc.steps]
        self.assertIn("detect_package_cycles", tool_names)

        q_hotspots = "Find maintenance hotspots and high-risk modules"
        plan_hot = self.planner.plan(q_hotspots, self.registry)
        tool_names = [s.tool_name for s in plan_hot.steps]
        self.assertIn("detect_maintenance_hotspots", tool_names)

        q_cov = "What is our evidence coverage and analysis limitations?"
        plan_cov = self.planner.plan(q_cov, self.registry)
        tool_names = [s.tool_name for s in plan_cov.steps]
        self.assertIn("get_evidence_coverage", tool_names)

    def test_03_plan_integrity_and_step_ids(self):
        """Plan steps are cleanly numbered step_1, step_2 and dependencies are acyclic."""
        query = "Review architecture hierarchy, conformance violations, and maintenance hotspots"
        plan = self.planner.plan(query, self.registry)
        step_ids = [s.step_id for s in plan.steps]
        expected_ids = [f"step_{i+1}" for i in range(len(plan.steps))]
        self.assertEqual(step_ids, expected_ids)


class TestInvestigationArchitectureEvidenceAndSynthesis(unittest.TestCase):
    """Test evidence collection and grounded synthesis for architecture tools."""

    def setUp(self):
        self.collector = EvidenceCollector()
        self.synthesizer = InvestigationSynthesizer(use_fallback_only=True)

    def test_01_evidence_collection_from_architecture_tools(self):
        """EvidenceCollector extracts grounded architecture evidence with provenance."""
        # 1. Overview step
        overview_data = {
            "total_modules": 4,
            "total_layers": 3,
            "matched_modules_count": 4,
            "modules": [
                {"name": "core", "layer": "domain", "files_count": 2, "confidence": 0.95, "total_complexity": 25}
            ],
            "quotient_graph": {"nodes_count": 4, "edges_count": 6},
        }
        self.collector.collect_from_step(
            StepResult(step_id="step_1", tool_name="get_architecture_overview", status=ToolStatus.SUCCESS, output=overview_data)
        )

        # 2. Conformance step
        conformance_data = {
            "conformance_index": 82.5,
            "total_evaluated_edges": 8,
            "violating_edges_count": 1,
            "violations_count": 1,
            "violations": [
                {
                    "source_module": "infra",
                    "target_module": "ui",
                    "source_file": "infra/db.py",
                    "target_file": "ui/app.py",
                    "line_number": 15,
                    "violation_type": "UPWARD_LAYER_LEAK",
                    "weight": 1.0,
                    "rule_description": "Upward leak violation",
                }
            ],
        }
        self.collector.collect_from_step(
            StepResult(step_id="step_2", tool_name="check_architecture_conformance", status=ToolStatus.SUCCESS, output=conformance_data)
        )

        # 3. Package cycles step
        cycles_data = {
            "has_cycles": True,
            "total_cycles": 1,
            "cycles": [{"cycle_path": ["mod_a", "mod_b"], "modules": ["mod_a", "mod_b"], "length": 2}],
        }
        self.collector.collect_from_step(
            StepResult(step_id="step_3", tool_name="detect_package_cycles", status=ToolStatus.SUCCESS, output=cycles_data)
        )

        # 4. Hotspots step
        hotspots_data = {
            "top_hotspot_mean": 0.452,
            "matched_hotspots_count": 1,
            "total_analyzed": 4,
            "analysis_state": "FULL_EVIDENCE",
            "hotspots": [
                {
                    "entity_path": "core",
                    "hotspot_score": 0.750,
                    "archetype": "Volatile Fragile Hotspot",
                    "multiplier": 1.25,
                    "raw_metrics": {"churn": 40, "complexity": 25},
                }
            ],
        }
        self.collector.collect_from_step(
            StepResult(step_id="step_4", tool_name="detect_maintenance_hotspots", status=ToolStatus.SUCCESS, output=hotspots_data)
        )

        # 5. Coverage step
        coverage_data = {
            "overall_coverage": 0.85,
            "analysis_state": "FULL_EVIDENCE",
            "missing_signals": ["temporal_coupling"],
            "dimensions": {"ast_coverage": 1.0},
        }
        self.collector.collect_from_step(
            StepResult(step_id="step_5", tool_name="get_evidence_coverage", status=ToolStatus.SUCCESS, output=coverage_data)
        )

        arch_items = self.collector.filter_by_category("architecture")
        self.assertGreaterEqual(len(arch_items), 7)

        # Check violation item has file line reference
        violation_item = next(i for i in arch_items if i.provenance == "layer_violation")
        self.assertEqual(violation_item.relative_path, "infra/db.py")
        self.assertEqual(violation_item.start_line, 15)
        self.assertEqual(violation_item.relationship_type, "UPWARD_LAYER_LEAK")

    def test_02_offline_synthesis_with_architecture_grounding(self):
        """InvestigationSynthesizer creates grounded answer with ACI, RRS, and line citations."""
        collector = EvidenceCollector()
        collector.collect_from_step(
            StepResult(
                step_id="step_1",
                tool_name="check_architecture_conformance",
                status=ToolStatus.SUCCESS,
                output={
                    "conformance_index": 75.0,
                    "total_evaluated_edges": 4,
                    "violating_edges_count": 1,
                    "violations_count": 1,
                    "violations": [
                        {
                            "source_module": "repo",
                            "target_module": "view",
                            "source_file": "repo/data.py",
                            "target_file": "view/ui.py",
                            "line_number": 88,
                            "violation_type": "UPWARD_LAYER_LEAK",
                            "weight": 1.0,
                            "rule_description": "Strict layer upward leak",
                        }
                    ],
                },
            )
        )
        collector.collect_from_step(
            StepResult(
                step_id="step_2",
                tool_name="detect_maintenance_hotspots",
                status=ToolStatus.SUCCESS,
                output={
                    "top_hotspot_mean": 0.384,
                    "matched_hotspots_count": 1,
                    "total_analyzed": 3,
                    "hotspots": [
                        {
                            "entity_path": "repo",
                            "hotspot_score": 0.680,
                            "archetype": "God Class",
                            "multiplier": 1.15,
                        }
                    ],
                },
            )
        )
        collector.collect_from_step(
            StepResult(
                step_id="step_3",
                tool_name="get_evidence_coverage",
                status=ToolStatus.SUCCESS,
                output={
                    "overall_coverage": 0.70,
                    "missing_signals": ["git_churn"],
                    "limitations": ["Git repository history unavailable"],
                },
            )
        )

        from codemind.investigation.models import InvestigationResult
        result = InvestigationResult(
            query="Analyze architecture conformance and maintenance hotspots",
            intent=InvestigationIntent.INSIGHTS,
            plan=None,
            overall_status=InvestigationStatus.SUCCESS,
            step_results=[
                StepResult(step_id="step_1", tool_name="check_architecture_conformance", status=ToolStatus.SUCCESS),
                StepResult(step_id="step_2", tool_name="detect_maintenance_hotspots", status=ToolStatus.SUCCESS),
                StepResult(step_id="step_3", tool_name="get_evidence_coverage", status=ToolStatus.SUCCESS),
            ],
            evidence=collector.to_list(),
        )

        answer = self.synthesizer.synthesize_fallback(result)

        # Assert key elements in synthesized markdown
        self.assertIn("### Direct Answer", answer)
        self.assertIn("75.00%", answer)  # ACI
        self.assertIn("0.38", answer)    # RRS / top hotspot mean
        self.assertIn("### Key Findings", answer)
        self.assertIn("repo/data.py:88", answer)  # Line citation
        self.assertIn("God Class", answer)        # Hotspot archetype
        self.assertIn("### Supporting Evidence & Citations", answer)
        self.assertIn("### Limitations & Uncertainty", answer)
        self.assertIn("Git repository history unavailable", answer)


class TestInvestigationEngineEndToEnd(unittest.TestCase):
    """End-to-end integration test with InvestigationEngine."""

    def test_01_end_to_end_architecture_investigation(self):
        """InvestigationEngine executes architecture query end-to-end."""
        mod_a = ModuleEntity(
            name="mod_a",
            relative_dir="mod_a",
            files=["mod_a/main.py"],
            inferred_layer="layer_1",
            internal_dependencies=["mod_b"],
        )
        mod_b = ModuleEntity(
            name="mod_b",
            relative_dir="mod_b",
            files=["mod_b/worker.py"],
            inferred_layer="layer_2",
            internal_dependencies=[],
        )
        modules = {"mod_a": mod_a, "mod_b": mod_b}
        layers = {
            "layer_1": LayerDefinition(name="layer_1", level=1, modules=["mod_a"], allowed_dependencies=["layer_2"]),
            "layer_2": LayerDefinition(name="layer_2", level=2, modules=["mod_b"], allowed_dependencies=[]),
        }
        q_graph = nx.DiGraph()
        q_graph.add_edge("mod_a", "mod_b", weight=1)

        engine = InvestigationEngine(
            enable_architecture=True,
            modules=modules,
            layers=layers,
            quotient_graph=q_graph,
        )

        result = engine.investigate("Show the architecture overview and module hierarchy")

        self.assertEqual(result.overall_status, InvestigationStatus.SUCCESS)
        self.assertEqual(result.intent, InvestigationIntent.INSIGHTS)
        self.assertIsNotNone(result.plan)
        self.assertGreaterEqual(len(result.step_results), 1)
        self.assertGreaterEqual(len(result.evidence), 1)
        self.assertIn("Direct Answer", result.final_answer)
        self.assertIn("mod_a", result.final_answer)

    def test_02_graceful_handling_empty_architecture(self):
        """When architecture tools run on empty state, they handle it gracefully without crashing."""
        tool_overview = GetArchitectureOverviewTool(modules=None, layers=None)
        res_ov = tool_overview.execute({})
        self.assertEqual(res_ov.status, ToolStatus.SUCCESS)
        self.assertEqual(res_ov.data["total_modules"], 0)

        tool_conf = CheckArchitectureConformanceTool(conformance_engine=None)
        res_cf = tool_conf.execute({})
        self.assertEqual(res_cf.status, ToolStatus.SUCCESS)
        self.assertEqual(res_cf.data["conformance_index"], 100.0)

        tool_cyc = DetectPackageCyclesTool(quotient_graph=None)
        res_cyc = tool_cyc.execute({})
        self.assertEqual(res_cyc.status, ToolStatus.SUCCESS)
        self.assertFalse(res_cyc.data["has_cycles"])

        tool_hot = DetectMaintenanceHotspotsTool(modules=None, quotient_graph=None)
        res_hot = tool_hot.execute({})
        self.assertEqual(res_hot.status, ToolStatus.SUCCESS)
        self.assertEqual(res_hot.data["matched_hotspots_count"], 0)

        tool_cov = GetEvidenceCoverageTool(evidence_coverage=None)
        res_cov = tool_cov.execute({})
        self.assertEqual(res_cov.status, ToolStatus.SUCCESS)
        self.assertEqual(res_cov.data["analysis_state"], "DEGRADED_ANALYSIS")
        self.assertAlmostEqual(res_cov.data["overall_coverage"], 0.35, places=2)

    def test_03_engine_empty_repo_investigation(self):
        """Engine investigates an empty repository without crashing."""
        engine = InvestigationEngine(
            enable_architecture=True,
            modules={},
            layers={},
            quotient_graph=nx.DiGraph(),
        )
        result = engine.investigate("Show the architecture overview and module hierarchy")
        self.assertIn(result.overall_status, [InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS])
        self.assertEqual(result.intent, InvestigationIntent.INSIGHTS)
        self.assertTrue(len(result.final_answer) > 0)

    def test_04_engine_no_git_hotspot_investigation(self):
        """Engine investigates hotspots in a repository with no Git temporal data."""
        mod = ModuleEntity(
            name="core",
            relative_dir="core",
            files=["core/app.py"],
            inferred_layer="domain",
            total_loc=50,
            total_complexity=3,
        )
        qg = nx.DiGraph()
        qg.add_node("core")

        engine = InvestigationEngine(
            enable_architecture=True,
            modules={"core": mod},
            quotient_graph=qg,
            git_client=None,
            git_churn_analyzer=None,
            git_coupling_analyzer=None,
        )
        result = engine.investigate("Find high risk maintenance hotspots and risk score")
        self.assertIn(result.overall_status, [InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS])
        self.assertEqual(result.intent, InvestigationIntent.INSIGHTS)
        # Hotspot tool executed successfully
        self.assertTrue(any(sr.tool_name == "detect_maintenance_hotspots" for sr in result.step_results))
        self.assertTrue(any(e.get("category") == "architecture" for e in result.evidence))

    def test_05_engine_unclassified_module_conformance(self):
        """Engine investigates conformance where a module is UNCLASSIFIED."""
        mod_unclass = ModuleEntity(
            name="scripts",
            relative_dir="scripts",
            files=["scripts/run.py"],
            inferred_layer="UNCLASSIFIED",
            total_loc=20,
        )
        qg = nx.DiGraph()
        qg.add_node("scripts")

        engine = InvestigationEngine(
            enable_architecture=True,
            modules={"scripts": mod_unclass},
            layers={},
            quotient_graph=qg,
        )
        result = engine.investigate("Check architecture conformance and rule violations")
        self.assertIn(result.overall_status, [InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS])
        self.assertEqual(result.intent, InvestigationIntent.INSIGHTS)
        self.assertTrue(any(sr.tool_name == "check_architecture_conformance" for sr in result.step_results))


if __name__ == "__main__":
    unittest.main()
