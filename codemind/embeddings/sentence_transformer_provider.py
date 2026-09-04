"""
SentenceTransformers local embedding provider implementation.
"""

import logging
from typing import List, Optional
from .base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """Generates dense semantic embeddings using local SentenceTransformer models."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: Optional[str] = None):
        self._model_name = model_name
        self._device = device
        self._model = None
        self._dimension = 384  # Default dimension for all-MiniLM-L6-v2 / bge-small-en

    def _load_model(self):
        """Lazy load the underlying model on first use."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name, device=self._device)
                # Determine actual dimension dynamically from model
                if hasattr(self._model, "get_embedding_dimension"):
                    self._dimension = self._model.get_embedding_dimension()
                elif hasattr(self._model, "get_sentence_embedding_dimension"):
                    self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(f"Loaded embedding model: {self._model_name} (dim: {self._dimension})")
            except ImportError as e:
                raise ImportError(
                    "The 'sentence-transformers' package is required for SentenceTransformerEmbeddingProvider. "
                    "Install it with: pip install sentence-transformers"
                ) from e

    @property
    def dimension(self) -> int:
        if self._model is not None:
            if hasattr(self._model, "get_embedding_dimension"):
                return self._model.get_embedding_dimension()
            elif hasattr(self._model, "get_sentence_embedding_dimension"):
                return self._model.get_sentence_embedding_dimension()
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        self._load_model()
        embeddings = self._model.encode(
            texts,
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [vec.tolist() for vec in embeddings]

    def embed_query(self, text: str) -> List[float]:
        self._load_model()
        vec = self._model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vec.tolist()
