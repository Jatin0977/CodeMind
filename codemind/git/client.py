"""
Safe Git CLI wrapper and repository validator for CodeMind (Phase 7, Milestone 1).
Executes commands securely using subprocess argument lists, shell=False, explicit timeouts,
and comprehensive error handling without leaking sensitive details.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Optional, Union, Dict, Any

from .models import (
    GitRepoStatus,
    GitError,
    GitNotFoundError,
    NotAGitRepositoryError,
    GitCommandError,
    GitTimeoutError,
)


class GitClient:
    """Safe, non-mutating Git CLI wrapper for repository inspection and commit mining."""

    def __init__(
        self,
        repo_path: Union[str, Path],
        git_executable: str = "git",
        default_timeout_seconds: float = 30.0,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.git_executable = git_executable
        self.default_timeout_seconds = default_timeout_seconds
        self._canonical_root: Optional[Path] = None

    @property
    def canonical_root(self) -> Path:
        """The verified canonical top-level root of the Git repository."""
        if self._canonical_root is None:
            status = self.validate_repository()
            if not status.is_git_repo or not status.git_root:
                raise NotAGitRepositoryError(
                    f"Path '{self.repo_path}' is not inside a valid Git repository: {status.error}"
                )
            self._canonical_root = Path(status.git_root).resolve()
        return self._canonical_root

    def run_command(
        self,
        args: List[str],
        timeout: Optional[float] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Execute a Git command safely against the target repository.

        Args:
            args: Command arguments starting after 'git'. Must be a List[str].
            timeout: Optional command timeout in seconds.
            check: If True, raises GitCommandError on non-zero exit code.

        Returns:
            subprocess.CompletedProcess containing raw stdout and stderr bytes.
        """
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise TypeError("Git command arguments must be provided as a List[str].")

        full_cmd = [self.git_executable, "-C", str(self.repo_path)] + args
        effective_timeout = timeout if timeout is not None else self.default_timeout_seconds

        try:
            result = subprocess.run(
                full_cmd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=effective_timeout,
            )
        except FileNotFoundError:
            raise GitNotFoundError(
                f"Git executable '{self.git_executable}' was not found on the system PATH."
            )
        except subprocess.TimeoutExpired as exc:
            raise GitTimeoutError(
                f"Git command timed out after {effective_timeout}s: git {' '.join(args[:3])}..."
            ) from exc
        except Exception as exc:
            raise GitError(f"Unexpected error executing Git command: {exc}") from exc

        if check and result.returncode != 0:
            stderr_msg = result.stderr.decode("utf-8", errors="replace").strip()
            # Sanitize stderr to prevent leaking potential credentials
            sanitized_msg = self._sanitize_error(stderr_msg)
            raise GitCommandError(
                f"Git command failed with exit code {result.returncode}: {sanitized_msg}",
                returncode=result.returncode,
                stderr=sanitized_msg,
            )

        return result

    def validate_repository(self) -> GitRepoStatus:
        """
        Perform complete validation of the repository state.
        Checks for:
        - Git executable availability
        - Valid Git repository root
        - Empty repository (no commits yet)
        - Shallow repository clone
        - Detached HEAD state
        """
        # 1. Test Git executable
        try:
            version_res = subprocess.run(
                [self.git_executable, "--version"],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5.0,
            )
            if version_res.returncode != 0:
                return GitRepoStatus(
                    is_git_repo=False,
                    error="Git executable check failed with non-zero exit code.",
                )
        except FileNotFoundError:
            return GitRepoStatus(
                is_git_repo=False,
                error=f"Git executable '{self.git_executable}' not found on system PATH.",
            )
        except Exception as e:
            return GitRepoStatus(
                is_git_repo=False,
                error=f"Failed to invoke Git executable: {e}",
            )

        # 2. Check if directory exists
        if not self.repo_path.exists() or not self.repo_path.is_dir():
            return GitRepoStatus(
                is_git_repo=False,
                error=f"Repository directory '{self.repo_path}' does not exist or is not a directory.",
            )

        # 3. Check inside work tree and get top-level
        try:
            res_root = self.run_command(["rev-parse", "--show-toplevel"], check=False)
            if res_root.returncode != 0:
                stderr_clean = self._sanitize_error(res_root.stderr.decode("utf-8", errors="replace").strip())
                return GitRepoStatus(
                    is_git_repo=False,
                    error=stderr_clean or "Not a Git repository.",
                )
            git_root = res_root.stdout.decode("utf-8", errors="replace").strip()
        except GitError as e:
            return GitRepoStatus(is_git_repo=False, error=str(e))

        # 4. Check if empty repository (HEAD unresolvable)
        is_empty = False
        head_commit: Optional[str] = None
        res_head = self.run_command(["rev-parse", "--verify", "HEAD"], check=False)
        if res_head.returncode != 0:
            is_empty = True
        else:
            head_commit = res_head.stdout.decode("ascii", errors="ignore").strip()

        # 5. Check if shallow repository
        is_shallow = False
        res_shallow = self.run_command(["rev-parse", "--is-shallow-repository"], check=False)
        if res_shallow.returncode == 0:
            is_shallow = res_shallow.stdout.decode("ascii", errors="ignore").strip().lower() == "true"
        else:
            # Fallback check for .git/shallow file
            shallow_file = Path(git_root) / ".git" / "shallow"
            is_shallow = shallow_file.exists()

        # 6. Check if detached HEAD
        is_detached = False
        if not is_empty:
            res_sym = self.run_command(["symbolic-ref", "-q", "HEAD"], check=False)
            is_detached = (res_sym.returncode != 0)

        return GitRepoStatus(
            is_git_repo=True,
            git_root=git_root,
            is_empty=is_empty,
            is_shallow=is_shallow,
            is_detached=is_detached,
            head_commit=head_commit,
            error=None,
        )

    # Convenience alias
    get_status = validate_repository

    def resolve_safe_path(self, git_path: str) -> Path:
        """
        Validate and resolve a Git-relative path against the repository filesystem.
        Ensures strict boundary containment (prevents directory traversal attacks).

        Args:
            git_path: Original Git path.

        Returns:
            Resolved absolute Path strictly contained within the canonical root.

        Raises:
            ValueError: If path is absolute or attempts to escape repository root.
        """
        if not git_path or not git_path.strip():
            raise ValueError("Git path cannot be empty.")

        # Reject absolute paths (POSIX / or Windows C:\)
        p = Path(git_path)
        if p.is_absolute() or git_path.startswith("/") or git_path.startswith("\\"):
            raise ValueError(f"Security error: Absolute path '{git_path}' is not permitted.")

        # Check for drive specification
        if len(git_path) >= 2 and git_path[1] == ":" and git_path[0].isalpha():
            raise ValueError(f"Security error: Drive-qualified path '{git_path}' is not permitted.")

        root = self.canonical_root
        resolved = (root / git_path).resolve()

        # Verify containment within canonical root
        try:
            resolved.relative_to(root)
        except ValueError:
            raise ValueError(
                f"Security error: Path '{git_path}' resolves outside the repository root '{root}'."
            )

        return resolved

    @staticmethod
    def _sanitize_error(error_msg: str) -> str:
        """Strip sensitive credentials (tokens, passwords, user info) from error text."""
        import re
        # Redact basic auth patterns in URLs: http(s)://user:token@domain
        sanitized = re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://\1:[REDACTED]@", error_msg)
        # Redact Bearer / token strings
        sanitized = re.sub(r"(token|bearer|key|secret)\s*[:=]\s*[^\s]+", r"\1=[REDACTED]", sanitized, flags=re.IGNORECASE)
        return sanitized
