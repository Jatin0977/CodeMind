"""
Factory for instantiating LLM completion providers.
"""

import os
import logging
from typing import Optional
from .base import BaseLLMProvider
from .gemini_provider import GeminiLLMProvider
from .mock_provider import MockLLMProvider

logger = logging.getLogger(__name__)


def get_llm_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseLLMProvider:
    """
    Instantiate appropriate LLM provider.

    Args:
        provider_type: 'gemini', 'mock', or None (auto-detect).
        model_name: Model identifier.
        api_key: Optional API key.

    Returns:
        BaseLLMProvider instance.
    """
    if provider_type == "mock":
        return MockLLMProvider(model_name=model_name or "mock-grounded-llm")

    # Check for Gemini API key
    effective_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if effective_key:
        return GeminiLLMProvider(
            api_key=effective_key,
            model_name=model_name or "gemini-2.5-flash",
        )

    if provider_type == "gemini":
        raise ValueError("GEMINI_API_KEY is required for Gemini provider but not found.")

    logger.warning("No GEMINI_API_KEY found in environment. Using MockLLMProvider for offline mode.")
    return MockLLMProvider(model_name="mock-grounded-llm")
