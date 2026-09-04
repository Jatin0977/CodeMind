"""
Parser factory for instantiating and dispatching language-specific code parsers.
"""

from typing import Dict, Optional
from .base_parser import BaseParser, ParsedFile
from .python_parser import PythonParser
from ..ingestion.models import SourceFile


class ParserFactory:
    """Factory and registry for language parsers."""

    def __init__(self):
        self._parsers_by_lang: Dict[str, BaseParser] = {}
        self._parsers_by_ext: Dict[str, BaseParser] = {}

        # Register default parsers
        python_parser = PythonParser()
        self.register_parser("python", python_parser, [".py", ".pyw"])

    def register_parser(self, language: str, parser: BaseParser, extensions: Optional[list] = None):
        """Register a new parser for a specific language and extensions."""
        lang_lower = language.lower()
        self._parsers_by_lang[lang_lower] = parser
        if extensions:
            for ext in extensions:
                self._parsers_by_ext[ext.lower()] = parser

    def get_parser(self, source_file: SourceFile) -> Optional[BaseParser]:
        """Retrieve appropriate parser for a source file."""
        # Try by language first
        lang = source_file.language.lower()
        if lang in self._parsers_by_lang:
            return self._parsers_by_lang[lang]

        # Try by extension
        ext = source_file.extension.lower()
        if ext in self._parsers_by_ext:
            return self._parsers_by_ext[ext]

        return None

    def parse(self, source_file: SourceFile) -> Optional[ParsedFile]:
        """Parse a source file with the appropriate parser if available."""
        parser = self.get_parser(source_file)
        if parser:
            return parser.parse(source_file)
        return None


# Default global instance
GLOBAL_PARSER_FACTORY = ParserFactory()
