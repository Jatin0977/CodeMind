"""
Factory for instantiating vector store backends.
"""

import logging
from typing import Optional
from .base import BaseVectorStore
from .memory_store import InMemoryVectorStore
from .chroma_store import ChromaVectorStore

logger = logging.getLogger(__name__)


def get_vector_store(
    store_type: str = "memory",
    persist_dir: Optional[str] = None,
) -> BaseVectorStore:
    """
    Get a vector store instance.

    Args:
        store_type: 'memory' or 'chroma'.
        persist_dir: Optional directory for ChromaDB persistence.

    Returns:
        BaseVectorStore instance.
    """
    if store_type == "chroma":
        try:
            import chromadb  # noqa: F401
            return ChromaVectorStore(persist_directory=persist_dir)
        except ImportError:
            logger.warning("chromadb is not installed; using InMemoryVectorStore instead.")
            return InMemoryVectorStore()

    return InMemoryVectorStore()
