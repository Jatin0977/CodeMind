"""
Base interface for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseLLMProvider(ABC):
    """Abstract interface for large language model completion providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns the name of the LLM model."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """
        Generate text response from the model.

        Args:
            prompt: User prompt containing question and evidence.
            system_instruction: Optional system level instruction.
            temperature: Sampling temperature (default: 0.2 for deterministic code QA).

        Returns:
            Generated response string.
        """
        pass
