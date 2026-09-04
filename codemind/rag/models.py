"""
Data models for Grounded RAG responses and citations.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from ..vector_store.base import SearchResult


@dataclass
class RAGResponse:
    """Represents a generated grounded answer backed by retrieved code evidence."""

    query: str
    answer: str
    citations: List[str] = field(default_factory=list)  # e.g., ['codemind/ingestion/file_filter.py:17-29']
    sources: List[SearchResult] = field(default_factory=list)  # Underlying retrieved evidence
    is_sufficient: bool = True  # False if repository lacked context
    model_name: str = "unknown"
    latency_ms: float = 0.0

    def to_dict(self, include_sources: bool = True) -> Dict[str, Any]:
        """Convert RAGResponse to a serializable dictionary."""
        data = {
            "query": self.query,
            "answer": self.answer,
            "citations": self.citations,
            "is_sufficient": self.is_sufficient,
            "model_name": self.model_name,
            "latency_ms": round(self.latency_ms, 2),
        }
        if include_sources:
            data["sources"] = [s.to_dict() for s in self.sources]
        return data
