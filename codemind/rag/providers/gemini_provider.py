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
    """Integrates with Google Gemini API for code grounding and answer synthesis."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
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
        return self._model_name

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Invoke Gemini API to generate completion."""
        # Try official SDK first if available
        try:
            from google import genai
            client = genai.Client(api_key=self._api_key)
            config = {"temperature": temperature}
            if system_instruction:
                config["system_instruction"] = system_instruction
            response = client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=config,
            )
            return response.text.strip()
        except ImportError:
            pass

        # Fallback to direct HTTP API (zero external library dependency)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model_name}:generateContent?key={self._api_key}"

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
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
