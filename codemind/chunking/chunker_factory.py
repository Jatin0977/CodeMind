"""
Chunker factory and registry for dispatching language-specific code and doc chunkers.
"""

from typing import Dict, Optional, List
from .base_chunker import BaseChunker
from .ast_chunker import ASTCodeChunker
from .doc_chunker import DocChunker
from .models import CodeChunk
from ..ingestion.models import SourceFile
from ..parsing.base_parser import ParsedFile


class ChunkerFactory:
    """Registry and factory for file chunkers."""

    def __init__(self):
        self._chunkers_by_lang: Dict[str, BaseChunker] = {}
        self._chunkers_by_ext: Dict[str, BaseChunker] = {}

        # Register default chunkers
        ast_chunker = ASTCodeChunker()
        doc_chunker = DocChunker()

        self.register_chunker("python", ast_chunker, [".py", ".pyw"])
        self.register_chunker("markdown", doc_chunker, [".md", ".markdown", ".rst", ".txt"])

    def register_chunker(self, language: str, chunker: BaseChunker, extensions: Optional[list] = None):
        """Register a chunker for a specific language and extensions."""
        lang_lower = language.lower()
        self._chunkers_by_lang[lang_lower] = chunker
        if extensions:
            for ext in extensions:
                self._chunkers_by_ext[ext.lower()] = chunker

    def get_chunker(self, source_file: SourceFile) -> Optional[BaseChunker]:
        """Get the appropriate chunker for a source file."""
        lang = source_file.language.lower()
        if lang in self._chunkers_by_lang:
            return self._chunkers_by_lang[lang]

        ext = source_file.extension.lower()
        if ext in self._chunkers_by_ext:
            return self._chunkers_by_ext[ext]

        return None

    def chunk_file(
        self,
        source_file: SourceFile,
        parsed_file: Optional[ParsedFile] = None,
    ) -> List[CodeChunk]:
        """Chunk a source file using the registered chunker, or fallback to whole file chunk."""
        chunker = self.get_chunker(source_file)
        if chunker:
            return chunker.chunk(source_file, parsed_file)

        # Fallback generic chunk
        raw_lines = source_file.content.splitlines()
        line_count = max(1, len(raw_lines))
        return [
            CodeChunk.create(
                file_path=source_file.file_path,
                relative_path=source_file.relative_path,
                language=source_file.language,
                chunk_type="block",
                start_line=1,
                end_line=line_count,
                content=source_file.content,
                symbol_name=source_file.file_name,
            )
        ]


# Global singleton instance
GLOBAL_CHUNKER_FACTORY = ChunkerFactory()
