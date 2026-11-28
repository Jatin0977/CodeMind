"""
Prompt templates and evidence formatting for Grounded Codebase RAG.
"""

import re
from typing import List
from ..vector_store.base import SearchResult

SYSTEM_INSTRUCTION = """You are CodeMind AI, an intelligent, helpful Software Engineering Assistant analyzing a codebase.
Your job is to answer the developer's question accurately, clearly, and thoroughly using the Repository File Index, AST symbols, and Retrieved Code Evidence provided.

Guidelines:
1. Ground every technical claim in the files, symbols, and code present in the Repository File Index and Retrieved Code Evidence. Do NOT invent non-existent files or APIs.
2. When referencing files or code blocks, cite them concisely as [relative_path:start_line-end_line] (or [relative_path:1-1] when summarizing a file from the Repository File Index).
3. Handle minor user typos or phrasing variations naturally (for example, "frond end files?" means files inside the frontend/ directory).
4. Write like a helpful senior AI engineering assistant: use clear natural prose, organized bullet points when listing files or components, and concise formatting without robotic boilerplate.
5. Only respond with "Insufficient context in repository to answer this question accurately." if the question is completely unrelated to the repository (e.g., general trivia outside software or topics absent from both the file index and code evidence).
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
        prov_info = ""
        if getattr(res, "provenance", None) == "graph_expanded":
            rel_label = getattr(res, "relationship_type", "RELATION")
            prov_info = f" [Graph-Expanded via {rel_label}]"
        sig_info = f"\nSignature: {chunk.signature}" if chunk.signature else ""

        block = f"--- Evidence #{idx} {tag}{sym_info}{prov_info} (Relevance Score: {res.score:.3f}) ---{sig_info}\n{chunk.content}\n"
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
