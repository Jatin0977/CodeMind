"""
Software Knowledge Graph Builder.
Constructs a NetworkX directed graph from IngestedRepository and ParsedFile AST data.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Set
import networkx as nx

from ..ingestion.models import IngestedRepository, SourceFile
from ..parsing.base_parser import ParsedFile, Symbol, ImportStatement
from .models import NodeType, EdgeType, Node, Edge, GraphSummary


class KnowledgeGraphBuilder:
    """
    Constructs a deterministic, multi-relational directed software knowledge graph.
    Extracts typed nodes (files, classes, functions, methods) and edges
    (CONTAINS, CALLS, IMPORTS, INHERITS) using existing Phase 1 & 2 AST structures.
    """

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self.nodes_by_id: Dict[str, Node] = {}
        self.edges_list: List[Edge] = []

    def build(
        self,
        repo: IngestedRepository,
        parsed_files: Dict[str, ParsedFile],
    ) -> nx.DiGraph:
        """
        Build the software knowledge graph.

        Args:
            repo: Ingested repository model.
            parsed_files: Dictionary of relative_path -> ParsedFile.

        Returns:
            Configured networkx.DiGraph instance.
        """
        self.graph.clear()
        self.nodes_by_id.clear()
        self.edges_list.clear()

        # Step 1: Create all entity nodes and CONTAINS hierarchy edges
        self._create_nodes_and_contains_edges(repo, parsed_files)

        # Step 2: Build resolution indices
        resolution_indexes = self._build_resolution_indexes(repo, parsed_files)

        # Step 3: Resolve and create IMPORTS edges
        self._create_imports_edges(parsed_files, resolution_indexes)

        # Step 4: Resolve and create INHERITS edges
        self._create_inherits_edges(parsed_files, resolution_indexes)

        # Step 5: Resolve and create CALLS edges
        self._create_calls_edges(parsed_files, resolution_indexes)

        return self.graph

    def _create_nodes_and_contains_edges(
        self,
        repo: IngestedRepository,
        parsed_files: Dict[str, ParsedFile],
    ):
        """Create file, class, function, and method nodes and link them via CONTAINS edges."""
        for sf in repo.files:
            rel_path = sf.relative_path.replace("\\", "/")
            file_id = f"file:{rel_path}"

            file_node = Node(
                id=file_id,
                name=sf.file_name,
                node_type=NodeType.FILE,
                file_path=sf.file_path,
                relative_path=rel_path,
                start_line=1,
                end_line=sf.line_count,
                language=sf.language,
                metadata={
                    "line_count": sf.line_count,
                    "file_size": sf.file_size,
                    "is_python": sf.is_python,
                    "is_doc": sf.is_documentation,
                },
            )
            self._add_node(file_node)

            parsed = parsed_files.get(rel_path)
            if not parsed or not parsed.is_valid:
                continue

            # Classes and methods
            for cls_sym in parsed.classes:
                class_id = f"class:{rel_path}:{cls_sym.name}"
                class_node = Node(
                    id=class_id,
                    name=cls_sym.name,
                    node_type=NodeType.CLASS,
                    file_path=sf.file_path,
                    relative_path=rel_path,
                    start_line=cls_sym.start_line,
                    end_line=cls_sym.end_line,
                    language=sf.language,
                    metadata={
                        "docstring": cls_sym.docstring,
                        "bases": cls_sym.bases,
                        "decorators": cls_sym.decorators,
                        "methods_count": len(cls_sym.methods),
                    },
                )
                self._add_node(class_node)
                self._add_edge(file_id, class_id, EdgeType.CONTAINS)

                for meth_sym in cls_sym.methods:
                    method_id = f"method:{rel_path}:{cls_sym.name}.{meth_sym.name}"
                    method_node = Node(
                        id=method_id,
                        name=f"{cls_sym.name}.{meth_sym.name}",
                        node_type=NodeType.METHOD,
                        file_path=sf.file_path,
                        relative_path=rel_path,
                        start_line=meth_sym.start_line,
                        end_line=meth_sym.end_line,
                        language=sf.language,
                        metadata={
                            "docstring": meth_sym.docstring,
                            "args": meth_sym.args,
                            "returns": meth_sym.returns,
                            "decorators": meth_sym.decorators,
                            "is_async": meth_sym.is_async,
                            "calls": meth_sym.calls,
                            "parent_class": cls_sym.name,
                        },
                    )
                    self._add_node(method_node)
                    self._add_edge(class_id, method_id, EdgeType.CONTAINS)

            # Top-level Functions
            for func_sym in parsed.functions:
                func_id = f"function:{rel_path}:{func_sym.name}"
                func_node = Node(
                    id=func_id,
                    name=func_sym.name,
                    node_type=NodeType.FUNCTION,
                    file_path=sf.file_path,
                    relative_path=rel_path,
                    start_line=func_sym.start_line,
                    end_line=func_sym.end_line,
                    language=sf.language,
                    metadata={
                        "docstring": func_sym.docstring,
                        "args": func_sym.args,
                        "returns": func_sym.returns,
                        "decorators": func_sym.decorators,
                        "is_async": func_sym.is_async,
                        "calls": func_sym.calls,
                    },
                )
                self._add_node(func_node)
                self._add_edge(file_id, func_id, EdgeType.CONTAINS)

    def _build_resolution_indexes(
        self,
        repo: IngestedRepository,
        parsed_files: Dict[str, ParsedFile],
    ) -> Dict[str, Any]:
        """Build dictionary indexes for fast symbol and module resolution."""
        # 1. Module path -> relative_path
        module_to_file: Dict[str, str] = {}
        for sf in repo.files:
            rel = sf.relative_path.replace("\\", "/")
            if rel.endswith(".py"):
                # e.g. codemind/ingestion/models.py -> codemind.ingestion.models
                without_ext = rel[:-3]
                dot_mod = without_ext.replace("/", ".")
                module_to_file[dot_mod] = rel

                # Also support relative without root package prefix (e.g. ingestion.models)
                parts = dot_mod.split(".")
                for i in range(1, len(parts)):
                    sub_mod = ".".join(parts[i:])
                    if sub_mod not in module_to_file:
                        module_to_file[sub_mod] = rel

                if rel.endswith("__init__.py"):
                    parent_pkg = rel[:-12].rstrip("/").replace("/", ".")
                    if parent_pkg:
                        module_to_file[parent_pkg] = rel

        # 2. Symbol name -> list of node IDs
        classes_by_name: Dict[str, List[str]] = {}
        functions_by_name: Dict[str, List[str]] = {}
        methods_by_qualified: Dict[str, str] = {}  # "Class.method" -> method_id
        methods_by_name: Dict[str, List[str]] = {}   # "method" -> [method_ids]

        # 3. Local symbols in each file: file_rel -> {name: node_id}
        local_symbols_by_file: Dict[str, Dict[str, str]] = {}

        for node_id, node in self.nodes_by_id.items():
            rel = node.relative_path
            if not rel:
                continue
            if rel not in local_symbols_by_file:
                local_symbols_by_file[rel] = {}

            if node.node_type == NodeType.CLASS:
                classes_by_name.setdefault(node.name, []).append(node_id)
                local_symbols_by_file[rel][node.name] = node_id
            elif node.node_type == NodeType.FUNCTION:
                functions_by_name.setdefault(node.name, []).append(node_id)
                local_symbols_by_file[rel][node.name] = node_id
            elif node.node_type == NodeType.METHOD:
                methods_by_qualified[node.name] = node_id
                simple_name = node.name.split(".")[-1]
                methods_by_name.setdefault(simple_name, []).append(node_id)
                local_symbols_by_file[rel][node.name] = node_id
                local_symbols_by_file[rel][simple_name] = node_id

        # 4. Explicit imports in each file: file_rel -> {imported_symbol: target_node_id}
        explicit_imports_by_file: Dict[str, Dict[str, str]] = {}
        for rel, pf in parsed_files.items():
            rel_norm = rel.replace("\\", "/")
            explicit_imports_by_file[rel_norm] = {}
            if not pf.is_valid:
                continue

            for imp in pf.imports:
                target_file_rel = self._resolve_import_target_file(imp, rel_norm, module_to_file)
                if not target_file_rel:
                    continue

                imported_symbol_name = imp.alias or imp.name
                # Check if target_file exports this symbol
                target_locals = local_symbols_by_file.get(target_file_rel, {})
                if imp.name in target_locals:
                    explicit_imports_by_file[rel_norm][imported_symbol_name] = target_locals[imp.name]

        return {
            "module_to_file": module_to_file,
            "classes_by_name": classes_by_name,
            "functions_by_name": functions_by_name,
            "methods_by_qualified": methods_by_qualified,
            "methods_by_name": methods_by_name,
            "local_symbols_by_file": local_symbols_by_file,
            "explicit_imports_by_file": explicit_imports_by_file,
        }

    def _resolve_import_target_file(
        self,
        imp: ImportStatement,
        current_file_rel: str,
        module_to_file: Dict[str, str],
    ) -> Optional[str]:
        """Resolve an import statement to a target file relative path."""
        module_str = imp.module or ""

        # Handle relative imports: from .foo import bar, from ..baz import qux
        if module_str.startswith("."):
            dots_count = 0
            while dots_count < len(module_str) and module_str[dots_count] == ".":
                dots_count += 1
            rel_sub = module_str[dots_count:]

            curr_dir = Path(current_file_rel).parent
            # Move up (dots_count - 1) levels for relative import
            target_dir = curr_dir
            for _ in range(dots_count - 1):
                target_dir = target_dir.parent

            # Candidate path
            if rel_sub:
                candidate_rel = str(target_dir / rel_sub.replace(".", "/")).replace("\\", "/")
            else:
                candidate_rel = str(target_dir).replace("\\", "/")

            # Check if candidates exist as .py or __init__.py
            for ext in [".py", "/__init__.py"]:
                test_path = candidate_rel + ext if not candidate_rel.endswith(".py") else candidate_rel
                if test_path in self.nodes_by_id or f"file:{test_path}" in self.nodes_by_id:
                    return test_path
            # Also check if imp.name is a file in target_dir (e.g. from . import repo_loader)
            if not rel_sub:
                candidate_file = str(target_dir / (imp.name + ".py")).replace("\\", "/")
                if f"file:{candidate_file}" in self.nodes_by_id:
                    return candidate_file

        # Check standard module_to_file mapping
        if module_str and module_str in module_to_file:
            return module_to_file[module_str]

        # Maybe from foo.bar import Baz where foo.bar.Baz is a file
        full_candidate = f"{module_str}.{imp.name}".strip(".")
        if full_candidate in module_to_file:
            return module_to_file[full_candidate]

        # Plain import foo.bar
        if not imp.is_from and imp.name in module_to_file:
            return module_to_file[imp.name]

        return None

    def _create_imports_edges(
        self,
        parsed_files: Dict[str, ParsedFile],
        indexes: Dict[str, Any],
    ):
        """Create IMPORTS edges between source files."""
        module_to_file = indexes["module_to_file"]

        for rel, pf in parsed_files.items():
            rel_norm = rel.replace("\\", "/")
            src_file_id = f"file:{rel_norm}"
            if src_file_id not in self.nodes_by_id:
                continue

            for imp in pf.imports:
                target_file_rel = self._resolve_import_target_file(imp, rel_norm, module_to_file)
                if target_file_rel:
                    tgt_file_id = f"file:{target_file_rel}"
                    if tgt_file_id in self.nodes_by_id and tgt_file_id != src_file_id:
                        self._add_edge(
                            src_file_id,
                            tgt_file_id,
                            EdgeType.IMPORTS,
                            {"line_number": imp.line_number, "import_stmt": str(imp)},
                        )

    def _create_inherits_edges(
        self,
        parsed_files: Dict[str, ParsedFile],
        indexes: Dict[str, Any],
    ):
        """Create INHERITS edges between classes and their base classes."""
        classes_by_name = indexes["classes_by_name"]
        local_symbols = indexes["local_symbols_by_file"]
        explicit_imports = indexes["explicit_imports_by_file"]

        for rel, pf in parsed_files.items():
            rel_norm = rel.replace("\\", "/")
            if not pf.is_valid:
                continue

            for cls_sym in pf.classes:
                class_id = f"class:{rel_norm}:{cls_sym.name}"
                if class_id not in self.nodes_by_id:
                    continue

                for base_raw in cls_sym.bases:
                    # Clean base class name (strip module prefix if present e.g. BaseParser or base.BaseParser)
                    base_name = base_raw.split(".")[-1]
                    target_id = None

                    # 1. Local symbol in current file
                    if base_name in local_symbols.get(rel_norm, {}):
                        cand = local_symbols[rel_norm][base_name]
                        if cand.startswith("class:"):
                            target_id = cand

                    # 2. Explicitly imported in current file
                    if not target_id and base_name in explicit_imports.get(rel_norm, {}):
                        cand = explicit_imports[rel_norm][base_name]
                        if cand.startswith("class:"):
                            target_id = cand

                    # 3. Unique global class name match in codebase
                    if not target_id and base_name in classes_by_name:
                        candidates = classes_by_name[base_name]
                        if len(candidates) == 1:
                            target_id = candidates[0]

                    if target_id and target_id in self.nodes_by_id and target_id != class_id:
                        self._add_edge(class_id, target_id, EdgeType.INHERITS, {"base": base_raw})

    def _create_calls_edges(
        self,
        parsed_files: Dict[str, ParsedFile],
        indexes: Dict[str, Any],
    ):
        """Create CALLS edges between callers (functions/methods) and callees."""
        classes_by_name = indexes["classes_by_name"]
        functions_by_name = indexes["functions_by_name"]
        methods_by_qualified = indexes["methods_by_qualified"]
        methods_by_name = indexes["methods_by_name"]
        local_symbols = indexes["local_symbols_by_file"]
        explicit_imports = indexes["explicit_imports_by_file"]

        for rel, pf in parsed_files.items():
            rel_norm = rel.replace("\\", "/")
            if not pf.is_valid:
                continue

            # Gather all callable callers in file: functions + class methods
            callers: List[Tuple[str, Optional[str], List[str]]] = []  # (caller_id, parent_class, calls)
            for f in pf.functions:
                callers.append((f"function:{rel_norm}:{f.name}", None, f.calls))

            for c in pf.classes:
                for m in c.methods:
                    callers.append((f"method:{rel_norm}:{c.name}.{m.name}", c.name, m.calls))

            for caller_id, parent_cls, calls in callers:
                if caller_id not in self.nodes_by_id:
                    continue

                for call_str in calls:
                    target_id = self._resolve_call(
                        call_str=call_str,
                        caller_file=rel_norm,
                        parent_class=parent_cls,
                        local_symbols=local_symbols,
                        explicit_imports=explicit_imports,
                        classes_by_name=classes_by_name,
                        functions_by_name=functions_by_name,
                        methods_by_qualified=methods_by_qualified,
                        methods_by_name=methods_by_name,
                    )

                    if target_id and target_id in self.nodes_by_id and target_id != caller_id:
                        self._add_edge(caller_id, target_id, EdgeType.CALLS, {"call_expr": call_str})

    def _resolve_call(
        self,
        call_str: str,
        caller_file: str,
        parent_class: Optional[str],
        local_symbols: Dict[str, Dict[str, str]],
        explicit_imports: Dict[str, Dict[str, str]],
        classes_by_name: Dict[str, List[str]],
        functions_by_name: Dict[str, List[str]],
        methods_by_qualified: Dict[str, str],
        methods_by_name: Dict[str, List[str]],
    ) -> Optional[str]:
        """Deterministically resolve a function or method invocation string to a Node ID."""
        cleaned = call_str.strip()
        if not cleaned:
            return None

        # Case 1: self.method(...) or cls.method(...)
        if (cleaned.startswith("self.") or cleaned.startswith("cls.")) and parent_class:
            meth_name = cleaned.split(".")[1].split("(")[0]
            # Check current class methods
            qual = f"{parent_class}.{meth_name}"
            target_method_id = f"method:{caller_file}:{qual}"
            if target_method_id in self.nodes_by_id:
                return target_method_id

            # Check if any base class defines this method
            parent_class_id = f"class:{caller_file}:{parent_class}"
            if parent_class_id in self.graph:
                for succ in self.graph.successors(parent_class_id):
                    edge_data = self.graph.get_edge_data(parent_class_id, succ)
                    if edge_data and edge_data.get("edge_type") == EdgeType.INHERITS:
                        base_node = self.nodes_by_id.get(succ)
                        if base_node:
                            base_qual = f"{base_node.name}.{meth_name}"
                            base_meth_id = f"method:{base_node.relative_path}:{base_qual}"
                            if base_meth_id in self.nodes_by_id:
                                return base_meth_id
            return None

        # Strip arguments if formatted as func(...)
        simple_id = cleaned.split("(")[0].strip()

        # Case 2: Simple name (func or Class)
        if "." not in simple_id:
            # A. Local symbol in current file
            if simple_id in local_symbols.get(caller_file, {}):
                cand = local_symbols[caller_file][simple_id]
                # If it's a class constructor call, target the class node
                return cand

            # B. Explicitly imported symbol in current file
            if simple_id in explicit_imports.get(caller_file, {}):
                return explicit_imports[caller_file][simple_id]

            # C. Unique top-level function in codebase
            if simple_id in functions_by_name:
                cands = functions_by_name[simple_id]
                if len(cands) == 1:
                    return cands[0]

            # D. Unique class constructor in codebase
            if simple_id in classes_by_name:
                cands = classes_by_name[simple_id]
                if len(cands) == 1:
                    return cands[0]

            return None

        # Case 3: Qualified name (Class.method or module.func)
        parts = simple_id.split(".")
        if len(parts) == 2:
            qual_name = f"{parts[0]}.{parts[1]}"
            if qual_name in methods_by_qualified:
                return methods_by_qualified[qual_name]

            # e.g. loader.load_repository -> if method_name is unique
            meth_name = parts[1]
            if meth_name in methods_by_name:
                cands = methods_by_name[meth_name]
                if len(cands) == 1:
                    return cands[0]

        return None

    def _add_node(self, node: Node):
        """Add a Node instance to internal graph and lookup table."""
        self.nodes_by_id[node.id] = node
        self.graph.add_node(node.id, **node.to_dict())

    def _add_edge(self, source_id: str, target_id: str, edge_type: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a directed Edge between source_id and target_id with edge_type."""
        meta = metadata or {}
        edge = Edge(source=source_id, target=target_id, edge_type=edge_type, metadata=meta)
        self.edges_list.append(edge)
        self.graph.add_edge(source_id, target_id, edge_type=edge_type, metadata=meta)

    def get_summary(self) -> GraphSummary:
        """Compute structural metrics and cycle breakdown."""
        node_counts: Dict[str, int] = {}
        for n in self.nodes_by_id.values():
            node_counts[n.node_type] = node_counts.get(n.node_type, 0) + 1

        edge_counts: Dict[str, int] = {}
        for e in self.edges_list:
            edge_counts[e.edge_type] = edge_counts.get(e.edge_type, 0) + 1

        # Check for circular dependencies (cycles) on IMPORTS and CALLS edges
        cycles: List[List[str]] = []
        try:
            # Subgraph of dependency edges (IMPORTS, CALLS)
            dep_edges = [
                (u, v) for u, v, d in self.graph.edges(data=True)
                if d.get("edge_type") in (EdgeType.IMPORTS, EdgeType.CALLS)
            ]
            dep_subgraph = self.graph.edge_subgraph(dep_edges)
            for c in nx.simple_cycles(dep_subgraph):
                cycles.append(c)
                if len(cycles) >= 10:  # Truncate to top 10
                    break
        except Exception:
            pass

        return GraphSummary(
            total_nodes=len(self.nodes_by_id),
            total_edges=len(self.edges_list),
            node_type_counts=node_counts,
            edge_type_counts=edge_counts,
            has_cycles=len(cycles) > 0,
            cycle_count=len(cycles),
            cycles=cycles,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert graph to complete JSON-serializable dictionary."""
        summary = self.get_summary()
        return {
            "summary": summary.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes_by_id.values()],
            "edges": [e.to_dict() for e in self.edges_list],
        }
