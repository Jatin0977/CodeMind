"""
ChromaDB persistent vector store implementation.
"""

import logging
from typing import List, Optional, Dict, Any
from .base import BaseVectorStore, SearchResult
from ..chunking.models import CodeChunk

logger = logging.getLogger(__name__)


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB vector store backend."""

    def __init__(self, collection_name: str = "codemind_chunks", persist_directory: Optional[str] = None):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None

    def _init_chroma(self):
        """Lazy initialize ChromaDB collection."""
        if self._collection is None:
            try:
                import chromadb
                if self.persist_directory:
                    self._client = chromadb.PersistentClient(path=self.persist_directory)
                else:
                    self._client = chromadb.Client()
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            except ImportError as e:
                raise ImportError(
                    "ChromaDB is required for ChromaVectorStore. Install it with: pip install chromadb"
                ) from e

    def add(self, chunks: List[CodeChunk], embeddings: List[List[float]]):
        if not chunks:
            return
        self._init_chroma()

        ids = [f"{c.chunk_id}_{i}" for i, c in enumerate(chunks)]
        documents = [c.content for c in chunks]
        metadatas = [
            {
                "file_path": c.file_path,
                "relative_path": c.relative_path,
                "language": c.language,
                "chunk_type": c.chunk_type,
                "symbol_name": c.symbol_name or "",
                "parent_symbol": c.parent_symbol or "",
                "start_line": c.start_line,
                "end_line": c.end_line,
                "signature": c.signature or "",
            }
            for c in chunks
        ]

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def count(self) -> int:
        self._init_chroma()
        return self._collection.count()

    def clear(self):
        self._init_chroma()
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        self._init_chroma()
        res = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=filter_dict if filter_dict else None,
        )

        results: List[SearchResult] = []
        if not res or not res["ids"] or not res["ids"][0]:
            return results

        docs = res["documents"][0]
        metas = res["metadatas"][0]
        distances = res["distances"][0] if "distances" in res and res["distances"] else [0.0] * len(docs)

        for rank, (doc, meta, dist) in enumerate(zip(docs, metas, distances), start=1):
            # Chroma returns cosine distance (1 - similarity); convert to similarity
            sim_score = max(0.0, min(1.0, 1.0 - dist))
            chunk = CodeChunk.create(
                file_path=meta.get("file_path", ""),
                relative_path=meta.get("relative_path", ""),
                language=meta.get("language", ""),
                chunk_type=meta.get("chunk_type", ""),
                start_line=int(meta.get("start_line", 1)),
                end_line=int(meta.get("end_line", 1)),
                content=doc,
                symbol_name=meta.get("symbol_name") or None,
                parent_symbol=meta.get("parent_symbol") or None,
                signature=meta.get("signature") or None,
            )
            results.append(SearchResult(chunk=chunk, score=sim_score, rank=rank))

        return results
