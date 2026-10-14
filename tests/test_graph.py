"""
Unit tests for CodeMind Phase 4 Software Knowledge Graph:
Models, Builder, Query Engine, Cycle Detection, and Structural Impact Tracing.
"""

import unittest
from pathlib import Path
from codemind.ingestion.models import IngestedRepository, SourceFile, IngestionSummary
from codemind.parsing.python_parser import PythonParser
from codemind.graph.models import NodeType, EdgeType, Node, Edge, GraphSummary
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.graph.query import GraphQueryEngine


class TestKnowledgeGraph(unittest.TestCase):
    """Test suite for Software Knowledge Graph construction and querying."""

    def setUp(self):
        self.parser = PythonParser()
        self.builder = KnowledgeGraphBuilder()

    def _make_source_file(self, rel_path: str, content: str) -> SourceFile:
        return SourceFile(
            file_path=f"/fake/{rel_path}",
            relative_path=rel_path,
            file_name=Path(rel_path).name,
            extension=".py",
            language="python",
            file_size=len(content.encode("utf-8")),
            line_count=len(content.splitlines()),
            content=content,
            checksum="test_sum",
        )

    def _build_test_graph(self, files_dict):
        """Helper to parse a dict of {rel_path: content} and build a knowledge graph."""
        source_files = []
        parsed_files = {}

        for rel, content in files_dict.items():
            sf = self._make_source_file(rel, content)
            source_files.append(sf)
            parsed_files[rel] = self.parser.parse(sf)

        summary = IngestionSummary(
            total_files=len(source_files),
            total_lines=sum(sf.line_count for sf in source_files),
            total_size_bytes=sum(sf.file_size for sf in source_files),
            language_breakdown={"python": len(source_files)},
        )

        repo = IngestedRepository(
            repo_path="/fake",
            repo_name="test_repo",
            files=source_files,
            summary=summary,
        )

        nx_graph = self.builder.build(repo, parsed_files)
        query_engine = GraphQueryEngine(nx_graph, self.builder.nodes_by_id)
        return repo, parsed_files, nx_graph, query_engine

    def test_node_creation_and_contains_edges(self):
        code = """
class Animal:
    def speak(self):
        pass

def global_helper():
    return 42
"""
        files = {"zoo/animal.py": code}
        repo, parsed, graph, engine = self._build_test_graph(files)

        # Verify nodes created
        self.assertIn("file:zoo/animal.py", self.builder.nodes_by_id)
        self.assertIn("class:zoo/animal.py:Animal", self.builder.nodes_by_id)
        self.assertIn("method:zoo/animal.py:Animal.speak", self.builder.nodes_by_id)
        self.assertIn("function:zoo/animal.py:global_helper", self.builder.nodes_by_id)

        file_node = self.builder.nodes_by_id["file:zoo/animal.py"]
        self.assertEqual(file_node.node_type, NodeType.FILE)
        self.assertEqual(file_node.name, "animal.py")

        class_node = self.builder.nodes_by_id["class:zoo/animal.py:Animal"]
        self.assertEqual(class_node.node_type, NodeType.CLASS)
        self.assertEqual(class_node.name, "Animal")

        # Verify CONTAINS edges
        file_to_class = graph.get_edge_data("file:zoo/animal.py", "class:zoo/animal.py:Animal")
        self.assertIsNotNone(file_to_class)
        self.assertEqual(file_to_class["edge_type"], EdgeType.CONTAINS)

        class_to_meth = graph.get_edge_data("class:zoo/animal.py:Animal", "method:zoo/animal.py:Animal.speak")
        self.assertIsNotNone(class_to_meth)
        self.assertEqual(class_to_meth["edge_type"], EdgeType.CONTAINS)

        file_to_func = graph.get_edge_data("file:zoo/animal.py", "function:zoo/animal.py:global_helper")
        self.assertIsNotNone(file_to_func)
        self.assertEqual(file_to_func["edge_type"], EdgeType.CONTAINS)

    def test_imports_edges(self):
        file_a = """
import zoo.animal
from zoo.helper import calculate
"""
        file_b = """
class Animal:
    pass
"""
        file_c = """
def calculate():
    return 100
"""
        files = {
            "zoo/app.py": file_a,
            "zoo/animal.py": file_b,
            "zoo/helper.py": file_c,
        }
        repo, parsed, graph, engine = self._build_test_graph(files)

        edge_ab = graph.get_edge_data("file:zoo/app.py", "file:zoo/animal.py")
        self.assertIsNotNone(edge_ab)
        self.assertEqual(edge_ab["edge_type"], EdgeType.IMPORTS)

        edge_ac = graph.get_edge_data("file:zoo/app.py", "file:zoo/helper.py")
        self.assertIsNotNone(edge_ac)
        self.assertEqual(edge_ac["edge_type"], EdgeType.IMPORTS)

    def test_inheritance_edges(self):
        base_code = """
class BaseParser:
    def parse(self):
        pass
"""
        sub_code = """
from parser.base import BaseParser

class PythonParser(BaseParser):
    def parse(self):
        pass
"""
        files = {
            "parser/base.py": base_code,
            "parser/python.py": sub_code,
        }
        repo, parsed, graph, engine = self._build_test_graph(files)

        sub_class_id = "class:parser/python.py:PythonParser"
        base_class_id = "class:parser/base.py:BaseParser"

        inherits_edge = graph.get_edge_data(sub_class_id, base_class_id)
        self.assertIsNotNone(inherits_edge)
        self.assertEqual(inherits_edge["edge_type"], EdgeType.INHERITS)

    def test_function_calls_edges(self):
        service_code = """
def process_data(item):
    validate(item)
    return item

def validate(item):
    if not item:
        raise ValueError()
"""
        files = {"app/service.py": service_code}
        repo, parsed, graph, engine = self._build_test_graph(files)

        caller_id = "function:app/service.py:process_data"
        callee_id = "function:app/service.py:validate"

        calls_edge = graph.get_edge_data(caller_id, callee_id)
        self.assertIsNotNone(calls_edge)
        self.assertEqual(calls_edge["edge_type"], EdgeType.CALLS)

        # Verify engine get_callers & get_callees
        callers = engine.get_callers(callee_id)
        self.assertEqual(len(callers), 1)
        self.assertEqual(callers[0]["id"], caller_id)

        callees = engine.get_callees(caller_id)
        self.assertEqual(len(callees), 1)
        self.assertEqual(callees[0]["id"], callee_id)

    def test_method_calls_self(self):
        code = """
class Worker:
    def run(self):
        self.setup()
        self.execute()

    def setup(self):
        pass

    def execute(self):
        pass
"""
        files = {"app/worker.py": code}
        repo, parsed, graph, engine = self._build_test_graph(files)

        run_id = "method:app/worker.py:Worker.run"
        setup_id = "method:app/worker.py:Worker.setup"
        execute_id = "method:app/worker.py:Worker.execute"

        self.assertIsNotNone(graph.get_edge_data(run_id, setup_id))
        self.assertIsNotNone(graph.get_edge_data(run_id, execute_id))

        callees = engine.get_callees(run_id)
        callee_ids = {c["id"] for c in callees}
        self.assertIn(setup_id, callee_ids)
        self.assertIn(execute_id, callee_ids)

    def test_dependency_depth_and_traversal(self):
        f1 = "def a(): b()"
        f2 = "def b(): c()"
        f3 = "def c(): d()"
        f4 = "def d(): pass"

        files = {
            "m1.py": f1,
            "m2.py": f2,
            "m3.py": f3,
            "m4.py": f4,
        }
        repo, parsed, graph, engine = self._build_test_graph(files)

        a_id = "function:m1.py:a"
        b_id = "function:m2.py:b"
        c_id = "function:m3.py:c"
        d_id = "function:m4.py:d"

        # Depth from a should be 3: a -> b -> c -> d
        depth = engine.get_dependency_depth(a_id, edge_types=[EdgeType.CALLS])
        self.assertEqual(depth, 3)

        # Dependencies of a (direct)
        direct_deps = engine.get_dependencies(a_id, edge_types=[EdgeType.CALLS], direct_only=True)
        self.assertEqual(len(direct_deps), 1)
        self.assertEqual(direct_deps[0]["id"], b_id)

        # Transitive dependencies of a
        all_deps = engine.get_dependencies(a_id, edge_types=[EdgeType.CALLS], direct_only=False)
        all_ids = {d["id"] for d in all_deps}
        self.assertEqual(all_ids, {b_id, c_id, d_id})

    def test_circular_dependency_detection(self):
        # File A imports B, File B imports A
        code_a = "import mod_b\ndef ping(): pass"
        code_b = "import mod_a\ndef pong(): pass"

        files = {
            "mod_a.py": code_a,
            "mod_b.py": code_b,
        }
        repo, parsed, graph, engine = self._build_test_graph(files)

        cycles = engine.detect_cycles(edge_types=[EdgeType.IMPORTS])
        self.assertTrue(len(cycles) > 0)
        cycle_nodes = set(cycles[0])
        self.assertIn("file:mod_a.py", cycle_nodes)
        self.assertIn("file:mod_b.py", cycle_nodes)

        summary = self.builder.get_summary()
        self.assertTrue(summary.has_cycles)
        self.assertGreaterEqual(summary.cycle_count, 1)

    def test_structural_impact_tracing(self):
        # Service defines calculate()
        # Controller calls calculate()
        # Handler calls Controller
        code_lib = "def calculate(x): return x * 2"
        code_ctrl = "from service import calculate\ndef handle_request(req): return calculate(req)"
        code_api = "from controller import handle_request\ndef endpoint(): return handle_request(10)"

        files = {
            "service.py": code_lib,
            "controller.py": code_ctrl,
            "api.py": code_api,
        }
        repo, parsed, graph, engine = self._build_test_graph(files)

        target_id = "function:service.py:calculate"
        impact = engine.trace_impact(target_id, max_depth=3)

        self.assertTrue(impact["found"])
        self.assertEqual(impact["analysis_type"], "Structural Reachability")
        self.assertIn("disclaimer", impact)
        self.assertIn("Structural reachability traces deterministic static relationships", impact["disclaimer"])

        impacted_ids = {item["node"]["id"] for item in impact["impacted_entities"]}
        self.assertIn("function:controller.py:handle_request", impacted_ids)
        self.assertIn("function:api.py:endpoint", impacted_ids)

        # Depth check: handle_request should be at depth 1, endpoint at depth 2
        for item in impact["impacted_entities"]:
            if item["node"]["id"] == "function:controller.py:handle_request":
                self.assertEqual(item["depth"], 1)
            elif item["node"]["id"] == "function:api.py:endpoint":
                self.assertEqual(item["depth"], 2)

    def test_unresolved_symbols_graceful_handling(self):
        """Ensure external libraries, builtins, and unknown calls do NOT invent phantom edges."""
        code = """
import os
import sys
import numpy as np

def run():
    print("hello")
    len([1, 2, 3])
    unknown_external_func()
    np.zeros((10, 10))
"""
        files = {"runner.py": code}
        repo, parsed, graph, engine = self._build_test_graph(files)

        # Only runner.py file and run function should exist
        self.assertEqual(len(self.builder.nodes_by_id), 2)
        # Only CONTAINS edge from file to function
        self.assertEqual(len(self.builder.edges_list), 1)
        edge = self.builder.edges_list[0]
        self.assertEqual(edge.edge_type, EdgeType.CONTAINS)

    def test_search_nodes(self):
        code = """
class DataPipeline:
    def process(self):
        pass

def train_model():
    pass
"""
        files = {"pipeline.py": code}
        repo, parsed, graph, engine = self._build_test_graph(files)

        matches = engine.search_nodes("pipeline")
        self.assertGreaterEqual(len(matches), 1)

        class_matches = engine.search_nodes(node_type=NodeType.CLASS)
        self.assertEqual(len(class_matches), 1)
        self.assertEqual(class_matches[0]["name"], "DataPipeline")

        func_matches = engine.search_nodes(node_type=NodeType.FUNCTION)
        self.assertEqual(len(func_matches), 1)
        self.assertEqual(func_matches[0]["name"], "train_model")

    def test_impact_tracing_not_found(self):
        files = {"dummy.py": "x = 1"}
        repo, parsed, graph, engine = self._build_test_graph(files)

        res = engine.trace_impact("nonexistent:node:id")
        self.assertFalse(res["found"])
        self.assertIn("error", res)

    def test_graph_summary_and_serialization(self):
        code = """
class A:
    def foo(self):
        pass
"""
        files = {"mod.py": code}
        repo, parsed, graph, engine = self._build_test_graph(files)

        summary = self.builder.get_summary()
        self.assertEqual(summary.total_nodes, 3)  # file, class, method
        self.assertEqual(summary.total_edges, 2)  # file->class, class->method
        self.assertFalse(summary.has_cycles)

        d = self.builder.to_dict()
        self.assertIn("summary", d)
        self.assertIn("nodes", d)
        self.assertIn("edges", d)
        self.assertEqual(len(d["nodes"]), 3)


if __name__ == "__main__":
    unittest.main()

