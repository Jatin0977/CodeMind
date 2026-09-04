"""
Base vector store interface and SearchResult model.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from ..chunking.models import CodeChunk


@dataclass
class SearchResult:
    """Represents a matched chunk from semantic vector search."""

    chunk: CodeChunk
    score: float  # Cosine similarity score (0.0 to 1.0)
    rank: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert SearchResult to dictionary."""
        return {
            "rank": self.rank,
            "score": round(self.score, 4),
            "chunk": self.chunk.to_dict(),
        }


class BaseVectorStore(ABC):
    """Abstract interface for local and persistent vector stores."""

    @abstractmethod
    def add(self, chunks: List[CodeChunk], embeddings: List[List[float]]):
        """
        Index chunks and their corresponding embedding vectors.

        Args:
            chunks: List of CodeChunk instances.
            embeddings: List of embedding vectors matching chunks.
        """
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Search for top_k most similar chunks to query_vector.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of results to return.
            filter_dict: Optional metadata key-value filters.

        Returns:
            List of SearchResult objects ordered by descending score.
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """Returns total number of chunks stored."""
        pass

    @abstractmethod
    def clear(self):
        """Clear all stored vectors and chunks."""
        pass
