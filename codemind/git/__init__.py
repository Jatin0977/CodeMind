"""
CodeMind Git Temporal Intelligence Subsystem (Phase 7).
Provides safe Git CLI interaction, stream parsing, commit mining, code churn analytics,
and logical coupling discovery.
"""

from .models import (
    CommitRecord,
    FileChange,
    FileChangeStatus,
    GitRepoStatus,
    GitError,
    GitNotFoundError,
    NotAGitRepositoryError,
    GitCommandError,
    GitTimeoutError,
    GitParsingError,
)
from .client import GitClient
from .miner import GitMiner, decode_git_path
from .churn import (
    CodeChurnAnalyzer,
    FileChurnMetrics,
    RepositoryChurnSummary,
)
from .coupling import (
    LogicalCouplingAnalyzer,
    LogicalCoupling,
    CouplingResult,
)

__all__ = [
    # Models & Exceptions
    "CommitRecord",
    "FileChange",
    "FileChangeStatus",
    "GitRepoStatus",
    "GitError",
    "GitNotFoundError",
    "NotAGitRepositoryError",
    "GitCommandError",
    "GitTimeoutError",
    "GitParsingError",
    # Client & Miner
    "GitClient",
    "GitMiner",
    "decode_git_path",
    # Churn Analytics
    "CodeChurnAnalyzer",
    "FileChurnMetrics",
    "RepositoryChurnSummary",
    # Logical Coupling
    "LogicalCouplingAnalyzer",
    "LogicalCoupling",
    "CouplingResult",
]
