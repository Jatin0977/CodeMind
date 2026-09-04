"""
Prompt templates and evidence formatting for Grounded Codebase RAG.
"""

import re
from typing import List
from ..vector_store.base import SearchResult

SYSTEM_INSTRUCTION = """You are CodeMind, an expert Software Engineering Intelligence system.
Your job is to answer the developer's question accurately and objectively using ONLY the retrieved repository evidence provided below.

Strict Grounding Rules:
1. Base your answer EXCLUSIVELY on the code, docstrings, classes, functions, and documentation present in the provided evidence.
2. Every major assertion, code explanation, or workflow description MUST include an inline citation in the exact format: [relative_path:start_line-end_line]. For example: [codemind/ingestion/file_filter.py:17-29].
3. Do NOT invent functions, parameters, classes, or architecture not present in the evidence.
4. If the provided evidence does not contain enough information to answer the question, do not speculate or hallucinate. State clearly:
   "Insufficient context in repository to answer this question accurately." and explain what is missing.
5. Provide clear, concise explanations with relevant code references and short illustrative snippets where helpful.
"""


def format_evidence_context(results: List[SearchResult]) -> str:
    """Format retrieved search results into a clean structured evidence text block."""
    if not results:
        return "No relevant code chunks retrieved from repository."

    evidence_blocks: List[str] = []
    for idx, res in enumerate(results, start=1):
        chunk = res.chunk
        tag = f"[{chunk.relative_path}:{chunk.start_line}-{chunk.end_line}]"
        sym_info = f" ({chunk.chunk_type.upper()}: {chunk.symbol_name})" if chunk.symbol_name else ""
        sig_info = f"\nSignature: {chunk.signature}" if chunk.signature else ""

        block = f"--- Evidence #{idx} {tag}{sym_info} (Relevance Score: {res.score:.3f}) ---{sig_info}\n{chunk.content}\n"
        evidence_blocks.append(block)

    return "\n".join(evidence_blocks)


def extract_citations(text: str) -> List[str]:
    """Extract all [path/to/file.ext:start-end] citation tags from text in discovery order."""
    pattern = re.compile(r"\[([a-zA-Z0-9_\-\.\/\\]+:\d+-\d+)\]")
    matches = pattern.findall(text)
    unique_citations: List[str] = []
    seen = set()

    for m in matches:
        normalized = m.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            unique_citations.append(normalized)

    return unique_citations
