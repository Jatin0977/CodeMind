"""
Lightweight deterministic embedding provider for fast testing and degraded offline environments.
"""

import math
import hashlib
from typing import List
from .base import BaseEmbeddingProvider


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Generates deterministic pseudo-semantic embeddings based on token hashing.
    Used for sub-millisecond unit testing and offline test execution.
    """

    def __init__(self, dimension: int = 64):
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return "mock-deterministic-embedder"

    def _text_to_vector(self, text: str) -> List[float]:
        """Generate a deterministic unit vector from text tokens."""
        vec = [0.0] * self._dimension
        tokens = text.lower().replace("\n", " ").split()
        if not tokens:
            vec[0] = 1.0
            return vec

        for token in tokens:
            # Clean token (letters and digits only)
            clean_token = "".join(c for c in token if c.isalnum() or c == "_")
            if not clean_token:
                continue
            token_hash = int(hashlib.md5(clean_token.encode("utf-8")).hexdigest(), 16)
            idx = token_hash % self._dimension
            vec[idx] += 1.0 + math.log(1.0 + len(clean_token))

        # Normalize to unit length (L2 norm)
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0

        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._text_to_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._text_to_vector(text)
