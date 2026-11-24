"""
Blast-Radius Test Intelligence Engine for CodeMind Phase 8.
Discovers and prioritizes automated regression test candidates across
the change target, directly affected components, and transitive dependents.
Strictly disclaims dynamic test execution and coverage guarantees.
"""

import os
from typing import Dict, Any, Optional, List, Set, Tuple
import networkx as nx

from .models import (
    ChangeTarget,
    BlastRadiusReport,
    BlastRadiusNode,
    TestEvidenceType,
    TestRecommendation,
    TestIntelligenceReport,
    ImpactAnalysisConfig,
)
from ..graph.models import NodeType, EdgeType


class TestIntelligenceEngine:
    """
    Statically discovers and ranks candidate tests across the blast radius.
    Categorizes evidence strictly into structural (DIRECT_INVOCATION, DIRECT_IMPORT)
    and heuristic (HEURISTIC_NAMING, HEURISTIC_MIRRORING, HEURISTIC_CO_CHANGE).
    """
    __test__ = False

    EVIDENCE_WEIGHTS = {
        TestEvidenceType.DIRECT_INVOCATION.value: 1.00,
        TestEvidenceType.DIRECT_IMPORT.value: 0.80,
        TestEvidenceType.HEURISTIC_NAMING.value: 0.60,
        TestEvidenceType.HEURISTIC_MIRRORING.value: 0.50,
        TestEvidenceType.HEURISTIC_CO_CHANGE.value: 0.40,
    }

    def __init__(
        self,
        graph: nx.DiGraph,
        config: Optional[ImpactAnalysisConfig] = None,
        coupling_analyzer: Optional[Any] = None,
        repo: Optional[Any] = None,
    ):
        self.graph = graph
        self.config = config or ImpactAnalysisConfig()
        self.coupling_analyzer = coupling_analyzer
        self.repo = repo
        self._test_nodes: Optional[List[Tuple[str, Dict[str, Any]]]] = None

    @property
    def test_nodes(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Collect all test files, test classes, and test functions from the graph."""
        if self._test_nodes is None:
            self._test_nodes = []
            for n, d in self.graph.nodes(data=True):
                if self._is_test_entity(n, d):
                    self._test_nodes.append((n, d))
        return self._test_nodes

    def analyze_tests(
        self,
        target: ChangeTarget,
        blast_radius: BlastRadiusReport,
    ) -> TestIntelligenceReport:
        """
        Discover and prioritize candidate tests across:
        - Tier 0: Direct Change Target
        - Tier 1: Directly Affected Components (depth 1)
        - Tier 2: Transitively Affected Components (depth >= 2)

        Returns:
            TestIntelligenceReport with prioritized recommendations.
        """
        candidate_map: Dict[Tuple[str, str], TestRecommendation] = {}

        # 1. Tier 0 Discovery: Direct Target
        self._discover_tests_for_entity(
            entity_id=target.node_id,
            entity_name=target.name,
            entity_type=target.entity_type,
            file_path=target.relative_path or target.file_path or "",
            tier=0,
            candidate_map=candidate_map,
        )

        # 2. Tier 1 & Tier 2 Discovery across Blast Radius
        for bnode in blast_radius.impacted_nodes:
            tier = 1 if bnode.depth == 1 else 2
            self._discover_tests_for_entity(
                entity_id=bnode.node_id,
                entity_name=bnode.name,
                entity_type=bnode.entity_type,
                file_path=bnode.file_path or "",
                tier=tier,
                candidate_map=candidate_map,
            )

        # 3. Sort and Rank Recommendations
        recommendations = list(candidate_map.values())
        recommendations.sort(key=lambda r: (r.tier, -r.rank_score, r.test_file))

        tier_breakdown: Dict[int, int] = {}
        evidence_breakdown: Dict[str, int] = {}
        for r in recommendations:
            tier_breakdown[r.tier] = tier_breakdown.get(r.tier, 0) + 1
            evidence_breakdown[r.evidence_type] = evidence_breakdown.get(r.evidence_type, 0) + 1

        return TestIntelligenceReport(
            target=target,
            total_tests=len(recommendations),
            recommendations=recommendations,
            tier_breakdown=tier_breakdown,
            evidence_breakdown=evidence_breakdown,
        )

    def _discover_tests_for_entity(
        self,
        entity_id: str,
        entity_name: str,
        entity_type: str,
        file_path: str,
        tier: int,
        candidate_map: Dict[Tuple[str, str], TestRecommendation],
    ) -> None:
        """Evaluate all evidence strategies for a single source entity."""
        norm_source_file = file_path.replace("\\", "/").strip("/")

        # Strategy A: DIRECT_INVOCATION (Test function calls entity)
        for pred in self.graph.predecessors(entity_id):
            edge_data = self.graph.get_edge_data(pred, entity_id) or {}
            if edge_data.get("edge_type") == EdgeType.CALLS:
                pred_data = self.graph.nodes[pred]
                if self._is_test_entity(pred, pred_data):
                    test_file = (pred_data.get("relative_path") or pred_data.get("file_path") or "").replace("\\", "/")
                    self._add_or_update_recommendation(
                        test_file=test_file,
                        test_target=pred_data.get("name", pred),
                        evidence_type=TestEvidenceType.DIRECT_INVOCATION.value,
                        tier=tier,
                        source_id=entity_id,
                        source_file=norm_source_file,
                        desc=f"Test directly invokes '{entity_name}' via AST call edge.",
                        candidate_map=candidate_map,
                    )

        # Strategy B: DIRECT_IMPORT (Test file imports source file)
        target_file_node = self._resolve_file_node_id(entity_id, norm_source_file)
        if target_file_node and target_file_node in self.graph:
            for pred in self.graph.predecessors(target_file_node):
                edge_data = self.graph.get_edge_data(pred, target_file_node) or {}
                if edge_data.get("edge_type") == EdgeType.IMPORTS:
                    pred_data = self.graph.nodes[pred]
                    if self._is_test_entity(pred, pred_data):
                        test_file = (pred_data.get("relative_path") or pred_data.get("file_path") or "").replace("\\", "/")
                        self._add_or_update_recommendation(
                            test_file=test_file,
                            test_target=pred_data.get("name", pred),
                            evidence_type=TestEvidenceType.DIRECT_IMPORT.value,
                            tier=tier,
                            source_id=entity_id,
                            source_file=norm_source_file,
                            desc=f"Test file directly imports '{norm_source_file}'.",
                            candidate_map=candidate_map,
                        )

        # Strategy C: HEURISTIC_NAMING (test_function name matches entity_name)
        if entity_name:
            norm_name = entity_name.lower()
            for t_node, t_data in self.test_nodes:
                t_name = (t_data.get("name") or "").lower()
                # Check for test_<name>, <name>_test, test_<name>_
                if (
                    t_name == f"test_{norm_name}" or
                    t_name == f"{norm_name}_test" or
                    t_name.startswith(f"test_{norm_name}_") or
                    t_name == f"test{norm_name}"
                ):
                    test_file = (t_data.get("relative_path") or t_data.get("file_path") or "").replace("\\", "/")
                    self._add_or_update_recommendation(
                        test_file=test_file,
                        test_target=t_data.get("name", t_node),
                        evidence_type=TestEvidenceType.HEURISTIC_NAMING.value,
                        tier=tier,
                        source_id=entity_id,
                        source_file=norm_source_file,
                        desc=f"Test symbol name matches entity name '{entity_name}'.",
                        candidate_map=candidate_map,
                    )

        # Strategy D: HEURISTIC_MIRRORING (Test file mirrors source path)
        if norm_source_file:
            mirror_candidates = self._find_mirror_test_files(norm_source_file)
            for m_file, m_target in mirror_candidates:
                self._add_or_update_recommendation(
                    test_file=m_file,
                    test_target=m_target,
                    evidence_type=TestEvidenceType.HEURISTIC_MIRRORING.value,
                    tier=tier,
                    source_id=entity_id,
                    source_file=norm_source_file,
                    desc=f"Test file mirrors source file '{norm_source_file}'.",
                    candidate_map=candidate_map,
                )

        # Strategy E: HEURISTIC_CO_CHANGE (Test file co-commits with source file)
        if norm_source_file and self.coupling_analyzer:
            co_changes = self._find_co_changing_tests(norm_source_file)
            for t_file, jaccard in co_changes:
                self._add_or_update_recommendation(
                    test_file=t_file,
                    test_target=t_file,
                    evidence_type=TestEvidenceType.HEURISTIC_CO_CHANGE.value,
                    tier=tier,
                    source_id=entity_id,
                    source_file=norm_source_file,
                    coupling_jaccard=jaccard,
                    desc=f"Test file historically co-commits with '{norm_source_file}' (Jaccard={jaccard:.2f}).",
                    candidate_map=candidate_map,
                )

    def _add_or_update_recommendation(
        self,
        test_file: str,
        test_target: str,
        evidence_type: str,
        tier: int,
        source_id: str,
        source_file: str,
        desc: str,
        candidate_map: Dict[Tuple[str, str], TestRecommendation],
        coupling_jaccard: float = 0.0,
    ) -> None:
        """Compute ranking score and update candidate map with best tier/evidence."""
        if not test_file:
            return

        key = (test_file, test_target)
        base_ev_weight = self.EVIDENCE_WEIGHTS.get(evidence_type, 0.40)

        # Ranking formula: EvidenceWeight / (1.0 + Tier) + lambda * Coupling
        rank_score = (base_ev_weight / (1.0 + tier)) + (self.config.coupling_lambda * coupling_jaccard)
        rank_score = round(min(1.0, max(0.0, rank_score)), 4)

        if key in candidate_map:
            existing = candidate_map[key]
            # If new match is in a closer tier or has higher rank score, upgrade it
            if tier < existing.tier or (tier == existing.tier and rank_score > existing.rank_score):
                candidate_map[key] = TestRecommendation(
                    test_file=test_file,
                    test_target=test_target,
                    evidence_type=evidence_type,
                    tier=tier,
                    rank_score=rank_score,
                    associated_source_entity=source_id,
                    description=desc,
                )
            elif rank_score == existing.rank_score and tier == existing.tier:
                # Add evidence reinforcement boost (+0.05) if multiple evidence types match
                existing.rank_score = round(min(1.0, existing.rank_score + 0.05), 4)
        else:
            candidate_map[key] = TestRecommendation(
                test_file=test_file,
                test_target=test_target,
                evidence_type=evidence_type,
                tier=tier,
                rank_score=rank_score,
                associated_source_entity=source_id,
                description=desc,
            )

    def _is_test_entity(self, node_id: str, data: Dict[str, Any]) -> bool:
        """Determine if a graph node represents a test file, class, or function."""
        name = (data.get("name") or "").lower()
        file_path = (data.get("relative_path") or data.get("file_path") or "").lower().replace("\\", "/")
        node_id_lower = str(node_id).lower()

        # Check path patterns
        is_in_tests_dir = "tests/" in file_path or file_path.startswith("tests") or "test/" in file_path
        is_test_file = file_path.endswith("_test.py") or "/test_" in file_path or file_path.startswith("test_")

        # Check symbol names
        is_test_symbol = name.startswith("test_") or name.endswith("_test") or name.startswith("test")

        return is_in_tests_dir or is_test_file or is_test_symbol or "test" in node_id_lower

    def _resolve_file_node_id(self, entity_id: str, file_path: str) -> Optional[str]:
        """Resolve file node ID for an entity."""
        if file_path:
            norm = file_path.replace("\\", "/").strip("/")
            fid = f"file:{norm}"
            if fid in self.graph:
                return fid
        # Fallback to checking predecessors of entity
        for pred in self.graph.predecessors(entity_id):
            if self.graph.nodes[pred].get("node_type") == NodeType.FILE:
                return pred
        return None

    def _find_mirror_test_files(self, source_path: str) -> List[Tuple[str, str]]:
        """
        Locate test files mirroring the source path.
        e.g., 'codemind/auth.py' -> 'tests/test_auth.py'
        """
        base_name = os.path.basename(source_path)
        stem, _ = os.path.splitext(base_name)
        mirror_patterns = [
            f"test_{stem}.py",
            f"{stem}_test.py",
        ]

        matches = []
        for t_node, t_data in self.test_nodes:
            if t_data.get("node_type") == NodeType.FILE:
                t_path = (t_data.get("relative_path") or t_data.get("file_path") or "").replace("\\", "/")
                t_base = os.path.basename(t_path)
                if t_base in mirror_patterns:
                    matches.append((t_path, t_data.get("name", t_base)))
        return matches

    def _find_co_changing_tests(self, source_path: str) -> List[Tuple[str, float]]:
        """Query logical coupling analyzer for test files co-committed with source_path."""
        matches = []
        couplings = getattr(self.coupling_analyzer, "couplings", [])
        if not isinstance(source_path, str) or not isinstance(couplings, (list, tuple, set)):
            return matches

        norm_source = source_path.replace("\\", "/").strip("/").lower()
        while norm_source.startswith("./"):
            norm_source = norm_source[2:]

        for c in couplings:
            raw_a = getattr(c, "canonical_file_a", None)
            if not isinstance(raw_a, str):
                raw_a = getattr(c, "file_a", "")
            raw_b = getattr(c, "canonical_file_b", None)
            if not isinstance(raw_b, str):
                raw_b = getattr(c, "file_b", "")

            file_a = raw_a.replace("\\", "/").strip("/").lower() if isinstance(raw_a, str) else ""
            file_b = raw_b.replace("\\", "/").strip("/").lower() if isinstance(raw_b, str) else ""
            while file_a.startswith("./"):
                file_a = file_a[2:]
            while file_b.startswith("./"):
                file_b = file_b[2:]
            jaccard = getattr(c, "jaccard_similarity", 0.0)
            if not isinstance(jaccard, (int, float)):
                jaccard = 0.0

            if norm_source in (file_a, file_b) and jaccard >= 0.15:
                other_file = file_b if norm_source == file_a else file_a
                if "test" in other_file.lower():
                    matches.append((other_file, float(jaccard)))
        return matches
