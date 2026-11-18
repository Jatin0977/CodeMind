"""
Unit tests for CodeMind Phase 6 Milestone 2 Retrieval Tools.
Verifies SemanticSearchTool and HybridSearchTool wrappers.
"""

import unittest
import networkx as nx

from codemind.investigation.models import ToolStatus, ToolAvailability
from codemind.investigation.tools.retrieval_tools import (
    SemanticSearchTool,
    HybridSearchTool,
)
from codemind.chunking.models import CodeChunk
from codemind.embeddings.mock_provider import MockEmbeddingProvider
from codemind.vector_store.memory_store import InMemoryVectorStore
from codemind.retrieval.retriever import SemanticRetriever
from codemind.retrieval.hybrid_retriever import HybridGraphRetriever
from codemind.graph.models import EdgeType


class TestInvestigationRetrievalTools(unittest.TestCase):
    """Test suite verifying semantic and hybrid retrieval tool wrappers."""

    def setUp(self):
        # Create chunks
        self.chunk1 = CodeChunk(
            chunk_id="chunk_1",
            file_path="C:/repo/auth/service.py",
            relative_path="auth/service.py",
            language="python",
            chunk_type="class",
            symbol_name="UserService",
            start_line=10,
            end_line=30,
            content="class UserService:\n    def authenticate(self): pass",
        )
        self.chunk2 = CodeChunk(
            chunk_id="chunk_2",
            file_path="C:/repo/auth/token.py",
            relative_path="auth/token.py",
            language="python",
            chunk_type="function",
            symbol_name="verify_jwt",
            start_line=1,
            end_line=15,
            content="def verify_jwt(token):\n    return token == 'valid'",
        )
        self.chunk3 = CodeChunk(
            chunk_id="chunk_3",
            file_path="C:/repo/db/connection.py",
            relative_path="db/connection.py",
            language="python",
            chunk_type="class",
            symbol_name="Database",
            start_line=1,
            end_line=20,
            content="class Database:\n    def connect(self): pass",
        )
        self.chunks = [self.chunk1, self.chunk2, self.chunk3]

        # In-memory vector store & retriever
        self.embedding_provider = MockEmbeddingProvider(dimension=16)
        self.vector_store = InMemoryVectorStore()
        self.retriever = SemanticRetriever(
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
        )
        self.retriever.index_chunks(self.chunks)

        # Knowledge graph linking UserService -> CALLS -> verify_jwt
        self.graph = nx.DiGraph()
        self.graph.add_node("class:auth/service.py:UserService", name="UserService", node_type="class")
        self.graph.add_node("function:auth/token.py:verify_jwt", name="verify_jwt", node_type="function")
        self.graph.add_edge(
            "class:auth/service.py:UserService",
            "function:auth/token.py:verify_jwt",
            edge_type=EdgeType.CALLS,
        )

        self.hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=self.graph,
        )

    def test_semantic_search_tool_valid(self):
        """Verify SemanticSearchTool returns structured results with chunk metadata."""
        tool = SemanticSearchTool(retriever=self.retriever)
        self.assertEqual(tool.name, "semantic_search")
        self.assertEqual(tool.availability, ToolAvailability.AVAILABLE)

        res = tool.execute({"query": "authenticate user", "top_k": 2})
        self.assertTrue(res.is_success)
        self.assertEqual(res.data["query"], "authenticate user")
        self.assertLessEqual(len(res.data["results"]), 2)

        # Verify provenance is vector_seed
        for item in res.data["results"]:
            self.assertEqual(item["provenance"], "vector_seed")
            self.assertIn("score", item)
            self.assertIn("chunk", item)

        # Verify disclaimer notes mock provider
        self.assertTrue(res.metadata["is_mock_provider"])
        self.assertIsNotNone(res.metadata["disclaimer"])

    def test_semantic_search_tool_errors(self):
        """Verify error handling on empty queries or missing retriever."""
        tool = SemanticSearchTool(retriever=self.retriever)

        res_empty = tool.execute({"query": ""})
        self.assertTrue(res_empty.is_error)

        tool_uninit = SemanticSearchTool(retriever=None)
        res_uninit = tool_uninit.execute({"query": "test"})
        self.assertTrue(res_uninit.is_error)
        self.assertIn("not initialized", res_uninit.message)

    def test_hybrid_search_tool_valid_and_provenance(self):
        """Verify HybridSearchTool distinguishes vector seeds from graph-expanded results."""
        tool = HybridSearchTool(hybrid_retriever=self.hybrid_retriever)
        self.assertEqual(tool.name, "hybrid_search")
        self.assertEqual(tool.availability, ToolAvailability.AVAILABLE)

        res = tool.execute({
            "query": "authenticate",
            "top_k": 3,
            "intent": "flow",
            "use_graph": True,
        })
        self.assertTrue(res.is_success)
        self.assertEqual(res.data["retrieval_mode"], "hybrid")
        self.assertGreater(res.data["total_results"], 0)

        # Check provenance fields exist on results
        results = res.data["results"]
        for r in results:
            self.assertIn(r["provenance"], ["vector_seed", "graph_expanded"])

    def test_hybrid_search_tool_fallback_to_vector_only(self):
        """Verify HybridSearchTool cleanly supports vector-only mode when use_graph is False."""
        tool = HybridSearchTool(hybrid_retriever=self.hybrid_retriever)

        res = tool.execute({
            "query": "database",
            "top_k": 2,
            "use_graph": False,
        })
        self.assertTrue(res.is_success)
        self.assertEqual(res.data["retrieval_mode"], "vector_only")

    def test_hybrid_search_tool_errors(self):
        """Verify error handling for empty queries and uninitialized retriever."""
        tool = HybridSearchTool(hybrid_retriever=self.hybrid_retriever)

        res_empty = tool.execute({"query": "   "})
        self.assertTrue(res_empty.is_error)

        tool_uninit = HybridSearchTool(hybrid_retriever=None)
        res_uninit = tool_uninit.execute({"query": "test"})
        self.assertTrue(res_uninit.is_error)


if __name__ == "__main__":
    unittest.main()
