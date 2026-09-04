"""
RAG Engine orchestrating semantic retrieval, grounded prompt generation, and LLM inference.
"""

import time
import logging
from typing import Optional, List, Dict, Any

from .models import RAGResponse
from .prompt_templates import SYSTEM_INSTRUCTION, format_evidence_context, extract_citations
from .providers.base import BaseLLMProvider
from .providers.factory import get_llm_provider
from ..retrieval.retriever import SemanticRetriever
from ..ingestion.models import IngestedRepository

logger = logging.getLogger(__name__)


class RAGEngine:
    """End-to-end Grounded RAG system for repository question answering."""

    def __init__(
        self,
        retriever: Optional[SemanticRetriever] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        min_relevance_threshold: float = 0.15,
    ):
        self.retriever = retriever or SemanticRetriever()
        self.llm_provider = llm_provider or get_llm_provider()
        self.min_relevance_threshold = min_relevance_threshold

    def ask(
        self,
        query: str,
        repo: Optional[IngestedRepository] = None,
        top_k: int = 4,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> RAGResponse:
        """
        Answer a developer question using strictly grounded codebase evidence.

        Args:
            query: Natural language question.
            repo: Optional IngestedRepository (indexes if not already indexed).
            top_k: Number of evidence chunks to retrieve.
            filter_dict: Optional metadata filters.

        Returns:
            RAGResponse containing grounded answer and citations.
        """
        t0 = time.time()
        query_clean = query.strip()

        if not query_clean:
            return RAGResponse(
                query=query,
                answer="Please provide a valid non-empty question.",
                is_sufficient=False,
                model_name=self.llm_provider.model_name,
                latency_ms=0.0,
            )

        # Index repository if provided and vector store is empty
        if repo is not None and self.retriever.vector_store.count() == 0:
            self.retriever.index_repository(repo)

        # 1. Retrieve top-k evidence chunks
        results = self.retriever.search(query_clean, top_k=top_k, filter_dict=filter_dict)

        # Check if no chunks found or relevance is too low
        if not results or (results and results[0].score < self.min_relevance_threshold):
            latency = (time.time() - t0) * 1000
            return RAGResponse(
                query=query_clean,
                answer="Insufficient context in repository to answer this question accurately. No relevant code or documentation was found.",
                citations=[],
                sources=results,
                is_sufficient=False,
                model_name=self.llm_provider.model_name,
                latency_ms=latency,
            )

        # 2. Format evidence context block
        evidence_text = format_evidence_context(results)

        # 3. Assemble User Prompt
        user_prompt = f"""Developer Question:
{query_clean}

Retrieved Codebase Evidence:
{evidence_text}

Provide an accurate, grounded answer with inline citations in the format [relative/path.py:start_line-end_line].
"""

        # 4. Invoke LLM Provider
        try:
            answer = self.llm_provider.generate(
                prompt=user_prompt,
                system_instruction=SYSTEM_INSTRUCTION,
            )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            latency = (time.time() - t0) * 1000
            return RAGResponse(
                query=query_clean,
                answer=f"Error generating answer from LLM provider: {e}",
                citations=[],
                sources=results,
                is_sufficient=False,
                model_name=self.llm_provider.model_name,
                latency_ms=latency,
            )

        # 5. Extract citations and detect insufficiency
        citations = extract_citations(answer)

        # If model generated an answer grounded in top result but forgot brackets, add top result citation
        if not citations and results and "insufficient context" not in answer.lower():
            top_chunk = results[0].chunk
            citations = [f"{top_chunk.relative_path}:{top_chunk.start_line}-{top_chunk.end_line}"]

        is_sufficient = "insufficient context" not in answer.lower()
        latency = (time.time() - t0) * 1000

        return RAGResponse(
            query=query_clean,
            answer=answer,
            citations=citations,
            sources=results,
            is_sufficient=is_sufficient,
            model_name=self.llm_provider.model_name,
            latency_ms=latency,
        )
