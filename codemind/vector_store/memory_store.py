"""
In-memory vector store with cosine similarity calculation.
"""

import math
from typing import List, Optional, Dict, Any, Tuple
from .base import BaseVectorStore, SearchResult
from ..chunking.models import CodeChunk


class InMemoryVectorStore(BaseVectorStore):
    """Fast in-memory vector store with cosine similarity ranking."""

    def __init__(self):
        self._chunks: List[CodeChunk] = []
        self._embeddings: List[List[float]] = []

    def add(self, chunks: List[CodeChunk], embeddings: List[List[float]]):
        """Add chunks and embedding vectors to store."""
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks count ({len(chunks)}) must match embeddings count ({len(embeddings)})"
            )
        self._chunks.extend(chunks)
        self._embeddings.extend(embeddings)

    def count(self) -> int:
        return len(self._chunks)

    def clear(self):
        self._chunks.clear()
        self._embeddings.clear()

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Compute cosine similarities and return top-k matches."""
        if not self._chunks or not query_vector:
            return []

        q_norm = math.sqrt(sum(x * x for x in query_vector))
        if q_norm == 0:
            return []

        scored_results: List[Tuple[float, CodeChunk]] = []

        for chunk, doc_vec in zip(self._chunks, self._embeddings):
            # Check metadata filters if specified
            if filter_dict:
                match = True
                for k, v in filter_dict.items():
                    if getattr(chunk, k, None) != v and chunk.metadata.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            dot = 0.0
            doc_norm_sq = 0.0
            for a, b in zip(query_vector, doc_vec):
                dot += a * b
                doc_norm_sq += b * b

            d_norm = math.sqrt(doc_norm_sq)
            cos_sim = (dot / (q_norm * d_norm)) if (q_norm * d_norm) > 0 else 0.0
            # Clamp to [0.0, 1.0]
            score = max(0.0, min(1.0, cos_sim))
            scored_results.append((score, chunk))

        # Sort descending by score
        scored_results.sort(key=lambda x: x[0], reverse=True)

        results: List[SearchResult] = []
        for rank, (score, chunk) in enumerate(scored_results[:top_k], start=1):
            results.append(SearchResult(chunk=chunk, score=score, rank=rank))

        return results
