"""
Local grounded answer synthesizer for zero-key / offline AI question answering.
Synthesizes structured technical explanations directly from retrieved codebase evidence.
"""

import re
from typing import List, Optional, Tuple
from .base import BaseLLMProvider


_EVIDENCE_HEADER_RE = re.compile(
    r"--- Evidence #(\d+) \[([^\]]+)\](?:\s*\(([^)]+)\))?(?:\s*\|\s*Relevance Score:\s*([0-9.]+))? ---"
)


class LocalGroundedLLMProvider(BaseLLMProvider):
    """
    Synthesizes structured, citation-grounded answers directly from retrieved code chunks
    without requiring an external LLM API key.
    """

    def __init__(self, model_name: str = "local-grounded-ai"):
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        if "No relevant code chunks retrieved" in prompt or "--- Evidence #1" not in prompt:
            return "Insufficient context in repository to answer this question accurately."

        q_match = re.search(
            r"Developer Question:\s*\n(.*?)(?:\n\nRetrieved Codebase Evidence:|$)",
            prompt,
            re.DOTALL,
        )
        question_text = q_match.group(1).strip() if q_match else ""

        ev_section = (
            prompt.split("Retrieved Codebase Evidence:", 1)[-1]
            if "Retrieved Codebase Evidence:" in prompt
            else prompt
        )

        # Split into evidence blocks
        blocks: List[Tuple[str, str, str, float, str]] = []
        matches = list(_EVIDENCE_HEADER_RE.finditer(ev_section))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(ev_section)
            body = ev_section[start:end].strip()
            cit = m.group(2).replace("\\", "/")
            sym = (m.group(3) or "").strip()
            score = float(m.group(4)) if m.group(4) else 0.0
            blocks.append((m.group(1), cit, sym, score, body))

        if not blocks:
            return "Insufficient context in repository to answer this question accurately."

        # Extract concise prose sentences summarizing retrieved files/symbols
        clauses: List[str] = []
        seen_files = set()

        for _, cit, sym, score, body in blocks[:4]:
            rel_file = cit.split(":", 1)[0]
            seen_files.add(rel_file)
            lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("# File:")]
            doc_line = ""
            for ln in lines:
                if ln.startswith('"""') or ln.startswith("'''") or ln.startswith("//") or ln.startswith("/**"):
                    cleaned = ln.strip('"\'/* ').strip()
                    if len(cleaned) > 10:
                        doc_line = cleaned
                        break

            if sym and doc_line:
                clauses.append(f"`{sym}` in [{cit}] handles {doc_line.rstrip('.').lower()}")
            elif sym:
                clauses.append(f"`{sym}` is defined in [{cit}]")
            elif doc_line:
                clauses.append(f"[{cit}] implements {doc_line.rstrip('.').lower()}")
            else:
                clauses.append(f"`{rel_file}` provides relevant configuration and logic at [{cit}]")

        if len(clauses) == 1:
            return f"Based on the repository evidence, {clauses[0]}."
        joined = "; ".join(clauses[:3])
        return f"In this repository, the relevant functionality spans **{len(seen_files)} file(s)**: {joined}."
