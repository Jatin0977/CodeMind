"""
Google Gemini API LLM provider implementation.
"""

import os
import json
import urllib.request
import urllib.error
import logging
from typing import Optional
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


class GeminiLLMProvider(BaseLLMProvider):
    """Integrates with Google Gemini API for fast code grounding and answer synthesis."""

    _cached_working_model: Optional[str] = None

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-flash-lite-latest",
    ):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._model_name = model_name

        if not self._api_key:
            raise ValueError(
                "Gemini API key not found. Please set GEMINI_API_KEY environment variable "
                "or pass api_key parameter to GeminiLLMProvider."
            )

    @property
    def model_name(self) -> str:
        return self._cached_working_model or self._model_name

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Invoke Gemini API quickly using cached working model + fast Flash cascade on 503/429."""
        primary = GeminiLLMProvider._cached_working_model or self._model_name
        candidates_order = [primary]
        for alt in ("gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"):
            if alt not in candidates_order:
                candidates_order.append(alt)

        last_err: Optional[Exception] = None
        for idx, model_id in enumerate(candidates_order):
            try:
                out = self._call_model_rest(model_id, prompt, system_instruction, temperature)
                GeminiLLMProvider._cached_working_model = model_id
                return out
            except Exception as e:
                last_err = e
                msg = str(e).upper()
                is_transient = any(tok in msg for tok in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND", "NOT_FOUND", "404", "TIMED OUT", "TIMEOUT"))
                if is_transient and idx < len(candidates_order) - 1:
                    logger.warning(f"Gemini model '{model_id}' unavailable ({e}); trying fallback model.")
                    if GeminiLLMProvider._cached_working_model == model_id:
                        GeminiLLMProvider._cached_working_model = None
                    continue
                if is_transient:
                    logger.warning(f"All Gemini endpoints temporarily overloaded ({e}); falling back to LocalGroundedLLMProvider.")
                    from .local_grounded_provider import LocalGroundedLLMProvider
                    return LocalGroundedLLMProvider().generate(prompt, system_instruction, temperature)
                raise

        raise RuntimeError(f"Gemini API failed: {last_err}")

    def _call_model_rest(
        self,
        model_id: str,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Execute single fast completion call via direct REST without SDK retry stalls."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={self._api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))

            candidates = resp_data.get("candidates", [])
            if not candidates:
                return "Insufficient context or response filtered by safety settings."

            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()

            return "No response content returned."

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Gemini API HTTPError ({e.code}): {err_body}")
            raise RuntimeError(f"Gemini API Error {e.code}: {err_body}") from e
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise RuntimeError(f"Gemini API connection error: {e}") from e
