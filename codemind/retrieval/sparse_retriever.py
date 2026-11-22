"""
In-memory BM25 sparse retriever for code intelligence.
Implements BM25Okapi ranking with field weighting, subword tokenization,
CamelCase/snake_case splitting, and IDF term weighting for source code chunks.
"""

import re
import math
from typing import List, Dict, Tuple, Optional, Set
from ..chunking.models import CodeChunk


class SparseBM25Retriever:
    """
    High-performance in-memory BM25 sparse keyword retriever.
    Extracts structured identifier tokens from file paths, symbol names,
    signatures, and code bodies to provide fast lexical matching.
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        path_weight: float = 3.0,
        symbol_weight: float = 4.0,
        signature_weight: float = 2.0,
        content_weight: float = 1.0,
    ):
        self.k1 = k1
        self.b = b
        self.path_weight = path_weight
        self.symbol_weight = symbol_weight
        self.signature_weight = signature_weight
        self.content_weight = content_weight

        self._chunks: List[CodeChunk] = []
        self._doc_lengths: List[int] = []
        self._avg_dl: float = 0.0
        self._inverted_index: Dict[str, List[Tuple[int, float]]] = {}  # token -> [(doc_idx, weighted_tf)]
        self._idf: Dict[str, float] = {}

    @property
    def chunks(self) -> List[CodeChunk]:
        """Indexed code chunks."""
        return self._chunks

    def count(self) -> int:
        """Count of indexed documents."""
        return len(self._chunks)

    def clear(self):
        """Reset internal index."""
        self._chunks.clear()
        self._doc_lengths.clear()
        self._avg_dl = 0.0
        self._inverted_index.clear()
        self._idf.clear()

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """
        Tokenize code text into lowercase tokens, expanding CamelCase and snake_case words.
        """
        if not text:
            return []
        raw_words = [w for w in re.findall(r"[a-zA-Z0-9_]+", text) if w.strip("_")]
        tokens: List[str] = []
        for word in raw_words:
            word_lower = word.lower()
            tokens.append(word_lower)
            # CamelCase decomposition: e.g. "AuthService" -> "auth", "service"
            camel_parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)", word)
            if len(camel_parts) > 1:
                for part in camel_parts:
                    p_lower = part.lower()
                    if p_lower != word_lower and len(p_lower) > 1:
                        tokens.append(p_lower)
            # snake_case decomposition: e.g. "auth_service" -> "auth", "service"
            if "_" in word:
                snake_parts = word.split("_")
                for part in snake_parts:
                    p_lower = part.lower()
                    if p_lower != word_lower and len(p_lower) > 1:
                        tokens.append(p_lower)
        return tokens

    def index(self, chunks: List[CodeChunk]) -> int:
        """
        Index a collection of code chunks with field-weighted BM25.
        """
        self.clear()
        if not chunks:
            return 0

        self._chunks = list(chunks)
        N = len(chunks)

        doc_term_freqs: List[Dict[str, float]] = []
        df: Dict[str, int] = {}

        for chunk in chunks:
            path_tokens = self.tokenize(chunk.relative_path)
            symbol_tokens = self.tokenize(chunk.symbol_name or "")
            sig_tokens = self.tokenize(chunk.signature or "")
            content_tokens = self.tokenize(chunk.content or "")

            tf: Dict[str, float] = {}
            for t in path_tokens:
                tf[t] = tf.get(t, 0.0) + self.path_weight
            for t in symbol_tokens:
                tf[t] = tf.get(t, 0.0) + self.symbol_weight
            for t in sig_tokens:
                tf[t] = tf.get(t, 0.0) + self.signature_weight
            for t in content_tokens:
                tf[t] = tf.get(t, 0.0) + self.content_weight

            effective_len = (
                len(path_tokens) * self.path_weight
                + len(symbol_tokens) * self.symbol_weight
                + len(sig_tokens) * self.signature_weight
                + len(content_tokens) * self.content_weight
            )
            self._doc_lengths.append(max(1, int(round(effective_len))))
            doc_term_freqs.append(tf)

            for term in tf.keys():
                df[term] = df.get(term, 0) + 1

        self._avg_dl = sum(self._doc_lengths) / N

        # Compute Robertson-Spärck Jones IDF
        self._idf = {}
        for term, freq in df.items():
            self._idf[term] = math.log(1.0 + (N - freq + 0.5) / (freq + 0.5))

        # Inverted index construction
        self._inverted_index = {}
        for doc_idx, tf_map in enumerate(doc_term_freqs):
            for term, weight in tf_map.items():
                if term not in self._inverted_index:
                    self._inverted_index[term] = []
                self._inverted_index[term].append((doc_idx, weight))

        return N

    def search(self, query: str, top_k: int = 10) -> List[Tuple[CodeChunk, float]]:
        """
        Execute BM25 search for a query string.
        Returns list of (CodeChunk, score) tuples ranked descending by score.
        """
        if not self._chunks:
            return []
        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        scores = [0.0] * len(self._chunks)
        query_terms = set(query_tokens)

        for term in query_terms:
            idf_val = self._idf.get(term, 0.0)
            if idf_val <= 0:
                continue
            postings = self._inverted_index.get(term, [])
            for doc_idx, tf in postings:
                dl = self._doc_lengths[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / self._avg_dl))
                if denom > 0:
                    scores[doc_idx] += idf_val * ((tf * (self.k1 + 1.0)) / denom)

        ranked = [(self._chunks[i], scores[i]) for i in range(len(self._chunks)) if scores[i] > 0]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
