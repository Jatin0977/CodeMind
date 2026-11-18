"""
Unit tests for CodeMind Phase 6 Milestone 2 Code Tools.
Verifies SearchSymbolsTool, GetNodeDetailsTool, and GetFileContentTool.
"""

import unittest
from typing import Dict, Any
import networkx as nx

from codemind.investigation.models import ToolStatus, ToolAvailability
from codemind.investigation.tools.code_tools import (
    SearchSymbolsTool,
    GetNodeDetailsTool,
    GetFileContentTool,
)
from codemind.graph.models import Node, NodeType
from codemind.graph.query import GraphQueryEngine
from codemind.ingestion.models import SourceFile, IngestedRepository, IngestionSummary


class TestInvestigationCodeTools(unittest.TestCase):
    """Test suite verifying code tools behavior, argument validation, and security boundaries."""

    def setUp(self):
        # Create a mock knowledge graph and query engine
        self.graph = nx.DiGraph()
        self.nodes_by_id = {}

        node1 = Node(
            id="class:auth/service.py:UserService",
            name="UserService",
            node_type=NodeType.CLASS,
            relative_path="auth/service.py",
            start_line=10,
            end_line=45,
            metadata={"docstring": "Manages user operations."},
        )
        node2 = Node(
            id="function:auth/service.py:verify_user",
            name="verify_user",
            node_type=NodeType.FUNCTION,
            relative_path="auth/service.py",
            start_line=50,
            end_line=65,
            metadata={},
        )
        node3 = Node(
            id="class:billing/service.py:UserService",
            name="UserService",
            node_type=NodeType.CLASS,
            relative_path="billing/service.py",
            start_line=5,
            end_line=30,
            metadata={},
        )

        for n in [node1, node2, node3]:
            self.nodes_by_id[n.id] = n
            self.graph.add_node(n.id, **n.to_dict())

        self.query_engine = GraphQueryEngine(self.graph, self.nodes_by_id)

        # Create a mock ingested repository
        sample_code = (
            "import os\n"
            "# Line 2\n"
            "class UserService:\n"
            "    def __init__(self):\n"
            "        self.name = 'test'\n"
            "    def get_user(self, uid):\n"
            "        return {'id': uid}\n"
            "# Line 8\n"
        )
        self.sf = SourceFile(
            file_path="C:/repo/auth/service.py",
            relative_path="auth/service.py",
            file_name="service.py",
            extension=".py",
            language="python",
            file_size=len(sample_code),
            line_count=8,
            content=sample_code,
            checksum="dummy_hash",
        )
        self.repo = IngestedRepository(
            repo_path="C:/repo",
            repo_name="mock_repo",
            files=[self.sf],
            summary=IngestionSummary(total_files=1, total_lines=8),
        )

    # 1. SearchSymbolsTool tests
    def test_search_symbols_valid_and_ambiguity(self):
        """Verify searching symbols, finding matches, and ambiguity tracking."""
        tool = SearchSymbolsTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "search_symbols")
        self.assertEqual(tool.availability, ToolAvailability.AVAILABLE)

        # Search for UserService -> exists in both auth and billing (ambiguous)
        result = tool.execute({"query": "UserService"})
        self.assertTrue(result.is_success)
        self.assertEqual(result.data["total_matches"], 2)
        self.assertTrue(result.data["is_ambiguous"])
        self.assertEqual(len(result.data["matches"]), 2)

        # Search for unique function
        res_unique = tool.execute({"query": "verify_user"})
        self.assertTrue(res_unique.is_success)
        self.assertEqual(res_unique.data["total_matches"], 1)
        self.assertFalse(res_unique.data["is_ambiguous"])

    def test_search_symbols_filter_by_node_type(self):
        """Verify filtering symbols by node_type."""
        tool = SearchSymbolsTool(query_engine=self.query_engine)

        res_func = tool.execute({"query": "service", "node_type": "function"})
        self.assertTrue(res_func.is_success)
        self.assertEqual(res_func.data["total_matches"], 1)
        self.assertEqual(res_func.data["matches"][0]["name"], "verify_user")

        res_class = tool.execute({"query": "service", "node_type": "class"})
        self.assertTrue(res_class.is_success)
        self.assertEqual(res_class.data["total_matches"], 2)

    def test_search_symbols_error_handling(self):
        """Verify error handling on empty queries or missing query engine."""
        tool = SearchSymbolsTool(query_engine=self.query_engine)

        res_empty = tool.execute({"query": "   "})
        self.assertTrue(res_empty.is_error)
        self.assertIn("cannot be empty", res_empty.message)

        tool_no_engine = SearchSymbolsTool(query_engine=None)
        res_no_engine = tool_no_engine.execute({"query": "UserService"})
        self.assertTrue(res_no_engine.is_error)
        self.assertIn("not initialized", res_no_engine.message)

    # 2. GetNodeDetailsTool tests
    def test_get_node_details_valid(self):
        """Verify retrieving existing node details by canonical node ID."""
        tool = GetNodeDetailsTool(query_engine=self.query_engine)
        self.assertEqual(tool.name, "get_node_details")

        result = tool.execute({"node_id": "class:auth/service.py:UserService"})
        self.assertTrue(result.is_success)
        self.assertEqual(result.data["name"], "UserService")
        self.assertEqual(result.data["start_line"], 10)
        self.assertEqual(result.data["end_line"], 45)
        self.assertEqual(result.data["metadata"]["docstring"], "Manages user operations.")

    def test_get_node_details_missing_and_errors(self):
        """Verify handling non-existent nodes and empty IDs."""
        tool = GetNodeDetailsTool(query_engine=self.query_engine)

        res_missing = tool.execute({"node_id": "class:auth.py:NonExistent"})
        self.assertTrue(res_missing.is_error)
        self.assertIn("not found in knowledge graph", res_missing.message)
        self.assertFalse(res_missing.data["found"])

        res_empty = tool.execute({"node_id": ""})
        self.assertTrue(res_empty.is_error)

        tool_no_engine = GetNodeDetailsTool(query_engine=None)
        res_no_engine = tool_no_engine.execute({"node_id": "class:test"})
        self.assertTrue(res_no_engine.is_error)

    # 3. GetFileContentTool tests
    def test_get_file_content_valid_and_slicing(self):
        """Verify reading verified repository lines with line numbers."""
        tool = GetFileContentTool(repo=self.repo)
        self.assertEqual(tool.name, "get_file_content")

        # Full file
        res_full = tool.execute({"relative_path": "auth/service.py"})
        self.assertTrue(res_full.is_success)
        self.assertEqual(res_full.data["total_lines"], 8)
        self.assertEqual(res_full.data["line_count_returned"], 8)
        self.assertEqual(res_full.data["start_line"], 1)
        self.assertEqual(res_full.data["end_line"], 8)
        self.assertEqual(res_full.data["lines"][0]["line_number"], 1)
        self.assertEqual(res_full.data["lines"][0]["content"], "import os")

        # Specific line range (lines 3-5: UserService class and init)
        res_slice = tool.execute({
            "relative_path": "auth/service.py",
            "start_line": 3,
            "end_line": 5,
        })
        self.assertTrue(res_slice.is_success)
        self.assertEqual(res_slice.data["start_line"], 3)
        self.assertEqual(res_slice.data["end_line"], 5)
        self.assertEqual(res_slice.data["line_count_returned"], 3)
        self.assertEqual(res_slice.data["lines"][0]["content"], "class UserService:")
        self.assertEqual(res_slice.data["lines"][0]["line_number"], 3)
        self.assertEqual(res_slice.data["lines"][2]["line_number"], 5)

    def test_get_file_content_line_range_validation(self):
        """Verify rejection of invalid line ranges."""
        tool = GetFileContentTool(repo=self.repo)

        # end_line < start_line
        res_inv = tool.execute({
            "relative_path": "auth/service.py",
            "start_line": 6,
            "end_line": 4,
        })
        self.assertTrue(res_inv.is_error)
        self.assertIn("cannot be less than start_line", res_inv.message)

        # start_line > total_lines
        res_out = tool.execute({
            "relative_path": "auth/service.py",
            "start_line": 50,
        })
        self.assertTrue(res_out.is_error)
        self.assertIn("exceeds total line count", res_out.message)

    def test_get_file_content_security_path_traversal(self):
        """Verify path traversal and absolute path attempts are strictly rejected."""
        tool = GetFileContentTool(repo=self.repo)

        traversal_attempts = [
            "../../etc/passwd",
            "../outside.py",
            "auth/../../secret.txt",
            "/absolute/path/file.py",
            "C:/Windows/System32/calc.exe",
        ]
        for bad_path in traversal_attempts:
            res = tool.execute({"relative_path": bad_path})
            self.assertTrue(res.is_error, f"Failed to reject traversal path: {bad_path}")
            self.assertIn("prohibited", res.message)

    def test_get_file_content_missing_file_and_repo(self):
        """Verify handling missing files and uninitialized repo."""
        tool = GetFileContentTool(repo=self.repo)
        res_missing = tool.execute({"relative_path": "auth/missing.py"})
        self.assertTrue(res_missing.is_error)
        self.assertIn("not found in ingested repository", res_missing.message)

        tool_no_repo = GetFileContentTool(repo=None)
        res_no_repo = tool_no_repo.execute({"relative_path": "auth/service.py"})
        self.assertTrue(res_no_repo.is_error)
        self.assertIn("not ingested", res_no_repo.message)


if __name__ == "__main__":
    unittest.main()
