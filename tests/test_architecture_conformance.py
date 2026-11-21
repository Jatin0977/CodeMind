"""
Unit and integration tests for CodeMind Architecture Conformance & Dependency Rule Engine (Phase 9, Milestone 2).
Verifies upward layer leaks, forbidden imports, strict layer skipping, edge-level ACI arithmetic,
and Tarjan SCC package-level cycle detection on the module quotient graph.
"""

import pytest
import networkx as nx

from codemind.architecture.conformance import ArchitectureConformanceEngine
from codemind.architecture.models import (
    ViolationSeverity,
    ConformanceViolation,
    ConformanceReport,
    ModuleEntity,
)


class TestArchitectureConformanceEngine:

    def setup_method(self):
        self.engine = ArchitectureConformanceEngine()

    def test_aci_aggregation_exact_edge_level_with_layer_skipping(self):
        """
        Approved Phase 9.0 test specification:
        - 4 downward edges (3 adjacent, 1 skipping intermediate layer).
        - 1 edge with 3 repeated imports violating upward, forbidden, and skipping.
        - Verifies exact numerator = 1.40, denominator = 5, and ACI = 72.00.
        """
        engine = ArchitectureConformanceEngine()
        engine.register_layer("Presentation", level=1, modules=["web"])
        engine.register_layer("Domain", level=2, modules=["domain"])
        engine.register_layer("Infrastructure", level=3, modules=["db"])
        engine.register_layer("Utilities", level=4, modules=["util"], forbidden=["web"])

        # 4 downward edges:
        # e2: web/view.py (L1) -> domain/service.py (L2) (Adjacent: weight 0.0)
        engine.add_import("web/view.py", "domain/service.py", line=5)
        # e3: domain/service.py (L2) -> db/repo.py (L3) (Adjacent: weight 0.0)
        engine.add_import("domain/service.py", "db/repo.py", line=8)
        # e4: domain/service.py (L2) -> util/logger.py (L4) (Skips L3: weight 0.4)
        engine.add_import("domain/service.py", "util/logger.py", line=12)
        # e5: db/repo.py (L3) -> util/logger.py (L4) (Adjacent: weight 0.0)
        engine.add_import("db/repo.py", "util/logger.py", line=3)

        # 1 edge (e1) with 3 repeated imports on the same physical file edge (util/helper.py -> web/app.py)
        engine.add_import("util/helper.py", "web/app.py", line=10) # UPWARD_LAYER_LEAK (1.0)
        engine.add_import("util/helper.py", "web/app.py", line=20) # FORBIDDEN_IMPORT (1.0)
        engine.add_import("util/helper.py", "web/app.py", line=30) # LAYER_SKIPPING (0.4)

        report = engine.evaluate(strict_layering=True)

        # 1. Total evaluated unique directed file edges
        assert report.total_evaluated_edges == 5

        # 2. Detailed violations captured for line-level inspection
        assert len(report.violations) >= 2
        edge_e1_rules = {v.violation_type for v in report.violations if v.source_file == "util/helper.py"}
        assert "UPWARD_LAYER_LEAK" in edge_e1_rules
        assert "FORBIDDEN_IMPORT" in edge_e1_rules
        assert "LAYER_SKIPPING" in edge_e1_rules

        # 3. Exact Numerator: max(1.0, 1.0, 0.4) for e1 + 0.4 for e4 = 1.40
        assert report.conformance_numerator == 1.40
        assert report.violating_edges_count == 2

        # 4. Exact ACI: 100 * (1 - 1.40 / 5) = 100 * 0.72 = 72.00
        assert report.conformance_index == 72.00

    def test_aci_clean_architecture_returns_100(self):
        """Clean architecture with only compliant downward dependencies yields ACI = 100.00."""
        self.engine.register_layer("Presentation", level=1, modules=["web"])
        self.engine.register_layer("Domain", level=2, modules=["domain"])
        self.engine.register_layer("Infrastructure", level=3, modules=["db"])

        self.engine.add_import("web/app.py", "domain/service.py", line=1)
        self.engine.add_import("domain/service.py", "db/repo.py", line=1)

        report = self.engine.evaluate(strict_layering=True)
        assert report.conformance_index == 100.00
        assert report.conformance_numerator == 0.0
        assert report.total_evaluated_edges == 2
        assert len(report.violations) == 0

    def test_aci_zero_evaluated_imports_boundary(self):
        """Repositories with zero cross-module imports yield ACI = 100.00 by definition."""
        report = self.engine.evaluate()
        assert report.conformance_index == 100.00
        assert report.conformance_numerator == 0.0
        assert report.total_evaluated_edges == 0
        assert len(report.violations) == 0

    def test_upward_layer_leak_detection(self):
        """Lower layer importing higher layer is flagged as CRITICAL UPWARD_LAYER_LEAK."""
        self.engine.register_layer("Domain", level=2, modules=["domain"])
        self.engine.register_layer("Infrastructure", level=3, modules=["db"])

        # db (L3) imports domain (L2) -> Upward leak
        self.engine.add_import("db/models.py", "domain/service.py", line=42, statement="from domain.service import Core")
        report = self.engine.evaluate()

        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.violation_type == "UPWARD_LAYER_LEAK"
        assert v.severity == ViolationSeverity.CRITICAL
        assert v.weight == 1.0
        assert v.source_layer == "Infrastructure"
        assert v.target_layer == "Domain"
        assert v.line_number == 42
        assert "from domain.service import Core" in v.import_statement
        assert report.conformance_index == 0.00  # 1 violation / 1 edge = 0.00

    def test_forbidden_import_detection(self):
        """Target layer in forbidden_dependencies is flagged as CRITICAL FORBIDDEN_IMPORT."""
        self.engine.register_layer("Domain", level=2, modules=["domain"], forbidden=["db"])
        self.engine.register_layer("Infrastructure", level=3, modules=["db"])

        # domain (L2) imports db (L3), but db is explicitly forbidden
        self.engine.add_import("domain/service.py", "db/client.py", line=15)
        report = self.engine.evaluate()

        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.violation_type == "FORBIDDEN_IMPORT"
        assert v.severity == ViolationSeverity.CRITICAL
        assert v.weight == 1.0

    def test_strict_layer_skipping_toggle(self):
        """Layer skipping of > 1 level is flagged only when strict_layering=True."""
        self.engine.register_layer("Presentation", level=1, modules=["web"])
        self.engine.register_layer("Domain", level=2, modules=["domain"])
        self.engine.register_layer("Infrastructure", level=3, modules=["db"])

        # web (L1) -> db (L3) skips domain (L2)
        self.engine.add_import("web/app.py", "db/repo.py", line=7)

        # Relaxed layering: downward skip is permitted
        report_relaxed = self.engine.evaluate(strict_layering=False)
        assert len(report_relaxed.violations) == 0
        assert report_relaxed.conformance_index == 100.00

        # Strict layering: downward skip is flagged as WARNING with weight 0.4
        report_strict = self.engine.evaluate(strict_layering=True)
        assert len(report_strict.violations) == 1
        v = report_strict.violations[0]
        assert v.violation_type == "LAYER_SKIPPING"
        assert v.severity == ViolationSeverity.WARNING
        assert v.weight == 0.4
        assert report_strict.conformance_index == 60.00  # 100 * (1 - 0.4 / 1) = 60.00

    def test_unclassified_modules_excluded_from_aci(self):
        """Imports involving unclassified modules do not alter ACI numerator or denominator."""
        self.engine.register_layer("Presentation", level=1, modules=["web"])
        # util is not registered in any layer -> UNCLASSIFIED
        self.engine.register_file_module("util/orphan.py", "unclassified_module")

        self.engine.add_import("web/app.py", "util/orphan.py", line=3)
        report = self.engine.evaluate()

        # Unclassified edges are excluded from ACI calculations
        assert report.total_evaluated_edges == 0
        assert report.conformance_index == 100.00
        assert len(report.violations) == 0

    def test_package_cycles_tarjan_scc_and_canonical_rotation(self):
        """
        Verify Tarjan SCC detects package-level circular dependency loops in G_M,
        applies canonical lexicographical rotation, and ignores self-loops.
        """
        q_graph = nx.DiGraph()
        # Create 3-module cycle: mod_c -> mod_a -> mod_b -> mod_c
        q_graph.add_edge("mod_c", "mod_a", weight=1)
        q_graph.add_edge("mod_a", "mod_b", weight=2)
        q_graph.add_edge("mod_b", "mod_c", weight=1)
        # Add self-loop on mod_d (must be ignored)
        q_graph.add_edge("mod_d", "mod_d", weight=5)

        engine = ArchitectureConformanceEngine(quotient_graph=q_graph)
        cycles = engine.detect_package_cycles()

        assert len(cycles) == 1
        # Canonical rotation ensures lexicographically smallest node ('mod_a') is first
        assert cycles[0] == ["mod_a", "mod_b", "mod_c"]

    def test_package_cycle_independence_from_aci(self):
        """
        Crucial requirement: Package cycles must remain strictly independent of ACI.
        Intra-layer cycle between peer Domain modules does not alter ACI.
        """
        self.engine.register_layer("Domain", level=2, modules=["domain_a", "domain_b"])

        # Add mutual peer dependencies (domain_a <-> domain_b)
        self.engine.add_import("domain_a/service.py", "domain_b/helper.py", line=10)
        self.engine.add_import("domain_b/client.py", "domain_a/models.py", line=15)

        report = self.engine.evaluate()

        # 1. Package cycle detected
        assert len(report.package_cycles) == 1
        assert set(report.package_cycles[0]) == {"domain_a", "domain_b"}

        # 2. ACI remains 100.00 (peer imports are permitted, cycle does not contaminate ACI)
        assert report.conformance_index == 100.00
        assert len(report.violations) == 0
        assert report.conformance_numerator == 0.0
        assert report.total_evaluated_edges == 2

    def test_non_simple_scc_distinguishes_sccs_from_cycles(self):
        """
        Audit Invariant: In a non-simple SCC (e.g., figure-8 / bow-tie graph sharing a node),
        the SCC cluster must NOT be falsely represented as a directed cycle path by merely
        sorting member nodes. Real elementary directed cycle paths must be reported.
        """
        q_graph = nx.DiGraph()
        # Bow-tie / figure-8 topology:
        # Loop 1: mod_a <-> mod_b
        q_graph.add_edge("mod_a", "mod_b", weight=1)
        q_graph.add_edge("mod_b", "mod_a", weight=1)
        # Loop 2: mod_b <-> mod_c
        q_graph.add_edge("mod_b", "mod_c", weight=1)
        q_graph.add_edge("mod_c", "mod_b", weight=1)

        engine = ArchitectureConformanceEngine(quotient_graph=q_graph)
        sccs = engine.detect_package_sccs()
        cycles = engine.detect_package_cycles()

        # 1. Exactly one strongly connected component containing all 3 mutually reachable modules
        assert len(sccs) == 1
        assert sccs[0] == ["mod_a", "mod_b", "mod_c"]

        # 2. Valid directed cycles are [mod_a, mod_b] and [mod_b, mod_c]
        assert len(cycles) == 2
        assert ["mod_a", "mod_b"] in cycles
        assert ["mod_b", "mod_c"] in cycles

        # 3. Merely sorted SCC ['mod_a', 'mod_b', 'mod_c'] is NOT a cycle (no edge mod_c -> mod_a)
        assert ["mod_a", "mod_b", "mod_c"] not in cycles

        # 4. Invariant: Every reported cycle is an authentic directed path with all edges present
        for cycle in cycles:
            n = len(cycle)
            for i in range(n):
                u, v = cycle[i], cycle[(i + 1) % n]
                assert q_graph.has_edge(u, v), f"Edge {u} -> {v} does not exist in graph!"

    def test_multiple_independent_sccs(self):
        """Verify multiple disjoint strongly connected components are discovered and sorted."""
        q_graph = nx.DiGraph()
        # Disjoint SCC 1: mod_p <-> mod_q
        q_graph.add_edge("mod_p", "mod_q", weight=1)
        q_graph.add_edge("mod_q", "mod_p", weight=1)

        # Disjoint SCC 2: mod_x -> mod_y -> mod_z -> mod_x
        q_graph.add_edge("mod_x", "mod_y", weight=1)
        q_graph.add_edge("mod_y", "mod_z", weight=1)
        q_graph.add_edge("mod_z", "mod_x", weight=1)

        engine = ArchitectureConformanceEngine(quotient_graph=q_graph)
        sccs = engine.detect_package_sccs()
        cycles = engine.detect_package_cycles()

        # Disjoint SCCs
        assert len(sccs) == 2
        assert ["mod_p", "mod_q"] in sccs
        assert ["mod_x", "mod_y", "mod_z"] in sccs

        # Both elementary cycles detected with canonical rotation
        assert len(cycles) == 2
        assert ["mod_p", "mod_q"] in cycles
        assert ["mod_x", "mod_y", "mod_z"] in cycles

    def test_edge_cases_duplicate_edges_and_file_self_loops(self):
        """
        Verify edge cases:
        1. Duplicate imports across the same file edge collapse into 1 evaluated edge.
        2. File self-loops (foo.py -> foo.py) are filtered and do not count.
        """
        self.engine.register_layer("Domain", level=2, modules=["domain"])
        self.engine.register_layer("Infrastructure", level=3, modules=["db"])

        # Multiple duplicate imports on the exact same file edge
        self.engine.add_import("domain/service.py", "db/repo.py", line=10, statement="import db.repo")
        self.engine.add_import("domain/service.py", "db/repo.py", line=15, statement="from db.repo import get_user")
        self.engine.add_import("domain/service.py", "db/repo.py", line=20, statement="from db.repo import save_user")

        # File-level self-loop
        self.engine.add_import("domain/service.py", "domain/service.py", line=5, statement="import domain.service")

        report = self.engine.evaluate()

        # 1 unique evaluated edge (duplicate collapsed, self-loop excluded)
        assert report.total_evaluated_edges == 1
        assert report.conformance_index == 100.00
        assert report.conformance_numerator == 0.0

    def test_edge_cases_empty_graphs_and_unresolved_imports(self):
        """
        Verify edge cases:
        1. Completely empty engine returns clean report without ZeroDivisionError.
        2. Unresolved imports in ParsedFile objects are gracefully ignored.
        """
        from codemind.parsing.base_parser import ParsedFile, ImportStatement

        empty_engine = ArchitectureConformanceEngine()
        report = empty_engine.evaluate()
        assert report.conformance_index == 100.00
        assert report.total_evaluated_edges == 0
        assert report.conformance_numerator == 0.0
        assert report.violations == []
        assert report.package_cycles == []
        assert report.package_sccs == []

        # Engine with parsed file having unresolved 3rd party import
        engine = ArchitectureConformanceEngine()
        engine.register_layer("Domain", level=2, modules=["domain"])
        dummy_parsed = ParsedFile(
            file_path="domain/service.py",
            relative_path="domain/service.py",
            language="python",
            imports=[
                ImportStatement(name="requests", line_number=1, is_from=False),
                ImportStatement(name="non_existent_pkg", line_number=2, is_from=False),
            ],
            functions=[],
            classes=[],
        )
        report_with_unresolved = engine.evaluate(parsed_files={"domain/service.py": dummy_parsed})
        assert report_with_unresolved.total_evaluated_edges == 0
        assert report_with_unresolved.conformance_index == 100.00
        assert len(report_with_unresolved.violations) == 0

    def test_package_exports_codemind_architecture(self):
        """Verify that codemind.architecture exports all public components cleanly."""
        import codemind.architecture as ca

        expected_exports = {
            "ViolationSeverity",
            "AnalysisState",
            "HotspotArchetype",
            "SymbolComplexity",
            "ComplexityMetrics",
            "ModuleEntity",
            "LayerDefinition",
            "UnresolvedImport",
            "EvidenceCoverage",
            "ConformanceViolation",
            "ConformanceReport",
            "ComplexityAnalyzer",
            "SubtreeComplexityVisitor",
            "ArchitectureDiscoveryEngine",
            "SourceRootResolver",
            "DependencyManifestParser",
            "normalize_dependency_name",
            "KNOWN_MODULE_DISCREPANCIES",
            "ArchitectureConformanceEngine",
        }
        for item in expected_exports:
            assert hasattr(ca, item), f"Missing public export: {item}"
        assert expected_exports.issubset(set(ca.__all__))
