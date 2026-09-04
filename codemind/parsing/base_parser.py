"""
Base parser interface and shared data structures for multi-language code parsing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from ..ingestion.models import SourceFile


@dataclass
class Symbol:
    """Represents a code symbol such as a class, function, or method."""

    name: str
    symbol_type: str  # 'class', 'function', 'method'
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    parent_name: Optional[str] = None  # Enclosing class or function
    is_async: bool = False
    args: List[str] = field(default_factory=list)
    returns: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)  # Function/method calls inside body
    bases: List[str] = field(default_factory=list)  # Base classes (for class symbols)
    methods: List["Symbol"] = field(default_factory=list)  # Child methods (for class symbols)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Symbol to dictionary representation."""
        data = {
            "name": self.name,
            "type": self.symbol_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "docstring": self.docstring,
            "parent_name": self.parent_name,
            "is_async": self.is_async,
            "args": self.args,
            "returns": self.returns,
            "decorators": self.decorators,
            "calls": self.calls,
        }
        if self.symbol_type == "class":
            data["bases"] = self.bases
            data["methods"] = [m.to_dict() for m in self.methods]
        return data


@dataclass
class ImportStatement:
    """Represents an imported module or symbol."""

    name: str  # e.g., 'os', 'Path', '*'
    module: Optional[str] = None  # e.g., 'pathlib'
    alias: Optional[str] = None  # e.g., 'np'
    is_from: bool = False  # True if 'from ... import ...'
    line_number: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert import statement to dictionary."""
        return asdict(self)

    def __str__(self) -> str:
        if self.is_from:
            base = f"from {self.module} import {self.name}"
        else:
            base = f"import {self.name}"
        if self.alias:
            base += f" as {self.alias}"
        return base


@dataclass
class ParsedFile:
    """Structured representation of a parsed source code file."""

    file_path: str
    relative_path: str
    language: str
    is_valid: bool = True
    error: Optional[str] = None
    docstring: Optional[str] = None
    classes: List[Symbol] = field(default_factory=list)
    functions: List[Symbol] = field(default_factory=list)
    imports: List[ImportStatement] = field(default_factory=list)
    symbols: List[Symbol] = field(default_factory=list)  # Flat list of all symbols

    @property
    def metrics(self) -> Dict[str, int]:
        """Compute symbol metrics for this file."""
        total_methods = sum(len(c.methods) for c in self.classes)
        return {
            "classes": len(self.classes),
            "functions": len(self.functions),
            "methods": total_methods,
            "imports": len(self.imports),
            "total_symbols": len(self.symbols),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert ParsedFile to dictionary."""
        return {
            "file_path": self.file_path,
            "relative_path": self.relative_path,
            "language": self.language,
            "is_valid": self.is_valid,
            "error": self.error,
            "docstring": self.docstring,
            "metrics": self.metrics,
            "imports": [imp.to_dict() for imp in self.imports],
            "classes": [c.to_dict() for c in self.classes],
            "functions": [f.to_dict() for f in self.functions],
            "symbols": [s.to_dict() for s in self.symbols],
        }


class BaseParser(ABC):
    """Abstract base class for code parsers."""

    @property
    @abstractmethod
    def supported_language(self) -> str:
        """Returns the language supported by this parser."""
        pass

    @abstractmethod
    def parse(self, source_file: SourceFile) -> ParsedFile:
        """
        Parse a SourceFile and return a structured ParsedFile.
        Must not raise uncaught exceptions on malformed code.
        """
        pass
