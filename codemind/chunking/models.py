"""
Data models for code and documentation chunks.
"""

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List


@dataclass
class CodeChunk:
    """Represents a discrete semantic chunk of source code or documentation."""

    chunk_id: str  # Deterministic hash ID
    file_path: str  # Absolute path
    relative_path: str  # Normalized relative path
    language: str  # 'python', 'markdown', etc.
    chunk_type: str  # 'function', 'method', 'class', 'module_header', 'doc_section', 'block'
    symbol_name: Optional[str] = None  # e.g. 'UserService.authenticate'
    parent_symbol: Optional[str] = None  # e.g. 'UserService'
    start_line: int = 1
    end_line: int = 1
    signature: Optional[str] = None  # Function/class signature
    content: str = ""  # The chunk text content
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        file_path: str,
        relative_path: str,
        language: str,
        chunk_type: str,
        start_line: int,
        end_line: int,
        content: str,
        symbol_name: Optional[str] = None,
        parent_symbol: Optional[str] = None,
        signature: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "CodeChunk":
        """Factory method to construct a CodeChunk with auto-generated deterministic chunk_id."""
        meta = metadata or {}
        hash_seed = f"{relative_path}:{chunk_type}:{symbol_name or ''}:{start_line}-{end_line}:{content.strip()}"
        chunk_id = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()[:16]

        return cls(
            chunk_id=chunk_id,
            file_path=file_path,
            relative_path=relative_path,
            language=language,
            chunk_type=chunk_type,
            symbol_name=symbol_name,
            parent_symbol=parent_symbol,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            content=content,
            metadata=meta,
        )

    @property
    def line_count(self) -> int:
        """Number of lines in the chunk."""
        return max(1, self.end_line - self.start_line + 1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary."""
        return asdict(self)
