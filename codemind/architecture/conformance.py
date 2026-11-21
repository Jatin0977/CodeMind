"""
Architecture Conformance & Dependency Rule Engine for CodeMind (Phase 9, Milestone 2).
Validates cross-module file imports against configured and heuristic layer rules,
detects upward layer leaks, forbidden imports, and strict layer-skipping violations,
and implements deterministic package-level cycle detection using Tarjan's SCC on G_M.
"""

import logging
from typing import List, Dict, Optional, Set, Tuple, Any

import networkx as nx

from .models import (
    ViolationSeverity,
    LayerDefinition,
    ModuleEntity,
    ConformanceViolation,
    ConformanceReport,
)
from ..parsing.base_parser import ParsedFile, ImportStatement

logger = logging.getLogger(__name__)


class ArchitectureConformanceEngine:
    """
    Evaluates repository dependencies against architectural layer definitions,
    calculates the Architecture Conformance Index (ACI), and detects package-level cycles.
    """

    def __init__(
        self,
        layers: Optional[Dict[str, LayerDefinition]] = None,
        modules_map: Optional[Dict[str, ModuleEntity]] = None,
        quotient_graph: Optional[nx.DiGraph] = None,
    ):
        self.layers: Dict[str, LayerDefinition] = layers or {}
        self.modules_map: Dict[str, ModuleEntity] = modules_map or {}
        self.quotient_graph: nx.DiGraph = quotient_graph if quotient_graph is not None else nx.DiGraph()

        # Manual / test import statements tracked as:
        # edge_key (source_file, target_file) -> list of (line_number, raw_statement)
        self._manual_imports: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}
        # Explicit file-to-module overrides
        self._file_to_module: Dict[str, str] = {}

    def register_layer(
        self,
        name: str,
        level: int,
        modules: Optional[List[str]] = None,
        allowed: Optional[List[str]] = None,
        forbidden: Optional[List[str]] = None,
    ) -> LayerDefinition:
        """Register or update an architectural layer definition."""
        layer = LayerDefinition(
            name=name,
            level=level,
            modules=list(modules or []),
            allowed_dependencies=list(allowed or []),
            forbidden_dependencies=list(forbidden or []),
        )
        self.layers[name] = layer
        return layer

    def register_file_module(self, file_path: str, module_name: str) -> None:
        """Manually map a relative file path to its parent module name."""
        norm_file = file_path.replace("\\", "/")
        self._file_to_module[norm_file] = module_name

    def add_import(
        self,
        source_file: str,
        target_file: str,
        line_number: int = 1,
        statement: Optional[str] = None,
        line: Optional[int] = None,
    ) -> None:
        """
        Manually record a cross-file import statement (used for testing or direct ingestion).
        Automatically derives module identities and updates internal tracking.
        """
        actual_line = line if line is not None else line_number
        src = source_file.replace("\\", "/")
        tgt = target_file.replace("\\", "/")
        edge_key = (src, tgt)

        if edge_key not in self._manual_imports:
            self._manual_imports[edge_key] = []

        stmt = statement or f"import {tgt}"
        self._manual_imports[edge_key].append((actual_line, stmt))

        # Infer modules if not explicitly registered
        src_mod = self._get_module_for_file(src)
        tgt_mod = self._get_module_for_file(tgt)

        # Update quotient graph for cycle tracking if cross-module
        if src_mod != tgt_mod:
            if not self.quotient_graph.has_node(src_mod):
                self.quotient_graph.add_node(src_mod)
            if not self.quotient_graph.has_node(tgt_mod):
                self.quotient_graph.add_node(tgt_mod)

            current_weight = self.quotient_graph.get_edge_data(src_mod, tgt_mod, {}).get("weight", 0)
            self.quotient_graph.add_edge(src_mod, tgt_mod, weight=current_weight + 1)

    def _get_module_for_file(self, file_path: str) -> str:
        """Derives or looks up the module name for a file path."""
        norm_path = file_path.replace("\\", "/")
        if norm_path in self._file_to_module:
            return self._file_to_module[norm_path]

        # Check existing modules_map
        for mod_name, mod in self.modules_map.items():
            if norm_path in mod.files:
                return mod_name

        # Derivation fallback: folder dot-path or __root__
        parts = norm_path.split("/")
        if len(parts) == 1:
            return "__root__"
        return ".".join(parts[:-1])

    def _get_layer_for_module(self, module_name: str) -> Optional[LayerDefinition]:
        """Looks up the LayerDefinition containing the module, or None if unclassified."""
        # Check explicit layers
        for layer in self.layers.values():
            if module_name in layer.modules:
                return layer
            if any(module_name.startswith(f"{m}.") for m in layer.modules):
                return layer

        # Check modules_map inferred layer
        if module_name in self.modules_map:
            inferred = self.modules_map[module_name].inferred_layer
            if inferred in self.layers:
                return self.layers[inferred]

        return None

    def evaluate(
        self,
        parsed_files: Optional[Dict[str, ParsedFile]] = None,
        total_eval_imports: Optional[int] = None,
        strict_layering: bool = False,
    ) -> ConformanceReport:
        """
        Evaluate all cross-module directed file edges against layer rules,
        calculate the Architecture Conformance Index (ACI), and detect package cycles.
        """
        # Ensure default layers exist if none were explicitly configured
        self._ensure_default_layers()

        # 1. Collect all directed cross-module file edges and their import statements
        file_edges: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}

        # Merge manual imports
        for edge_key, stmts in self._manual_imports.items():
            file_edges[edge_key] = list(stmts)

        # Merge parsed_files imports if provided
        if parsed_files:
            for rel_path, parsed in parsed_files.items():
                src_path = rel_path.replace("\\", "/")
                src_mod = self._get_module_for_file(src_path)

                for imp in parsed.imports:
                    # Attempt to resolve import target
                    target_file = self._resolve_parsed_import_target(imp, src_path)
                    if target_file:
                        tgt_path = target_file.replace("\\", "/")
                        edge_key = (src_path, tgt_path)
                        if edge_key not in file_edges:
                            file_edges[edge_key] = []
                        file_edges[edge_key].append((imp.line_number, str(imp)))

        # 2. Filter to eligible cross-module file edges between classified modules
        evaluated_edges: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}
        for (src_file, tgt_file), stmts in file_edges.items():
            if src_file == tgt_file:
                # File-level self-loop, skip
                continue

            src_mod = self._get_module_for_file(src_file)
            tgt_mod = self._get_module_for_file(tgt_file)

            if src_mod == tgt_mod:
                # Intra-module dependency, skip
                continue

            src_layer = self._get_layer_for_module(src_mod)
            tgt_layer = self._get_layer_for_module(tgt_mod)

            if not src_layer or not tgt_layer:
                # Unclassified module, skip from ACI calculation
                continue

            evaluated_edges[(src_file, tgt_file)] = stmts

        # Total unique evaluated directed cross-module file edges
        total_evaluated_edges = (
            total_eval_imports if total_eval_imports is not None else len(evaluated_edges)
        )

        # 3. Evaluate layer rules per file edge
        violations: List[ConformanceViolation] = []
        violating_edge_weights: Dict[Tuple[str, str], float] = {}

        for (src_file, tgt_file), stmts in evaluated_edges.items():
            src_mod = self._get_module_for_file(src_file)
            tgt_mod = self._get_module_for_file(tgt_file)
            src_layer = self._get_layer_for_module(src_mod)
            tgt_layer = self._get_layer_for_module(tgt_mod)

            if not src_layer or not tgt_layer:
                continue

            edge_rule_weights: List[float] = []

            for line_no, raw_stmt in stmts:
                # Rule A: Upward Layer Leak (Lower layer imports higher layer)
                if src_layer.level > tgt_layer.level:
                    v = ConformanceViolation(
                        violation_type="UPWARD_LAYER_LEAK",
                        severity=ViolationSeverity.CRITICAL,
                        source_file=src_file,
                        target_file=tgt_file,
                        source_module=src_mod,
                        target_module=tgt_mod,
                        source_layer=src_layer.name,
                        target_layer=tgt_layer.name,
                        line_number=line_no,
                        import_statement=raw_stmt,
                        rule_description=(
                            f"Upward layer leak: lower layer '{src_layer.name}' (level {src_layer.level}) "
                            f"imports higher layer '{tgt_layer.name}' (level {tgt_layer.level})"
                        ),
                        weight=1.0,
                    )
                    violations.append(v)
                    edge_rule_weights.append(1.0)

                # Rule B: Explicit Forbidden Import
                is_forbidden = (
                    tgt_layer.name in src_layer.forbidden_dependencies
                    or tgt_mod in src_layer.forbidden_dependencies
                )
                if not is_forbidden and src_layer.allowed_dependencies:
                    # Allowed list specified: any target not in allowed list is forbidden
                    if (
                        tgt_layer.name not in src_layer.allowed_dependencies
                        and tgt_mod not in src_layer.allowed_dependencies
                    ):
                        is_forbidden = True

                if is_forbidden:
                    v = ConformanceViolation(
                        violation_type="FORBIDDEN_IMPORT",
                        severity=ViolationSeverity.CRITICAL,
                        source_file=src_file,
                        target_file=tgt_file,
                        source_module=src_mod,
                        target_module=tgt_mod,
                        source_layer=src_layer.name,
                        target_layer=tgt_layer.name,
                        line_number=line_no,
                        import_statement=raw_stmt,
                        rule_description=(
                            f"Forbidden import: layer '{src_layer.name}' is prohibited "
                            f"from importing layer '{tgt_layer.name}'"
                        ),
                        weight=1.0,
                    )
                    violations.append(v)
                    edge_rule_weights.append(1.0)

                # Rule C: Strict Layer Skipping (Jump of > 1 layer across non-adjacent tiers)
                if strict_layering and abs(tgt_layer.level - src_layer.level) > 1:
                    v = ConformanceViolation(
                        violation_type="LAYER_SKIPPING",
                        severity=ViolationSeverity.WARNING,
                        source_file=src_file,
                        target_file=tgt_file,
                        source_module=src_mod,
                        target_module=tgt_mod,
                        source_layer=src_layer.name,
                        target_layer=tgt_layer.name,
                        line_number=line_no,
                        import_statement=raw_stmt,
                        rule_description=(
                            f"Strict layer skipping: layer '{src_layer.name}' (level {src_layer.level}) "
                            f"skips intermediate layers to import '{tgt_layer.name}' (level {tgt_layer.level})"
                        ),
                        weight=0.4,
                    )
                    violations.append(v)
                    edge_rule_weights.append(0.4)

            # Edge-level aggregation: edge takes MAXIMUM single rule weight
            if edge_rule_weights:
                violating_edge_weights[(src_file, tgt_file)] = max(edge_rule_weights)

        # 4. Conformance Index (ACI) Calculation
        conformance_numerator = sum(violating_edge_weights.values())
        if total_evaluated_edges == 0:
            conformance_index = 100.00
        else:
            ratio = min(1.0, conformance_numerator / total_evaluated_edges)
            conformance_index = round(100.0 * (1.0 - ratio), 2)

        # 5. Deterministic Package Cycle and SCC Detection on Quotient Graph
        package_cycles = self.detect_package_cycles()
        package_sccs = self.detect_package_sccs()

        return ConformanceReport(
            conformance_index=conformance_index,
            conformance_numerator=round(conformance_numerator, 4),
            total_evaluated_edges=total_evaluated_edges,
            violations=violations,
            violating_edges_count=len(violating_edge_weights),
            package_cycles=package_cycles,
            package_sccs=package_sccs,
        )

    def detect_package_sccs(self) -> List[List[str]]:
        """
        Detects non-trivial strongly connected components (size >= 2) on the module quotient graph G_M.
        Returns a deterministically sorted list of components, each member list sorted lexicographically.

        Note: An SCC represents a cluster of mutually reachable packages, whereas
        detect_package_cycles returns the actual valid directed cycle paths within each SCC.
        """
        if not self.quotient_graph or self.quotient_graph.number_of_nodes() < 2:
            return []

        sccs = [scc for scc in nx.strongly_connected_components(self.quotient_graph) if len(scc) >= 2]
        return sorted([sorted(list(scc)) for scc in sccs], key=lambda c: (len(c), c))

    def detect_package_cycles(self) -> List[List[str]]:
        """
        Detects circular dependencies between logical packages on the module quotient graph G_M.
        Uses Tarjan's SCC algorithm to locate non-trivial cyclic components, enumerates elementary
        directed cycles, applies canonical lexicographical rotation, and removes duplicate loops.
        Self-loops (intra-module imports) are excluded.

        Important Audit Invariant:
        SCC components are NOT naively represented as cycles by merely sorting their members
        (which would produce false non-existent cycles in non-simple SCCs like bow-tie or figure-8 graphs).
        Instead, genuine elementary directed cycles are enumerated from each SCC subgraph and
        canonically rotated to start at the lexicographically lowest node while strictly preserving
        the directed edge traversal sequence.
        """
        if not self.quotient_graph or self.quotient_graph.number_of_nodes() < 2:
            return []

        # Find non-trivial strongly connected components (size >= 2)
        sccs = [scc for scc in nx.strongly_connected_components(self.quotient_graph) if len(scc) >= 2]
        if not sccs:
            return []

        canonical_cycles: Set[Tuple[str, ...]] = set()

        for scc in sccs:
            scc_subgraph = self.quotient_graph.subgraph(scc)
            try:
                for cycle in nx.simple_cycles(scc_subgraph):
                    if len(cycle) < 2:
                        # Exclude self-loops
                        continue

                    # Canonical rotation: rotate so lexicographically smallest module name is at index 0
                    min_idx = min(range(len(cycle)), key=lambda i: cycle[i])
                    canonical_tuple = tuple(cycle[min_idx:] + cycle[:min_idx])
                    canonical_cycles.add(canonical_tuple)
            except Exception as e:
                logger.debug(f"Error enumerating simple cycles in SCC: {e}")

        # Deterministic sorting: by length then by node names
        sorted_cycles = sorted(
            [list(c) for c in canonical_cycles],
            key=lambda c: (len(c), c),
        )
        return sorted_cycles

    def _ensure_default_layers(self) -> None:
        """Initializes standard clean architecture layers if none were configured."""
        if not self.layers:
            self.register_layer("Presentation", level=1, allowed=["Domain", "Infrastructure", "Utilities"])
            self.register_layer("Domain", level=2, allowed=["Infrastructure", "Utilities"])
            self.register_layer("Infrastructure", level=3, allowed=["Utilities"])
            self.register_layer("Utilities", level=4, allowed=[])

    def _resolve_parsed_import_target(self, imp: ImportStatement, src_file: str) -> Optional[str]:
        """Resolves target relative file path for an ImportStatement."""
        module_str = imp.module or imp.name
        if not module_str:
            return None

        # Try relative import
        if imp.is_from and imp.module and imp.module.startswith("."):
            dots = len(imp.module) - len(imp.module.lstrip("."))
            src_parts = src_file.split("/")[:-1]
            if dots <= len(src_parts) + 1:
                base_dir = "/".join(src_parts[: len(src_parts) - (dots - 1)])
                sub_mod = imp.module.lstrip(".")
                candidate_rel = f"{base_dir}/{sub_mod}" if sub_mod else base_dir
                return f"{candidate_rel.replace('.', '/')}.py"

        # Check internal files in modules_map
        for mod in self.modules_map.values():
            for f in mod.files:
                f_mod = f.replace("/", ".").replace(".py", "")
                if f_mod == module_str or f_mod.endswith(f".{module_str}"):
                    return f

        return None
