"""
Unit tests for embedding providers, in-memory vector store, and semantic retriever.
"""

import unittest
from codemind.chunking.models import CodeChunk
from codemind.ingestion.models import SourceFile, IngestedRepository, IngestionSummary
from codemind.embeddings.mock_provider import MockEmbeddingProvider
from codemind.vector_store.memory_store import InMemoryVectorStore
from codemind.vector_store.base import SearchResult
from codemind.retrieval.retriever import SemanticRetriever


class TestRetrieval(unittest.TestCase):
    """Test embedding vectors, vector indexing, and semantic search."""

    def test_mock_embedding_provider_dimension_and_norm(self):
        provider = MockEmbeddingProvider(dimension=64)
        self.assertEqual(provider.dimension, 64)

        docs = ["def authenticate_user(username, password): pass", "class DatabaseConnection: pass"]
        vectors = provider.embed_documents(docs)

        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 64)
        self.assertEqual(len(vectors[1]), 64)

        # Vector should be L2 unit normalized
        norm = sum(x * x for x in vectors[0]) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=4)

        q_vec = provider.embed_query("authenticate user")
        self.assertEqual(len(q_vec), 64)

    def test_in_memory_vector_store(self):
        store = InMemoryVectorStore()
        provider = MockEmbeddingProvider(dimension=32)

        c1 = CodeChunk.create(
            file_path="/repo/auth.py",
            relative_path="auth.py",
            language="python",
            chunk_type="function",
            start_line=1,
            end_line=10,
            content="def login(user, pwd): return True",
            symbol_name="login",
        )
        c2 = CodeChunk.create(
            file_path="/repo/db.py",
            relative_path="db.py",
            language="python",
            chunk_type="class",
            start_line=1,
            end_line=20,
            content="class Database: def connect(self): pass",
            symbol_name="Database",
        )

        embeddings = provider.embed_documents([c1.content, c2.content])
        store.add([c1, c2], embeddings)

        self.assertEqual(store.count(), 2)

        # Search for login
        q_vec = provider.embed_query("login user")
        results = store.search(q_vec, top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.symbol_name, "login")
        self.assertTrue(0.0 <= results[0].score <= 1.0)
        self.assertEqual(results[0].rank, 1)

    def test_semantic_retriever_e2e(self):
        embedder = MockEmbeddingProvider(dimension=48)
        store = InMemoryVectorStore()
        retriever = SemanticRetriever(embedding_provider=embedder, vector_store=store)

        # Construct a synthetic repository
        sf1 = SourceFile(
            file_path="/repo/auth.py",
            relative_path="auth.py",
            file_name="auth.py",
            extension=".py",
            language="python",
            file_size=200,
            line_count=10,
            content="""def authenticate_user(username: str, token: str) -> bool:
    \"\"\"Validate credentials and tokens.\"\"\"
    return verify_token(token)
""",
            checksum="chk1",
        )

        sf2 = SourceFile(
            file_path="/repo/filter.py",
            relative_path="filter.py",
            file_name="filter.py",
            extension=".py",
            language="python",
            file_size=250,
            line_count=12,
            content="""class IgnoreFilter:
    \"\"\"Filter ignored directories and binary extensions.\"\"\"
    def is_ignored(self, path: str) -> bool:
        return path.startswith('.git')
""",
            checksum="chk2",
        )

        repo = IngestedRepository(
            repo_path="/repo",
            repo_name="TestRepo",
            files=[sf1, sf2],
            summary=IngestionSummary(total_files=2),
        )

        indexed_count = retriever.index_repository(repo)
        self.assertGreater(indexed_count, 0)

        # Query 1: Authentication
        auth_results = retriever.search("how to authenticate user tokens", top_k=2)
        self.assertGreater(len(auth_results), 0)
        top_auth = auth_results[0]
        self.assertIn("auth.py", top_auth.chunk.relative_path)
        self.assertIn("authenticate_user", top_auth.chunk.symbol_name)
        self.assertGreater(top_auth.score, 0.0)

        # Query 2: Filter directories
        filter_results = retriever.search("filter ignored directories and binary files", top_k=2)
        self.assertGreater(len(filter_results), 0)
        top_filter = filter_results[0]
        self.assertIn("filter.py", top_filter.chunk.relative_path)


if __name__ == "__main__":
    unittest.main()
