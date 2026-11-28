"""
Unit tests for CodeMind Phase 5: Hybrid Graph-Aware Retrieval Engine.
Tests ChunkGraphMapper, QueryIntent classification, HybridGraphRetriever,
topological expansion, hybrid scoring, context budgeting, and RAG integration.
"""

import unittest
from pathlib import Path
import networkx as nx

from codemind.chunking.models import CodeChunk
from codemind.ingestion.models import SourceFile, IngestedRepository, IngestionSummary
from codemind.parsing.python_parser import PythonParser
from codemind.graph.models import NodeType, EdgeType, Node, Edge
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.graph.query import GraphQueryEngine
from codemind.embeddings.mock_provider import MockEmbeddingProvider
from codemind.vector_store.memory_store import InMemoryVectorStore
from codemind.retrieval.retriever import SemanticRetriever
from codemind.retrieval.hybrid_retriever import (
    HybridGraphRetriever,
    ChunkGraphMapper,
    HybridSearchResult,
    QueryIntent,
    classify_query_intent,
    DEFAULT_RELATIONSHIP_WEIGHTS,
)
from codemind.rag.engine import RAGEngine
from codemind.rag.providers.mock_provider import MockLLMProvider


class TestHybridRetrieval(unittest.TestCase):
    """Test suite for Hybrid Graph-Aware Retrieval components."""

    def setUp(self):
        self.parser = PythonParser()
        self.graph_builder = KnowledgeGraphBuilder()
        self.embedder = MockEmbeddingProvider(dimension=64)
        self.vector_store = InMemoryVectorStore()
        self.retriever = SemanticRetriever(
            embedding_provider=self.embedder,
            vector_store=self.vector_store,
        )

    def _build_fixture_graph(self):
        """
        Creates a synthetic 3-file codebase graph:
        - service.py: OrderService.process_order (calls Validator.validate, calls notify_user)
        - validator.py: Validator.validate (inherits BaseValidator)
        - notifier.py: notify_user (called by OrderService.process_order)
        """
        code_service = """
from validator import Validator
from notifier import notify_user

class OrderService:
    def process_order(self, order_id: str) -> bool:
        \"\"\"Process customer order.\"\"\"
        v = Validator()
        if v.validate(order_id):
            return notify_user(order_id)
        return False
"""
        code_validator = """
class BaseValidator:
    def is_valid_format(self, data: str) -> bool:
        return len(data) > 0

class Validator(BaseValidator):
    def validate(self, order_id: str) -> bool:
        \"\"\"Validate order format.\"\"\"
        return self.is_valid_format(order_id)
"""
        code_notifier = """
def notify_user(order_id: str) -> bool:
    \"\"\"Send notification to customer.\"\"\"
    return True
"""
        files_dict = {
            "service.py": code_service,
            "validator.py": code_validator,
            "notifier.py": code_notifier,
        }

        source_files = []
        parsed_files = {}
        for rel, content in files_dict.items():
            sf = SourceFile(
                file_path=f"/fake/{rel}",
                relative_path=rel,
                file_name=Path(rel).name,
                extension=".py",
                language="python",
                file_size=len(content.encode("utf-8")),
                line_count=len(content.splitlines()),
                content=content,
                checksum="hash_" + rel,
            )
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
            repo_name="ecommerce_test",
            files=source_files,
            summary=summary,
        )

        nx_graph = self.graph_builder.build(repo, parsed_files)
        query_engine = GraphQueryEngine(nx_graph, self.graph_builder.nodes_by_id)

        # Index chunks in retriever
        from codemind.chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
        all_chunks = []
        for sf in source_files:
            parsed = parsed_files[sf.relative_path]
            all_chunks.extend(GLOBAL_CHUNKER_FACTORY.chunk_file(sf, parsed))

        self.retriever.index_chunks(all_chunks)
        return repo, nx_graph, query_engine, all_chunks

    # -------------------------------------------------------------
    # 1. Mapping Tests
    # -------------------------------------------------------------

    def test_chunk_graph_mapper_basic(self):
        mapper = ChunkGraphMapper()

        c_func = CodeChunk.create(
            file_path="/repo/utils/math_ops.py",
            relative_path="utils/math_ops.py",
            language="python",
            chunk_type="function",
            start_line=1,
            end_line=10,
            content="def add(a, b): return a + b",
            symbol_name="add",
        )
        c_class = CodeChunk.create(
            file_path="/repo/models/user.py",
            relative_path="models/user.py",
            language="python",
            chunk_type="class",
            start_line=1,
            end_line=20,
            content="class User: pass",
            symbol_name="User",
        )
        c_method = CodeChunk.create(
            file_path="/repo/models/user.py",
            relative_path="models/user.py",
            language="python",
            chunk_type="method",
            start_line=10,
            end_line=20,
            content="def get_name(self): return self.name",
            symbol_name="User.get_name",
            parent_symbol="User",
        )

        mapper.index([c_func, c_class, c_method])

        # Test chunk_id to node_id
        self.assertEqual(mapper.get_node_for_chunk(c_func.chunk_id), "function:utils/math_ops.py:add")
        self.assertEqual(mapper.get_node_for_chunk(c_class.chunk_id), "class:models/user.py:User")
        self.assertEqual(mapper.get_node_for_chunk(c_method.chunk_id), "method:models/user.py:User.get_name")

        # Test node_id to chunks (reverse lookup)
        chunks_func = mapper.get_chunks_for_node("function:utils/math_ops.py:add")
        self.assertEqual(len(chunks_func), 1)
        self.assertEqual(chunks_func[0].chunk_id, c_func.chunk_id)

    def test_chunk_graph_mapper_windows_path_normalization(self):
        mapper = ChunkGraphMapper()
        c_win = CodeChunk.create(
            file_path="C:\\repo\\service\\worker.py",
            relative_path="service\\worker.py",
            language="python",
            chunk_type="function",
            start_line=5,
            end_line=15,
            content="def run_job(): pass",
            symbol_name="run_job",
        )
        mapper.index([c_win])

        # Should normalize backslashes to forward slashes
        node_id = mapper.get_node_for_chunk(c_win.chunk_id)
        self.assertEqual(node_id, "function:service/worker.py:run_job")
        self.assertNotIn("\\", node_id)

    def test_chunk_graph_mapper_module_and_doc_chunks(self):
        mapper = ChunkGraphMapper()
        c_mod = CodeChunk.create(
            file_path="/repo/main.py",
            relative_path="main.py",
            language="python",
            chunk_type="module_header",
            start_line=1,
            end_line=10,
            content='"""Main module."""\nimport os',
            symbol_name="module:main.py",
        )
        c_doc = CodeChunk.create(
            file_path="/repo/docs/guide.md",
            relative_path="docs/guide.md",
            language="markdown",
            chunk_type="doc_section",
            start_line=1,
            end_line=25,
            content="# Installation Guide\nRun pip install .",
            symbol_name="Installation Guide",
        )
        mapper.index([c_mod, c_doc])

        self.assertEqual(mapper.get_node_for_chunk(c_mod.chunk_id), "file:main.py")
        self.assertEqual(mapper.get_node_for_chunk(c_doc.chunk_id), "file:docs/guide.md")

    def test_chunk_graph_mapper_missing_graph_node_graceful(self):
        mapper = ChunkGraphMapper()
        # Create an artificial graph with only one node
        g = nx.DiGraph()
        g.add_node("function:auth.py:login")

        c1 = CodeChunk.create(
            file_path="/repo/auth.py",
            relative_path="auth.py",
            language="python",
            chunk_type="function",
            start_line=1,
            end_line=10,
            content="def login(): pass",
            symbol_name="login",
        )
        c_missing = CodeChunk.create(
            file_path="/repo/external.py",
            relative_path="external.py",
            language="python",
            chunk_type="function",
            start_line=1,
            end_line=5,
            content="def external_call(): pass",
            symbol_name="external_call",
        )

        mapper.index([c1, c_missing], graph=g)
        self.assertEqual(mapper.get_node_for_chunk(c1.chunk_id), "function:auth.py:login")
        self.assertIsNone(mapper.get_node_for_chunk(c_missing.chunk_id))

    # -------------------------------------------------------------
    # 2. Query Intent Classification Tests
    # -------------------------------------------------------------

    def test_classify_query_intent(self):
        # Flow queries
        self.assertEqual(classify_query_intent("How does repository loading work?"), QueryIntent.FLOW)
        self.assertEqual(classify_query_intent("Explain the execution flow of process_order"), QueryIntent.FLOW)
        self.assertEqual(classify_query_intent("How does the AST chunker build signatures?"), QueryIntent.FLOW)
        self.assertEqual(classify_query_intent("Describe the pipeline steps for indexing"), QueryIntent.FLOW)

        # Impact queries
        self.assertEqual(classify_query_intent("Who uses this function?"), QueryIntent.IMPACT)
        self.assertEqual(classify_query_intent("What depends on file_filter.py?"), QueryIntent.IMPACT)
        self.assertEqual(classify_query_intent("What could break if Validator changes?"), QueryIntent.IMPACT)
        self.assertEqual(classify_query_intent("Show callers of notify_user"), QueryIntent.IMPACT)

        # General queries
        self.assertEqual(classify_query_intent("What is CodeMind?"), QueryIntent.GENERAL)
        self.assertEqual(classify_query_intent("Overview of data models"), QueryIntent.GENERAL)

    # -------------------------------------------------------------
    # 3. Hybrid Graph Expansion & Scoring Tests
    # -------------------------------------------------------------

    def test_forward_calls_and_inherits_expansion(self):
        repo, graph, query_engine, chunks = self._build_fixture_graph()

        hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=graph,
            query_engine=query_engine,
            alpha=0.6,
            gamma=0.7,
            total_budget=5,
        )

        # Query targeting process_order with flow intent
        query = "How does OrderService process_order work and validate orders?"
        results = hybrid_retriever.search(query, top_k=5, intent_override=QueryIntent.FLOW)

        self.assertGreater(len(results), 0)

        # Check that we have both seed and expanded evidence
        provenances = {r.provenance for r in results}
        self.assertIn("vector_seed", provenances)
        self.assertIn("graph_expanded", provenances)

        # Confirm that Validator.validate or notify_user was pulled in via CALLS
        symbols = [r.chunk.symbol_name for r in results if r.chunk.symbol_name]
        self.assertTrue(
            any("Validator.validate" in s or "notify_user" in s for s in symbols),
            f"Expected callee in expanded symbols: {symbols}",
        )

        # Check relationship tag
        expanded_items = [r for r in results if r.provenance == "graph_expanded"]
        self.assertTrue(len(expanded_items) > 0)
        self.assertIn(expanded_items[0].relationship_type, (EdgeType.CALLS, EdgeType.INHERITS, EdgeType.CONTAINS))

    def test_reverse_impact_expansion(self):
        repo, graph, query_engine, chunks = self._build_fixture_graph()

        hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=graph,
            query_engine=query_engine,
            total_budget=5,
        )

        # Query asking who depends on / uses notify_user
        query = "Who uses notify_user in the codebase?"
        results = hybrid_retriever.search(query, top_k=5, intent_override=QueryIntent.IMPACT)

        self.assertGreater(len(results), 0)
        # Should identify OrderService or process_order as a caller
        symbols = [r.chunk.symbol_name for r in results if r.chunk.symbol_name]
        self.assertTrue(
            any("process_order" in s or "OrderService" in s for s in symbols),
            f"Expected caller in results: {symbols}",
        )

    def test_hybrid_scoring_formula(self):
        repo, graph, query_engine, chunks = self._build_fixture_graph()

        hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=graph,
            query_engine=query_engine,
            alpha=0.6,
            gamma=0.7,
        )

        results = hybrid_retriever.search("How does process_order work?", top_k=4)
        for res in results:
            # Score must be bounded between 0.0 and 1.0
            self.assertTrue(0.0 <= res.score <= 1.0)
            self.assertGreater(res.graph_score, 0.0)

            # Check that hybrid results have proper rank order
            if res.provenance == "graph_expanded":
                self.assertIsNotNone(res.relationship_type)
                self.assertGreater(res.hop_distance, 0)

    def test_seed_ratio_guarantee(self):
        repo, graph, query_engine, chunks = self._build_fixture_graph()

        hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=graph,
            query_engine=query_engine,
            total_budget=4,
            seed_ratio=0.5,
        )

        results = hybrid_retriever.search("How does process_order work?", top_k=4)
        seeds = [r for r in results if r.provenance == "vector_seed"]
        # With total 4 and seed_ratio 0.5, at least 2 slots must be seeds
        self.assertGreaterEqual(len(seeds), 2)

    def test_vector_only_fallback_with_use_graph_false(self):
        repo, graph, query_engine, chunks = self._build_fixture_graph()

        hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=graph,
            query_engine=query_engine,
        )

        # use_graph=False must return 100% vector-only results without graph expansions
        results = hybrid_retriever.search("How does process_order work?", top_k=3, use_graph=False)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertFalse(hasattr(r, "provenance") and r.provenance == "graph_expanded")

    # -------------------------------------------------------------
    # 4. RAG Engine Integration Tests
    # -------------------------------------------------------------

    def test_rag_engine_with_hybrid_retriever(self):
        repo, graph, query_engine, chunks = self._build_fixture_graph()

        hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=graph,
            query_engine=query_engine,
        )

        mock_llm = MockLLMProvider()
        rag_engine = RAGEngine(
            retriever=self.retriever,
            hybrid_retriever=hybrid_retriever,
            llm_provider=mock_llm,
        )

        # Ask question with hybrid retrieval enabled
        response = rag_engine.ask(
            query="How does OrderService process_order work and validate?",
            top_k=5,
            use_graph=True,
        )

        self.assertTrue(response.is_sufficient)
        self.assertGreater(len(response.citations), 0)
        self.assertGreater(len(response.sources), 0)

        # Verify that sources contain graph-expanded items
        has_expanded = any(getattr(s, "provenance", None) == "graph_expanded" for s in response.sources)
        self.assertTrue(has_expanded, "Expected at least one graph-expanded source in RAG response")

    def test_rag_engine_backward_compatible_vector_only(self):
        repo, graph, query_engine, chunks = self._build_fixture_graph()

        hybrid_retriever = HybridGraphRetriever(
            retriever=self.retriever,
            graph=graph,
            query_engine=query_engine,
        )

        mock_llm = MockLLMProvider()
        rag_engine = RAGEngine(
            retriever=self.retriever,
            hybrid_retriever=hybrid_retriever,
            llm_provider=mock_llm,
        )

        # Explicitly disable graph
        response = rag_engine.ask(
            query="How does OrderService work?",
            top_k=3,
            use_graph=False,
        )

        self.assertTrue(response.is_sufficient)
        # All sources should be pure vector results
        for s in response.sources:
            self.assertNotEqual(getattr(s, "provenance", None), "graph_expanded")

    # -------------------------------------------------------------
    # 5. Controlled Seed Expansion & Ground-Truth Regression Tests
    # -------------------------------------------------------------

    def test_controlled_seed_ast_chunker_signature_helpers_and_inheritance(self):
        """Regression test: verifies Q2 and Q3 ground truth from verified ASTCodeChunker seed."""
        from codemind.ingestion.repo_loader import RepositoryLoader
        from codemind.parsing.parser_factory import GLOBAL_PARSER_FACTORY
        from codemind.graph.builder import KnowledgeGraphBuilder
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "codemind"
        loader = RepositoryLoader()
        repo = loader.load_repository(str(root))
        parsed = {sf.relative_path: GLOBAL_PARSER_FACTORY.parse(sf) for sf in repo.files if GLOBAL_PARSER_FACTORY.parse(sf)}
        builder = KnowledgeGraphBuilder()
        nx_g = builder.build(repo, parsed)

        hr = HybridGraphRetriever(retriever=self.retriever, graph=nx_g)

        # 1. Q2 helper-method discovery from correct ASTCodeChunker seed
        exp_ast = hr._expand_node("class:chunking/ast_chunker.py:ASTCodeChunker", seed_score=0.8, intent="flow")
        discovered_nodes = {e["node_id"] for e in exp_ast}
        self.assertIn("method:chunking/ast_chunker.py:ASTCodeChunker._build_class_signature", discovered_nodes)
        self.assertIn("method:chunking/ast_chunker.py:ASTCodeChunker._build_func_signature", discovered_nodes)

        # 2. Q3 BaseChunker discovery through INHERITS
        inherits_edges = [e for e in exp_ast if e["relationship"] == EdgeType.INHERITS]
        self.assertTrue(len(inherits_edges) > 0)
        self.assertEqual(inherits_edges[0]["node_id"], "class:chunking/base_chunker.py:BaseChunker")
        self.assertGreater(inherits_edges[0]["graph_score"], 0.4)

    def test_controlled_seed_file_filter_impact_dependents(self):
        """Regression test: verifies Q4 incoming dependency discovery from FileFilter seed."""
        from codemind.ingestion.repo_loader import RepositoryLoader
        from codemind.parsing.parser_factory import GLOBAL_PARSER_FACTORY
        from codemind.graph.builder import KnowledgeGraphBuilder
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "codemind"
        loader = RepositoryLoader()
        repo = loader.load_repository(str(root))
        parsed = {sf.relative_path: GLOBAL_PARSER_FACTORY.parse(sf) for sf in repo.files if GLOBAL_PARSER_FACTORY.parse(sf)}
        builder = KnowledgeGraphBuilder()
        nx_g = builder.build(repo, parsed)

        hr = HybridGraphRetriever(retriever=self.retriever, graph=nx_g)

        # 1. Incoming CALLS to FileFilter class
        exp_ff = hr._expand_node("class:ingestion/file_filter.py:FileFilter", seed_score=0.8, intent="impact")
        discovered_ff = {e["node_id"] for e in exp_ff}
        self.assertIn("method:ingestion/repo_loader.py:RepositoryLoader.__init__", discovered_ff)

        # 2. Incoming IMPORTS to file_filter.py
        exp_file = hr._expand_node("file:ingestion/file_filter.py", seed_score=0.8, intent="impact")
        discovered_file = {e["node_id"] for e in exp_file}
        self.assertIn("file:ingestion/repo_loader.py", discovered_file)

    def test_unrelated_nodes_not_expanded_arbitrarily(self):
        """Regression test: verifies no irrelevant graph expansion is labelled as relevant."""
        repo, graph, query_engine, chunks = self._build_fixture_graph()
        hr = HybridGraphRetriever(retriever=self.retriever, graph=graph, query_engine=query_engine)

        # In notifier.py, notify_user is a leaf function with no outgoing calls
        exp = hr._expand_node("function:notifier.py:notify_user", seed_score=0.8, intent="flow")
        discovered = {e["node_id"] for e in exp}
        # Forward flow must not expand backwards or to unrelated classes
        self.assertNotIn("class:service.py:OrderService", discovered)
        self.assertNotIn("class:validator.py:Validator", discovered)


if __name__ == "__main__":
    unittest.main()
