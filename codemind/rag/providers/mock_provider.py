"""
Deterministic Mock LLM provider for unit tests and offline demonstration.
"""

import re
from typing import Optional
from .base import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):
    """
    Simulates a grounded LLM by parsing evidence chunks in the prompt
    and synthesizing structured responses with accurate [file:start-end] citations.
    """

    def __init__(self, model_name: str = "mock-grounded-llm"):
        self._model_name = model_name
        self.custom_response: Optional[str] = None
        self.should_fail: bool = False

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        if self.should_fail:
            raise RuntimeError("Simulated LLM provider connection failure.")

        if self.custom_response is not None:
            return self.custom_response

        # Check for insufficient context in prompt
        if "No relevant code chunks retrieved" in prompt or "Relevance Score: 0.0" in prompt:
            return "Insufficient context in repository to answer this question accurately."

        # Extract developer question and evidence
        question_match = re.search(r"Developer Question:\s*\n(.*?)(?:\n\nRetrieved Codebase Evidence:|$)", prompt, re.DOTALL)
        if question_match:
            question_text = question_match.group(1).strip().lower()
            # Stop words to ignore during overlap check
            stop_words = {"how", "what", "where", "when", "which", "does", "implemented", "defined", "work", "show", "tell", "explain", "code", "file", "from", "with", "this", "that", "into", "have"}
            q_keywords = {w for w in re.findall(r"\b[a-zA-Z]{3,}\b", question_text) if w not in stop_words}
            evidence_section = prompt.split("Retrieved Codebase Evidence:")[-1].lower() if "Retrieved Codebase Evidence:" in prompt else ""
            ev_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", evidence_section))

            # Check for keyword overlap using root prefix matching (first 4 characters)
            def has_overlap(q_set, ev_set):
                for qk in q_set:
                    q_prefix = qk[:4]
                    for ew in ev_set:
                        if ew.startswith(q_prefix) or qk.startswith(ew[:4]):
                            return True
                return False

            if q_keywords and not has_overlap(q_keywords, ev_words):
                return "Insufficient context in repository to answer this question accurately. No relevant code or documentation was found."

        # Extract evidence citations from prompt
        evidence_pattern = re.compile(r"--- Evidence #\d+ \[([a-zA-Z0-9_\-\.\/\\]+:\d+-\d+)\](?:\s*\(([A-Z]+:\s*[^)]+)\))?")
        matches = evidence_pattern.findall(prompt)

        if not matches:
            return "Insufficient context in repository to answer this question accurately."

        top_tag, top_sym = matches[0]
        top_tag_clean = top_tag.replace("\\", "/")

        answer_lines = [
            f"Based on the repository code in [{top_tag_clean}], the requested functionality is implemented as follows:",
            f"",
            f"1. Primary definition: {top_sym if top_sym else 'relevant block'} is defined at [{top_tag_clean}].",
        ]

        if len(matches) > 1:
            second_tag, second_sym = matches[1]
            second_tag_clean = second_tag.replace("\\", "/")
            answer_lines.append(f"2. Related context: {second_sym if second_sym else 'supporting code'} is located at [{second_tag_clean}].")

        return "\n".join(answer_lines)
