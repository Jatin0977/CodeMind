"""
Documentation chunker for Markdown, reStructuredText, and plain text files.
"""

import re
from typing import List, Optional
from .base_chunker import BaseChunker
from .models import CodeChunk
from ..ingestion.models import SourceFile
from ..parsing.base_parser import ParsedFile


class DocChunker(BaseChunker):
    """Splits documentation files into semantic section chunks based on markdown headings."""

    @property
    def supported_language(self) -> str:
        return "markdown"

    def chunk(
        self,
        source_file: SourceFile,
        parsed_file: Optional[ParsedFile] = None,
    ) -> List[CodeChunk]:
        """Split documentation into header-based sections."""
        raw_lines = source_file.content.splitlines(keepends=True)
        if not raw_lines:
            return []

        # Find all markdown header lines: '# Title', '## Section', '### Sub'
        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
        heading_indices: List[tuple[int, int, str]] = []  # (line_no_1_indexed, level, title)

        for line_idx, line in enumerate(raw_lines):
            line_str = line.strip()
            match = header_pattern.match(line_str)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                heading_indices.append((line_idx + 1, level, title))

        # If no headings found, return as a single document chunk or paragraph blocks
        if not heading_indices:
            return [
                CodeChunk.create(
                    file_path=source_file.file_path,
                    relative_path=source_file.relative_path,
                    language=source_file.language,
                    chunk_type="doc_section",
                    start_line=1,
                    end_line=len(raw_lines),
                    content=source_file.content.strip(),
                    symbol_name=source_file.file_name,
                    signature=f"# {source_file.file_name}",
                    metadata={"level": 1},
                )
            ]

        chunks: List[CodeChunk] = []

        # Preamble before first heading if any
        first_heading_line = heading_indices[0][0]
        if first_heading_line > 1:
            preamble_content = "".join(raw_lines[0 : first_heading_line - 1]).strip()
            if preamble_content:
                chunks.append(
                    CodeChunk.create(
                        file_path=source_file.file_path,
                        relative_path=source_file.relative_path,
                        language=source_file.language,
                        chunk_type="doc_section",
                        start_line=1,
                        end_line=first_heading_line - 1,
                        content=preamble_content,
                        symbol_name=f"{source_file.file_name}:preamble",
                        signature=f"# {source_file.file_name} Overview",
                        metadata={"level": 0},
                    )
                )

        # Process each heading section
        heading_stack: List[tuple[int, str]] = []  # (level, title)

        for idx, (h_line, h_level, h_title) in enumerate(heading_indices):
            # Determine end line
            if idx + 1 < len(heading_indices):
                next_h_line = heading_indices[idx + 1][0]
                end_line = next_h_line - 1
            else:
                end_line = len(raw_lines)

            # Maintain parent heading hierarchy
            while heading_stack and heading_stack[-1][0] >= h_level:
                heading_stack.pop()

            parent_symbol = heading_stack[-1][1] if heading_stack else None
            heading_stack.append((h_level, h_title))

            section_content = "".join(raw_lines[h_line - 1 : end_line]).strip()
            if section_content:
                chunks.append(
                    CodeChunk.create(
                        file_path=source_file.file_path,
                        relative_path=source_file.relative_path,
                        language=source_file.language,
                        chunk_type="doc_section",
                        start_line=h_line,
                        end_line=end_line,
                        content=section_content,
                        symbol_name=h_title,
                        parent_symbol=parent_symbol,
                        signature=f"{'#' * h_level} {h_title}",
                        metadata={"level": h_level, "heading": h_title},
                    )
                )

        return chunks
