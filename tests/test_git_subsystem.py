"""
Unit and integration tests for CodeMind Git Subsystem (Phase 7, Milestone 1).
Validates GitClient, GitMiner, dual-pass stream parsing, change-type detection,
surrogateescape lossless decoding, merge exclusion, and path safety against
isolated temporary Git repositories.
"""

import os
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional

from codemind.git.models import (
    CommitRecord,
    FileChange,
    GitRepoStatus,
    GitError,
    GitNotFoundError,
    NotAGitRepositoryError,
    GitCommandError,
    GitTimeoutError,
    GitParsingError,
)
from codemind.git.client import GitClient
from codemind.git.miner import GitMiner, decode_git_path


class TestGitSubsystem(unittest.TestCase):
    """Test suite for Milestone 1: Git client, repository validation, and commit mining."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _init_git_repo(self, path: Optional[Path] = None) -> Path:
        """Initialize an isolated test Git repository with user config."""
        target = path or self.repo_path
        subprocess.run(["git", "init", "-b", "main"], cwd=str(target), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "CodeMind Tester"], cwd=str(target), check=True)
        subprocess.run(["git", "config", "user.email", "tester@codemind.local"], cwd=str(target), check=True)
        return target

    def _commit_file(
        self,
        rel_path: str,
        content: str,
        msg: str,
        binary: bool = False,
        path: Optional[Path] = None,
    ):
        """Create or update a file and commit it."""
        target = path or self.repo_path
        full_path = target / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            full_path.write_bytes(content.encode("latin-1") if isinstance(content, str) else content)
        else:
            full_path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(target), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=str(target), check=True, capture_output=True)

    # ========================================================================
    # 1. Repository Validation Tests
    # ========================================================================

    def test_non_git_directory_validation(self):
        """Validating a non-git directory returns is_git_repo=False and proper error."""
        client = GitClient(self.repo_path)
        status = client.validate_repository()
        self.assertFalse(status.is_git_repo)
        self.assertIn("not a git repository", (status.error or "").lower())

    def test_non_existent_directory_validation(self):
        """Validating a non-existent path returns is_git_repo=False."""
        client = GitClient(self.repo_path / "does_not_exist")
        status = client.validate_repository()
        self.assertFalse(status.is_git_repo)
        self.assertIn("does not exist", status.error or "")

    def test_empty_git_repository_validation(self):
        """Empty Git repository has is_empty=True and no head commit."""
        self._init_git_repo()
        client = GitClient(self.repo_path)
        status = client.validate_repository()
        self.assertTrue(status.is_git_repo)
        self.assertTrue(status.is_empty)
        self.assertIsNone(status.head_commit)
        self.assertIsNotNone(status.git_root)

    def test_valid_git_repository_with_commits(self):
        """Initialized Git repo with commits returns valid status, head commit, and root."""
        self._init_git_repo()
        self._commit_file("calc.py", "def add(a, b): return a + b\n", "Initial commit")
        client = GitClient(self.repo_path)
        status = client.validate_repository()
        self.assertTrue(status.is_git_repo)
        self.assertFalse(status.is_empty)
        self.assertIsNotNone(status.head_commit)
        self.assertEqual(len(status.head_commit or ""), 40)
        self.assertFalse(status.is_detached)

    def test_missing_git_executable_handling(self):
        """Client configured with a nonexistent executable raises GitNotFoundError."""
        client = GitClient(self.repo_path, git_executable="git_nonexistent_executable_12345")
        status = client.validate_repository()
        self.assertFalse(status.is_git_repo)
        self.assertIn("not found", status.error or "")
        with self.assertRaises(GitNotFoundError):
            client.run_command(["status"])

    def test_command_timeout_handling(self):
        """Commands exceeding the timeout threshold raise GitTimeoutError."""
        self._init_git_repo()
        client = GitClient(self.repo_path, default_timeout_seconds=0.00001)
        with self.assertRaises(GitTimeoutError):
            client.run_command(["log"], timeout=0.00001)

    def test_command_failure_raises_git_command_error(self):
        """Non-zero exit codes raise GitCommandError with sanitized message."""
        self._init_git_repo()
        client = GitClient(self.repo_path)
        with self.assertRaises(GitCommandError) as ctx:
            client.run_command(["show", "nonexistent_branch_commit_99999"])
        self.assertIn("nonexistent_branch_commit_99999", str(ctx.exception))

    # ========================================================================
    # 2. Path Safety Tests
    # ========================================================================

    def test_path_safety_valid_relative_path(self):
        """Valid relative paths resolve correctly within canonical root."""
        self._init_git_repo()
        client = GitClient(self.repo_path)
        resolved = client.resolve_safe_path("src/utils/calc.py")
        self.assertTrue(str(resolved).startswith(str(client.canonical_root)))

    def test_path_safety_rejects_absolute_path(self):
        """Absolute paths are rejected by security containment check."""
        self._init_git_repo()
        client = GitClient(self.repo_path)
        with self.assertRaises(ValueError):
            client.resolve_safe_path("/etc/passwd")
        with self.assertRaises(ValueError):
            client.resolve_safe_path("C:/Windows/System32")

    def test_path_safety_rejects_traversal(self):
        """Directory traversal attempts with .. escaping root are rejected."""
        self._init_git_repo()
        client = GitClient(self.repo_path)
        with self.assertRaises(ValueError):
            client.resolve_safe_path("../../outside.txt")

    # ========================================================================
    # 3. Commit Mining & Dual-Pass Parsing Tests
    # ========================================================================

    def test_mine_empty_repository_returns_empty_list(self):
        """Mining an empty repository returns an empty list without error."""
        self._init_git_repo()
        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()
        self.assertEqual(len(commits), 0)

    def test_mine_root_and_multiple_commits(self):
        """Mining multiple commits preserves chronological metadata and change details."""
        self._init_git_repo()
        self._commit_file("calc.py", "def add(a, b): return a + b\n", "Initial commit")
        self._commit_file("calc.py", "def add(a, b): return a + b\ndef sub(a, b): return a - b\n", "Add subtraction")

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        self.assertEqual(len(commits), 2)
        # Newest first
        self.assertEqual(commits[0].subject, "Add subtraction")
        self.assertFalse(commits[0].is_merge)
        self.assertEqual(len(commits[0].parents), 1)

        # Root commit has empty parents
        self.assertEqual(commits[1].subject, "Initial commit")
        self.assertEqual(len(commits[1].parents), 0)
        self.assertFalse(commits[1].is_merge)

    def test_change_type_distinction_modified_only_additions(self):
        """Modified file with only additions is correctly reported as 'M', not 'A'."""
        self._init_git_repo()
        self._commit_file("app.py", "line 1\nline 2\n", "C1: initial")
        # Append lines (only additions, 0 deletions)
        self._commit_file("app.py", "line 1\nline 2\nline 3\nline 4\n", "C2: append only")

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        c2 = commits[0]
        self.assertEqual(len(c2.files_changed), 1)
        change = c2.files_changed[0]
        self.assertEqual(change.path, "app.py")
        self.assertEqual(change.status, "M")  # Must be 'M', not 'A'
        self.assertEqual(change.additions, 2)
        self.assertEqual(change.deletions, 0)
        self.assertFalse(change.is_binary)

    def test_change_type_distinction_modified_only_deletions(self):
        """Modified file with only deletions is correctly reported as 'M', not 'D'."""
        self._init_git_repo()
        self._commit_file("app.py", "line 1\nline 2\nline 3\nline 4\n", "C1: initial")
        # Remove lines (only deletions, 0 additions)
        self._commit_file("app.py", "line 1\nline 2\n", "C2: delete lines")

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        c2 = commits[0]
        self.assertEqual(len(c2.files_changed), 1)
        change = c2.files_changed[0]
        self.assertEqual(change.path, "app.py")
        self.assertEqual(change.status, "M")  # Must be 'M', not 'D'
        self.assertEqual(change.additions, 0)
        self.assertEqual(change.deletions, 2)

    def test_deleted_file_change_status(self):
        """Deleted file has status 'D' and deletions count matching removed lines."""
        self._init_git_repo()
        self._commit_file("obsolete.py", "old = 1\nold = 2\n", "Add obsolete")
        # Delete file
        os.remove(self.repo_path / "obsolete.py")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "Remove obsolete"], cwd=str(self.repo_path), check=True)

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        c = commits[0]
        self.assertEqual(len(c.files_changed), 1)
        change = c.files_changed[0]
        self.assertEqual(change.status, "D")
        self.assertEqual(change.path, "obsolete.py")
        self.assertEqual(change.deletions, 2)
        self.assertEqual(change.additions, 0)

    def test_rename_detection_with_modifications(self):
        """Renamed file with line edits has status 'R', old_path, new_path, and accurate diff counts."""
        self._init_git_repo()
        initial_content = (
            "class Service:\n"
            "    def __init__(self):\n"
            "        self.active = True\n"
            "    def ping(self):\n"
            "        return 'pong'\n"
            "    def status(self):\n"
            "        return self.active\n"
        )
        self._commit_file("old_service.py", initial_content, "Initial service")

        # Rename using git mv and modify slightly (keeps >80% similarity)
        subprocess.run(["git", "mv", "old_service.py", "new_service.py"], cwd=str(self.repo_path), check=True)
        updated_content = initial_content + "    def run(self):\n        pass\n"
        (self.repo_path / "new_service.py").write_text(updated_content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "Rename and add method"], cwd=str(self.repo_path), check=True)

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        c = commits[0]
        self.assertEqual(len(c.files_changed), 1)
        change = c.files_changed[0]
        self.assertEqual(change.status, "R")
        self.assertEqual(change.old_path, "old_service.py")
        self.assertEqual(change.path, "new_service.py")
        self.assertGreater(change.additions, 0)

    def test_binary_file_detection(self):
        """Binary files are flagged is_binary=True with 0 line additions and deletions."""
        self._init_git_repo()
        binary_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x01\x00\x01\x08\x06"
        self._commit_file("logo.png", binary_bytes.decode("latin-1"), "Add logo", binary=True)

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        c = commits[0]
        self.assertEqual(len(c.files_changed), 1)
        change = c.files_changed[0]
        self.assertEqual(change.path, "logo.png")
        self.assertTrue(change.is_binary)
        self.assertEqual(change.additions, 0)
        self.assertEqual(change.deletions, 0)

    def test_empty_commit_handling(self):
        """Empty commit created via --allow-empty has files_changed = []."""
        self._init_git_repo()
        self._commit_file("calc.py", "x = 1\n", "C1")
        subprocess.run(["git", "commit", "--allow-empty", "-m", "C2 empty"], cwd=str(self.repo_path), check=True)

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        self.assertEqual(len(commits), 2)
        self.assertEqual(commits[0].subject, "C2 empty")
        self.assertEqual(len(commits[0].files_changed), 0)

    def test_merge_commit_exclusion(self):
        """Non-fast-forward merge commits are strictly excluded by default (--no-merges)."""
        self._init_git_repo()
        self._commit_file("base.txt", "base\n", "C1: base")

        # Feature branch
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=str(self.repo_path), check=True, capture_output=True)
        self._commit_file("feat.txt", "feature content\n", "C2: feature")

        # Main branch
        subprocess.run(["git", "checkout", "main"], cwd=str(self.repo_path), check=True, capture_output=True)
        self._commit_file("main.txt", "main content\n", "C3: main")

        # Merge feature into main
        subprocess.run(
            ["git", "merge", "--no-ff", "-m", "Merge branch feature", "feature"],
            cwd=str(self.repo_path),
            check=True,
            capture_output=True,
        )

        client = GitClient(self.repo_path)
        miner = GitMiner(client)

        # Default mining excludes merge commits
        commits_no_merge = miner.mine_commits(include_merges=False)
        self.assertEqual(len(commits_no_merge), 3)
        subjects = [c.subject for c in commits_no_merge]
        self.assertNotIn("Merge branch feature", subjects)

        # Explicit include_merges=True includes merge commit
        commits_with_merge = miner.mine_commits(include_merges=True)
        self.assertEqual(len(commits_with_merge), 4)
        merge_commit = next(c for c in commits_with_merge if c.is_merge)
        self.assertEqual(merge_commit.subject, "Merge branch feature")
        self.assertEqual(len(merge_commit.parents), 2)

    def test_filenames_with_spaces_tabs_and_multilingual(self):
        """Filenames containing spaces, Unicode characters, and emojis are preserved losslessly."""
        self._init_git_repo()
        space_path = "my documents/calc spec v2.py"
        unicode_path = "src/données/résumé_🚀.py"
        self._commit_file(space_path, "a = 10\n", "Commit spaces")
        self._commit_file(unicode_path, "class Résumé: pass\n", "Commit multilingual")

        client = GitClient(self.repo_path)
        miner = GitMiner(client)
        commits = miner.mine_commits()

        self.assertEqual(len(commits), 2)
        paths = [f.path for c in commits for f in c.files_changed]
        self.assertIn(space_path, paths)
        self.assertIn(unicode_path, paths)

    def test_lossless_surrogateescape_roundtrip(self):
        """Surrogateescape decoding decodes arbitrary bytes losslessly and roundtrips byte-for-byte."""
        raw_bytes = b"my_path_\xff\xfe_test.py"
        decoded = decode_git_path(raw_bytes)
        re_encoded = decoded.encode("utf-8", errors="surrogateescape")
        self.assertEqual(re_encoded, raw_bytes)

    def test_models_serialization_roundtrip(self):
        """CommitRecord and FileChange serialize to dict and deserialize losslessly."""
        fc = FileChange(status="M", path="src/app.py", old_path=None, additions=10, deletions=5, is_binary=False)
        fc_dict = fc.to_dict()
        fc_restored = FileChange.from_dict(fc_dict)
        self.assertEqual(fc, fc_restored)

        cr = CommitRecord(
            full_hash="a" * 40,
            short_hash="a" * 7,
            author_name="Alice",
            author_email="alice@example.com",
            author_date=datetime(2026, 11, 18, 10, 30, 0),
            parents=["b" * 40],
            subject="Refactor core",
            is_merge=False,
            files_changed=[fc],
        )
        cr_dict = cr.to_dict()
        cr_restored = CommitRecord.from_dict(cr_dict)
        self.assertEqual(cr.full_hash, cr_restored.full_hash)
        self.assertEqual(cr.short_hash, cr_restored.short_hash)
        self.assertEqual(cr.subject, cr_restored.subject)
        self.assertEqual(len(cr_restored.files_changed), 1)
        self.assertEqual(cr_restored.files_changed[0].path, "src/app.py")


if __name__ == "__main__":
    unittest.main()
