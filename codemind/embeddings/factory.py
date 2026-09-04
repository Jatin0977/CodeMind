"""
Factory for instantiating embedding providers.
"""

import logging
from typing import Optional
from .base import BaseEmbeddingProvider
from .sentence_transformer_provider import SentenceTransformerEmbeddingProvider
from .mock_provider import MockEmbeddingProvider

logger = logging.getLogger(__name__)


def get_embedding_provider(
    provider_type: Optional[str] = None,
    model_name: str = "all-MiniLM-L6-v2",
) -> BaseEmbeddingProvider:
    """
    Get an embedding provider instance.

    Args:
        provider_type: 'sentence_transformers', 'mock', or None (auto-detect).
        model_name: Name of the SentenceTransformer model (e.g., 'all-MiniLM-L6-v2').

    Returns:
        Instance of BaseEmbeddingProvider.
    """
    if provider_type == "mock":
        return MockEmbeddingProvider()

    # Try SentenceTransformers as primary
    try:
        import sentence_transformers  # noqa: F401
        return SentenceTransformerEmbeddingProvider(model_name=model_name)
    except ImportError:
        if provider_type == "sentence_transformers":
            raise
        logger.warning(
            "sentence-transformers not installed; falling back to lightweight deterministic embedding provider."
        )
        return MockEmbeddingProvider()
