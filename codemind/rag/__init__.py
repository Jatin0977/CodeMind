"""
Grounded Codebase RAG subpackage for CodeMind.
"""

from .models import RAGResponse
from .engine import RAGEngine
from .providers.base import BaseLLMProvider
from .providers.gemini_provider import GeminiLLMProvider
from .providers.mock_provider import MockLLMProvider
from .providers.factory import get_llm_provider
from .prompt_templates import format_evidence_context, extract_citations, SYSTEM_INSTRUCTION

__all__ = [
    "RAGResponse",
    "RAGEngine",
    "BaseLLMProvider",
    "GeminiLLMProvider",
    "MockLLMProvider",
    "get_llm_provider",
    "format_evidence_context",
    "extract_citations",
    "SYSTEM_INSTRUCTION",
]
