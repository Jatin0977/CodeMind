"""
Factory for instantiating embedding providers.
"""

import os
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
    if provider_type == "mock" or os.environ.get("CODEMIND_EMBEDDING_PROVIDER") == "mock":
        return MockEmbeddingProvider()

    # Try SentenceTransformers as primary without eagerly importing torch DLLs
    try:
        import importlib.util
        if importlib.util.find_spec("sentence_transformers") is not None:
            return SentenceTransformerEmbeddingProvider(model_name=model_name)
    except Exception:
        pass

    if provider_type == "sentence_transformers":
        raise ImportError("sentence-transformers is not available.")
    logger.warning(
        "sentence-transformers not installed; falling back to lightweight deterministic embedding provider."
    )
    return MockEmbeddingProvider()
