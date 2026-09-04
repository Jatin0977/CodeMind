"""
Semantic retriever coordinating embedding generation and vector store search.
"""

import logging
from typing import List, Optional, Dict, Any

from ..chunking.models import CodeChunk
from ..chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from ..parsing.parser_factory import GLOBAL_PARSER_FACTORY
from ..ingestion.models import IngestedRepository, SourceFile
from ..embeddings.base import BaseEmbeddingProvider
from ..embeddings.factory import get_embedding_provider
from ..vector_store.base import BaseVectorStore, SearchResult
from ..vector_store.factory import get_vector_store

logger = logging.getLogger(__name__)


class SemanticRetriever:
    """Orchestrates codebase indexing, embedding, and semantic similarity search."""

    def __init__(
        self,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        vector_store: Optional[BaseVectorStore] = None,
    ):
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.vector_store = vector_store or get_vector_store()
        self._all_chunks: List[CodeChunk] = []

    @property
    def chunks(self) -> List[CodeChunk]:
        """All currently indexed code chunks."""
        return self._all_chunks

    def index_chunks(self, chunks: List[CodeChunk]) -> int:
        """
        Embed and index a list of pre-extracted code/documentation chunks.

        Args:
            chunks: List of CodeChunk instances.

        Returns:
            Number of indexed chunks.
        """
        if not chunks:
            self.vector_store.clear()
            self._all_chunks = []
            return 0

        # Construct contextual embedding strings
        chunk_texts: List[str] = []
        for c in chunks:
            header_prefix = f"# File: {c.relative_path}\n"
            if c.symbol_name:
                header_prefix += f"# Symbol: {c.symbol_name}\n"
            if c.signature:
                header_prefix += f"# Signature: {c.signature}\n"
            full_text = f"{header_prefix}\n{c.content}"
            chunk_texts.append(full_text)

        # Generate dense embeddings
        embeddings = self.embedding_provider.embed_documents(chunk_texts)

        # Store in vector store
        self.vector_store.clear()
        self.vector_store.add(chunks, embeddings)
        self._all_chunks = chunks

        logger.info(f"Successfully indexed {len(chunks)} chunks in vector store.")
        return len(chunks)

    def index_repository(self, repo: IngestedRepository) -> int:
        """
        Chunk and embed all source and documentation files in the repository.

        Args:
            repo: Ingested repository model.

        Returns:
            Number of successfully indexed chunks.
        """
        all_chunks: List[CodeChunk] = []

        for source_file in repo.files:
            parsed = GLOBAL_PARSER_FACTORY.parse(source_file)
            file_chunks = GLOBAL_CHUNKER_FACTORY.chunk_file(source_file, parsed)
            all_chunks.extend(file_chunks)

        return self.index_chunks(all_chunks)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Perform semantic similarity search for a natural language query.

        Args:
            query: Natural language query (e.g. 'how does authentication work').
            top_k: Number of most relevant code chunks to return.
            filter_dict: Optional metadata filter dict.

        Returns:
            Ranked list of SearchResult instances with similarity scores and line spans.
        """
        if not query.strip():
            return []

        query_vector = self.embedding_provider.embed_query(query)
        return self.vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            filter_dict=filter_dict,
        )
