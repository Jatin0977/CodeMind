"""
Factory for instantiating LLM completion providers.
"""

import os
import logging
from typing import Optional
from .base import BaseLLMProvider
from .gemini_provider import GeminiLLMProvider
from .local_grounded_provider import LocalGroundedLLMProvider
from .mock_provider import MockLLMProvider

logger = logging.getLogger(__name__)


def get_llm_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseLLMProvider:
    """
    Instantiate appropriate LLM provider (Google Gemini with local grounded fallback).

    Args:
        provider_type: 'gemini', 'local', 'mock', or None (auto-detect).
        model_name: Model identifier.
        api_key: Optional API key.

    Returns:
        BaseLLMProvider instance.
    """
    ptype = (provider_type or "").strip().lower() or None

    if ptype == "mock":
        return MockLLMProvider(model_name=model_name or "mock-grounded-llm")

    if ptype == "local":
        return LocalGroundedLLMProvider(model_name=model_name or "local-grounded-ai")

    clean_key = (api_key or "").strip() or None
    effective_key = clean_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if effective_key:
        return GeminiLLMProvider(
            api_key=effective_key,
            model_name=model_name or "gemini-flash-lite-latest",
        )

    if ptype == "gemini":
        raise ValueError("GEMINI_API_KEY is required for Gemini provider. Set it in .env.")

    logger.info("No GEMINI_API_KEY found in environment. Using LocalGroundedLLMProvider.")
    return LocalGroundedLLMProvider(model_name="local-grounded-ai")
