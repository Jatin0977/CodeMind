"""
Abstract base class for codebase chunkers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from .models import CodeChunk
from ..ingestion.models import SourceFile
from ..parsing.base_parser import ParsedFile


class BaseChunker(ABC):
    """Abstract interface for splitting source code and documentation files into CodeChunks."""

    @property
    @abstractmethod
    def supported_language(self) -> str:
        """Returns the language supported by this chunker."""
        pass

    @abstractmethod
    def chunk(
        self,
        source_file: SourceFile,
        parsed_file: Optional[ParsedFile] = None,
    ) -> List[CodeChunk]:
        """
        Split a source or documentation file into meaningful semantic CodeChunks.

        Args:
            source_file: Raw source file model.
            parsed_file: Optional AST-parsed file model.

        Returns:
            List of CodeChunk instances with preserved line spans and metadata.
        """
        pass
