"""
Unit tests for Grounded RAG, prompt formatting, citation extraction, and insufficient-context handling.
"""

import unittest
from codemind.chunking.models import CodeChunk
from codemind.vector_store.base import SearchResult
from codemind.vector_store.memory_store import InMemoryVectorStore
from codemind.embeddings.mock_provider import MockEmbeddingProvider
from codemind.retrieval.retriever import SemanticRetriever
from codemind.ingestion.models import SourceFile, IngestedRepository, IngestionSummary
from codemind.rag.models import RAGResponse
from codemind.rag.prompt_templates import format_evidence_context, extract_citations
from codemind.rag.providers.mock_provider import MockLLMProvider
from codemind.rag.providers.base import BaseLLMProvider
from codemind.rag.engine import RAGEngine


class TestRAG(unittest.TestCase):
    """Test suite for Grounded Codebase RAG components."""

    def setUp(self):
        self.chunk1 = CodeChunk.create(
            file_path="/repo/codemind/auth.py",
            relative_path="codemind/auth.py",
            language="python",
            chunk_type="function",
            start_line=10,
            end_line=25,
            content="def authenticate_user(user, pwd):\n    return verify(user, pwd)",
            symbol_name="authenticate_user",
            signature="def authenticate_user(user, pwd) -> bool",
        )
        self.chunk2 = CodeChunk.create(
            file_path="/repo/codemind/filter.py",
            relative_path="codemind/filter.py",
            language="python",
            chunk_type="method",
            start_line=15,
            end_line=30,
            content="def should_ignore_dir(self, name):\n    return name in self.ignored",
            symbol_name="FileFilter.should_ignore_dir",
            parent_symbol="FileFilter",
            signature="def should_ignore_dir(self, name: str) -> bool",
        )
        self.res1 = SearchResult(chunk=self.chunk1, score=0.88, rank=1)
        self.res2 = SearchResult(chunk=self.chunk2, score=0.75, rank=2)

    def test_context_assembly(self):
        evidence_text = format_evidence_context([self.res1, self.res2])

        self.assertIn("--- Evidence #1 [codemind/auth.py:10-25] (FUNCTION: authenticate_user)", evidence_text)
        self.assertIn("--- Evidence #2 [codemind/filter.py:15-30] (METHOD: FileFilter.should_ignore_dir)", evidence_text)
        self.assertIn("def authenticate_user", evidence_text)
        self.assertIn("def should_ignore_dir", evidence_text)

    def test_citation_parser(self):
        text = """
The system handles login at [codemind/auth.py:10-25] and filters directories at [codemind/filter.py:15-30].
A repeated reference [codemind/auth.py:10-25] should not be duplicated.
"""
        citations = extract_citations(text)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0], "codemind/auth.py:10-25")
        self.assertEqual(citations[1], "codemind/filter.py:15-30")

    def test_mock_llm_provider_grounded_synthesis(self):
        provider = MockLLMProvider()
        evidence_text = format_evidence_context([self.res1, self.res2])
        prompt = f"Question: How is auth handled?\n\n{evidence_text}"

        response = provider.generate(prompt)
        self.assertIn("[codemind/auth.py:10-25]", response)
        self.assertIn("authenticate_user", response)

    def test_insufficient_context_handling(self):
        mock_provider = MockLLMProvider()
        # Empty retriever
        embedder = MockEmbeddingProvider()
        store = InMemoryVectorStore()
        retriever = SemanticRetriever(embedding_provider=embedder, vector_store=store)

        engine = RAGEngine(retriever=retriever, llm_provider=mock_provider)
        rag_res = engine.ask("How is Kubernetes pod scaling orchestrated?")

        self.assertFalse(rag_res.is_sufficient)
        self.assertIn("Insufficient context", rag_res.answer)
        self.assertEqual(len(rag_res.citations), 0)

    def test_provider_failure_handling(self):
        failing_provider = MockLLMProvider()
        failing_provider.should_fail = True

        embedder = MockEmbeddingProvider()
        store = InMemoryVectorStore()
        store.add([self.chunk1], embedder.embed_documents([self.chunk1.content]))
        retriever = SemanticRetriever(embedding_provider=embedder, vector_store=store)

        engine = RAGEngine(retriever=retriever, llm_provider=failing_provider)
        rag_res = engine.ask("How does authentication work?")

        self.assertFalse(rag_res.is_sufficient)
        self.assertIn("Error generating answer", rag_res.answer)

    def test_end_to_end_rag_engine(self):
        embedder = MockEmbeddingProvider()
        store = InMemoryVectorStore()
        retriever = SemanticRetriever(embedding_provider=embedder, vector_store=store)
        mock_llm = MockLLMProvider()
        engine = RAGEngine(retriever=retriever, llm_provider=mock_llm)

        sf = SourceFile(
            file_path="/repo/auth.py",
            relative_path="auth.py",
            file_name="auth.py",
            extension=".py",
            language="python",
            file_size=150,
            line_count=5,
            content="def authenticate_user(username, password):\n    return verify(password)\n",
            checksum="chk_123",
        )
        repo = IngestedRepository(
            repo_path="/repo",
            repo_name="AuthRepo",
            files=[sf],
            summary=IngestionSummary(total_files=1),
        )

        rag_res: RAGResponse = engine.ask(
            query="How does authentication work?",
            repo=repo,
        )

        self.assertTrue(rag_res.is_sufficient)
        self.assertEqual(rag_res.query, "How does authentication work?")
        self.assertIn("auth.py:1-2", rag_res.citations[0])
        self.assertGreater(len(rag_res.sources), 0)
        self.assertGreaterEqual(rag_res.latency_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
