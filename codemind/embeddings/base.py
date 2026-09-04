"""
Base interface for embedding providers.
"""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingProvider(ABC):
    """Abstract base class for generating vector embeddings from text."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Returns the embedding vector dimensionality."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns the name or identifier of the underlying model."""
        pass

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embedding vectors for a list of document strings.

        Args:
            texts: List of text chunks.

        Returns:
            List of float vectors, each of length self.dimension.
        """
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        Generate an embedding vector for a single query string.

        Args:
            text: Query string.

        Returns:
            Float vector of length self.dimension.
        """
        pass
