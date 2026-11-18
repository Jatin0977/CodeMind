"""
End-to-end integration tests for CodeMind Phase 6 Agentic Investigation Engine.
Validates end-to-end investigation workflows across all 5 canonical intents:
1. UNDERSTAND
2. STRUCTURE
3. IMPACT
4. EVOLUTION (deferred)
5. INSIGHTS (deferred)
"""

import tempfile
import unittest
from pathlib import Path

from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.parsing.parser_factory import GLOBAL_PARSER_FACTORY
from codemind.graph.builder import KnowledgeGraphBuilder
from codemind.graph.query import GraphQueryEngine
from codemind.retrieval.retriever import SemanticRetriever
from codemind.retrieval.hybrid_retriever import HybridGraphRetriever
from codemind.chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from codemind.embeddings.mock_provider import MockEmbeddingProvider
from codemind.rag.providers.factory import get_llm_provider
from codemind.investigation.engine import create_investigation_engine
from codemind.investigation.models import InvestigationStatus, InvestigationIntent


class TestInvestigationIntegration(unittest.TestCase):
    """End-to-end integration test suite verifying full investigation workflows."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = Path(cls.temp_dir.name)

        # Create multi-file repository structure with real relationships
        repo_model_py = cls.repo_path / "models.py"
        repo_model_py.write_text(
            '"""Data models for ingestion."""\n\n'
            "class IngestedRepository:\n"
            '    """Represents an ingested repository."""\n'
            "    def __init__(self, name: str):\n"
            "        self.name = name\n"
            "        self.files = []\n\n"
            "    def add_file(self, f):\n"
            "        self.files.append(f)\n",
            encoding="utf-8",
        )

        filter_py = cls.repo_path / "file_filter.py"
        filter_py.write_text(
            '"""File filter implementation."""\n\n'
            "class FileFilter:\n"
            '    """Filters ignored paths and binaries."""\n'
            "    def should_ignore(self, path: str) -> bool:\n"
            '        """Check if path is ignored."""\n'
            '        return "node_modules" in path or path.startswith(".")\n',
            encoding="utf-8",
        )

        loader_py = cls.repo_path / "repo_loader.py"
        loader_py.write_text(
            '"""Repository loader."""\n\n'
            "from models import IngestedRepository\n"
            "from file_filter import FileFilter\n\n"
            "class RepositoryLoader:\n"
            '    """Loads repository files."""\n'
            "    def __init__(self):\n"
            "        self.filter = FileFilter()\n\n"
            "    def load(self, path: str) -> IngestedRepository:\n"
            "        repo = IngestedRepository(name=path)\n"
            "        return repo\n\n"
            "def verify_token(token: str) -> bool:\n"
            '    """Token verification helper."""\n'
            '    return token == "secret"\n\n'
            "def run_pipeline(token: str):\n"
            "    if verify_token(token):\n"
            "        loader = RepositoryLoader()\n"
            '        return loader.load(".")\n'
            "    return None\n",
            encoding="utf-8",
        )

        # Ingest and build graph + retrievers
        loader = RepositoryLoader()
        cls.repo = loader.load_repository(str(cls.repo_path))

        cls.parsed_files = {}
        for sf in cls.repo.files:
            pf = GLOBAL_PARSER_FACTORY.parse(sf)
            if pf:
                cls.parsed_files[sf.relative_path] = pf

        builder = KnowledgeGraphBuilder()
        cls.nx_graph = builder.build(cls.repo, cls.parsed_files)
        cls.query_engine = GraphQueryEngine(cls.nx_graph, builder.nodes_by_id)

        embed_provider = MockEmbeddingProvider(dimension=64)
        cls.retriever = SemanticRetriever(embedding_provider=embed_provider)
        cls.retriever.index_repository(cls.repo)

        chunks = []
        for sf in cls.repo.files:
            pf = cls.parsed_files.get(sf.relative_path)
            chunks.extend(GLOBAL_CHUNKER_FACTORY.chunk_file(sf, pf))

        cls.hybrid_retriever = HybridGraphRetriever(
            retriever=cls.retriever,
            graph=cls.nx_graph,
            query_engine=cls.query_engine,
        )
        cls.hybrid_retriever.index(chunks, cls.nx_graph)

        cls.mock_llm = get_llm_provider("mock")

        cls.engine = create_investigation_engine(
            repo=cls.repo,
            query_engine=cls.query_engine,
            retriever=cls.retriever,
            hybrid_retriever=cls.hybrid_retriever,
            llm_provider=cls.mock_llm,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_01_understand_investigation(self):
        """Test UNDERSTAND intent: 'Explain the FileFilter class and its methods'"""
        query = "Explain the FileFilter class and its methods"
        res = self.engine.investigate(query)

        self.assertEqual(res.intent, InvestigationIntent.UNDERSTAND)
        self.assertIn(res.overall_status, [InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS])
        self.assertGreater(len(res.step_results), 0)
        self.assertGreater(len(res.evidence), 0)
        self.assertIn("FileFilter", res.final_answer)

    def test_02_structure_investigation(self):
        """Test STRUCTURE intent: 'Who calls verify_token?'"""
        query = "Who calls verify_token?"
        res = self.engine.investigate(query)

        self.assertEqual(res.intent, InvestigationIntent.STRUCTURE)
        self.assertIn(res.overall_status, [InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS])
        self.assertGreater(len(res.step_results), 0)
        # Check that get_callers or dependents discovered run_pipeline
        callers = [
            (e.get("symbol_name") if isinstance(e, dict) else getattr(e, "symbol_name", None))
            for e in res.evidence
            if (e.get("symbol_name") if isinstance(e, dict) else getattr(e, "symbol_name", None))
            and "run_pipeline" in (e.get("symbol_name") if isinstance(e, dict) else getattr(e, "symbol_name", ""))
        ]
        self.assertGreater(len(callers), 0)

    def test_03_impact_investigation(self):
        """Test IMPACT intent: 'What is affected if IngestedRepository is modified?'"""
        query = "What is affected if IngestedRepository is modified?"
        res = self.engine.investigate(query)

        self.assertEqual(res.intent, InvestigationIntent.IMPACT)
        self.assertIn(res.overall_status, [InvestigationStatus.SUCCESS, InvestigationStatus.PARTIAL_SUCCESS])
        self.assertGreater(len(res.step_results), 0)

    def test_04_evolution_investigation_deferred(self):
        """Test EVOLUTION intent with graceful deferred handling."""
        query = "Show the commit history of file_filter.py"
        res = self.engine.investigate(query)

        self.assertEqual(res.intent, InvestigationIntent.EVOLUTION)
        has_deferred = any(
            sr.status.value.startswith("UNAVAILABLE") or "DEFERRED" in sr.status.value
            for sr in res.step_results
        )
        self.assertTrue(has_deferred)
        self.assertIn("file_filter.py", res.final_answer)

    def test_05_insights_investigation_deferred(self):
        """Test INSIGHTS intent with graceful deferred handling."""
        query = "Check architecture conformance of web module"
        res = self.engine.investigate(query)

        self.assertEqual(res.intent, InvestigationIntent.INSIGHTS)
        has_deferred = any(
            sr.status.value.startswith("UNAVAILABLE") or "DEFERRED" in sr.status.value
            for sr in res.step_results
        )
        self.assertTrue(has_deferred)
