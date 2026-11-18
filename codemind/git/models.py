"""
Data models and error types for CodeMind Git Subsystem (Phase 7, Milestone 1).
Provides typed, validated, and serializable representations for Git commit records,
file change diffs, repository status, and domain exceptions.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Any, Union


class FileChangeStatus(str, Enum):
    """Authoritative Git file status codes (renames supported; copies excluded)."""
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"
    TYPE_CHANGED = "T"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        if isinstance(other, FileChangeStatus):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value)


@dataclass
class FileChange:
    """Represents a specific file modification within a Git commit."""
    status: str  # 'A', 'M', 'D', 'R', 'T'
    path: str  # Original lossless path
    old_path: Optional[str] = None  # Populated only for renames ('R')
    additions: int = 0  # Added lines (0 for binary or deletions)
    deletions: int = 0  # Deleted lines (0 for binary or additions)
    is_binary: bool = False  # True if Git detected binary diff (- -)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileChange to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileChange":
        """Deserialize FileChange from a dictionary."""
        return cls(
            status=data["status"],
            path=data["path"],
            old_path=data.get("old_path"),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            is_binary=data.get("is_binary", False),
        )


@dataclass
class CommitRecord:
    """Represents a parsed Git commit with metadata and associated file changes."""
    full_hash: str
    short_hash: str
    author_name: str
    author_email: str
    author_date: datetime
    parents: List[str] = field(default_factory=list)
    subject: str = ""
    is_merge: bool = False
    files_changed: List[FileChange] = field(default_factory=list)

    def __post_init__(self):
        # Automatically mark as merge if multiple parents exist
        if len(self.parents) >= 2:
            self.is_merge = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize CommitRecord to a dictionary."""
        data = asdict(self)
        data["author_date"] = self.author_date.isoformat() if isinstance(self.author_date, datetime) else self.author_date
        data["files_changed"] = [f.to_dict() for f in self.files_changed]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommitRecord":
        """Deserialize CommitRecord from a dictionary."""
        raw_date = data["author_date"]
        author_date = datetime.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
        files = [
            FileChange.from_dict(f) if isinstance(f, dict) else f
            for f in data.get("files_changed", [])
        ]
        return cls(
            full_hash=data["full_hash"],
            short_hash=data["short_hash"],
            author_name=data["author_name"],
            author_email=data["author_email"],
            author_date=author_date,
            parents=data.get("parents", []),
            subject=data.get("subject", ""),
            is_merge=data.get("is_merge", len(data.get("parents", [])) >= 2),
            files_changed=files,
        )


# Alias for compatibility with external references
GitCommit = CommitRecord


@dataclass
class GitRepoStatus:
    """Status summary describing the state of a Git repository."""
    is_git_repo: bool
    git_root: Optional[str] = None
    is_empty: bool = False
    is_shallow: bool = False
    is_detached: bool = False
    head_commit: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# Git Subsystem Exception Hierarchy
# ============================================================================

class GitError(Exception):
    """Base exception for all Git subsystem errors."""
    pass


class GitNotFoundError(GitError):
    """Raised when the git executable cannot be found on the host system."""
    pass


class NotAGitRepositoryError(GitError):
    """Raised when an operation targets a directory that is not a Git repository."""
    pass


class GitCommandError(GitError):
    """Raised when a Git command execution returns a non-zero exit code."""

    def __init__(self, message: str, returncode: int = 1, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class GitTimeoutError(GitError):
    """Raised when a Git command execution exceeds the configured timeout."""
    pass


class GitParsingError(GitError):
    """Raised when Git stream output cannot be parsed or records cannot be matched."""
    pass
