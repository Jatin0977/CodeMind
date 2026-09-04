"""
Data models for codebase files and repository ingestion.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from pathlib import Path


@dataclass
class SourceFile:
    """Represents a single ingested source code or documentation file."""

    file_path: str  # Absolute path
    relative_path: str  # Normalized relative path (forward slashes)
    file_name: str  # File name with extension
    extension: str  # e.g., '.py', '.md'
    language: str  # e.g., 'python', 'markdown'
    file_size: int  # Size in bytes
    line_count: int  # Total lines in file
    content: str  # Raw file text content
    checksum: str  # SHA-256 hash of content

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        """Convert SourceFile to a dictionary."""
        data = asdict(self)
        if not include_content:
            data.pop("content", None)
        return data

    @property
    def is_python(self) -> bool:
        """Check if file is a Python file."""
        return self.language.lower() == "python" or self.extension.lower() in {".py", ".pyw"}

    @property
    def is_documentation(self) -> bool:
        """Check if file is a documentation file."""
        return self.language.lower() in {"markdown", "restructuredtext", "text"} or self.extension.lower() in {
            ".md", ".markdown", ".rst", ".txt"
        }


@dataclass
class IngestionSummary:
    """Summary statistics for an ingested repository."""

    total_files: int = 0
    total_size_bytes: int = 0
    total_lines: int = 0
    language_breakdown: Dict[str, int] = field(default_factory=dict)
    skipped_count: int = 0
    skipped_files: List[Dict[str, str]] = field(default_factory=list)  # {"path": ..., "reason": ...}

    def to_dict(self) -> Dict[str, Any]:
        """Convert IngestionSummary to a dictionary."""
        return asdict(self)


@dataclass
class IngestedRepository:
    """Represents a fully ingested repository containing source files and metadata."""

    repo_path: str
    repo_name: str
    files: List[SourceFile] = field(default_factory=list)
    summary: IngestionSummary = field(default_factory=IngestionSummary)

    def get_python_files(self) -> List[SourceFile]:
        """Return all Python source files."""
        return [f for f in self.files if f.is_python]

    def get_doc_files(self) -> List[SourceFile]:
        """Return all documentation files."""
        return [f for f in self.files if f.is_documentation]

    def get_file_by_relative_path(self, rel_path: str) -> Optional[SourceFile]:
        """Find a file by its normalized relative path."""
        norm_target = rel_path.replace("\\", "/").lstrip("/")
        for f in self.files:
            if f.relative_path.replace("\\", "/").lstrip("/") == norm_target:
                return f
        return None

    def to_dict(self, include_content: bool = False) -> Dict[str, Any]:
        """Convert repository metadata to dictionary."""
        return {
            "repo_path": self.repo_path,
            "repo_name": self.repo_name,
            "summary": self.summary.to_dict(),
            "files": [f.to_dict(include_content=include_content) for f in self.files]
        }
