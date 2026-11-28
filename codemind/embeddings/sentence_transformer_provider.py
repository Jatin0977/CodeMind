"""
SentenceTransformers local embedding provider implementation.
"""

import logging
import threading
from typing import List, Optional
from .base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """Generates dense semantic embeddings using local SentenceTransformer models."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: Optional[str] = None):
        self._model_name = model_name
        self._device = device
        self._model = None
        self._fallback = None
        self._dimension = 384  # Default dimension for all-MiniLM-L6-v2 / bge-small-en
        self._load_lock = threading.Lock()

    def _load_model(self):
        """Lazy load the underlying model on first use (thread-safe single load)."""
        if self._model is not None or self._fallback is not None:
            return
        with self._load_lock:
            if self._model is None and self._fallback is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    # Try loading from local cache only (avoid DNS/network hangs in offline/sandboxed environments)
                    self._model = SentenceTransformer(self._model_name, device=self._device, local_files_only=True)

                    # Determine actual dimension dynamically from model
                    if hasattr(self._model, "get_embedding_dimension"):
                        self._dimension = self._model.get_embedding_dimension()
                    elif hasattr(self._model, "get_sentence_embedding_dimension"):
                        self._dimension = self._model.get_sentence_embedding_dimension()
                    logger.info(f"Loaded embedding model: {self._model_name} (dim: {self._dimension})")
                except Exception as e:
                    logger.warning(
                        f"SentenceTransformer model '{self._model_name}' not cached locally ({e}); "
                        "falling back to deterministic mock embedding provider."
                    )
                    from .mock_provider import MockEmbeddingProvider
                    self._fallback = MockEmbeddingProvider(dimension=self._dimension)

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
        if self._fallback is not None:
            return self._fallback.embed_documents(texts)
        # Truncate long blocks beyond ~1500 chars since MiniLM tokenizes max 256 wordpieces anyway
        clipped = [t[:1500] if len(t) > 1500 else t for t in texts]
        embeddings = self._model.encode(
            clipped,
            batch_size=128,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [vec.tolist() for vec in embeddings]

    def embed_query(self, text: str) -> List[float]:
        self._load_model()
        if self._fallback is not None:
            return self._fallback.embed_query(text)
        vec = self._model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vec.tolist()
