"""
Stateful two-pass Git commit miner and stream parser for CodeMind (Phase 7, Milestone 1).
Extracts authoritative change statuses and line diff statistics using NUL-delimited streams
with lossless surrogateescape decoding and strict commit boundary validation.
"""

from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

from .client import GitClient
from .models import (
    CommitRecord,
    FileChange,
    GitParsingError,
)


def decode_git_path(raw_bytes: bytes) -> str:
    """
    Losslessly decode raw Git filename bytes into a string using surrogateescape (PEP 383).
    Preserves all valid UTF-8 sequences (multilingual, accents, emojis) while mapping
    arbitrary non-UTF-8 bytes to surrogate code points (\udc80 - \udcff), guaranteeing
    a bijective roundtrip without data corruption.
    """
    return raw_bytes.decode("utf-8", errors="surrogateescape")


class GitMiner:
    """Mines Git commit logs and file changes using dual-pass batch extraction."""

    def __init__(self, client: GitClient):
        self.client = client

    def mine_commits(
        self,
        max_commits: int = 1000,
        include_merges: bool = False,
        file_path: Optional[str] = None,
        path: Optional[str] = None,
        since: Optional[str] = None,
        author: Optional[str] = None,
    ) -> List[CommitRecord]:
        """
        Mine commit history across the analysis window using synchronized dual-pass extraction.

        Args:
            max_commits: Maximum commits to inspect (default W_analysis = 1000).
            include_merges: If False (default), excludes merge commits (--no-merges).
            file_path: Optional file path to scope the history query.
            path: Alias for file_path.
            since: Optional date string to filter commits since.
            author: Optional author string to filter commits by author.

        Returns:
            List of parsed CommitRecord instances ordered from newest to oldest.
        """
        status = self.client.validate_repository()
        if not status.is_git_repo:
            raise GitParsingError(f"Cannot mine commits: {status.error}")
        if status.is_empty:
            return []

        target_file = file_path or path

        # Common revision flags ensuring both passes cover the identical commit set
        common_flags = [f"-n{max_commits}"]
        if not include_merges:
            common_flags.append("--no-merges")
        if since:
            common_flags.append(f"--since={since}")
        if author:
            common_flags.append(f"--author={author}")

        # Pass 1: Commit metadata and authoritative name-status (renames enabled with -M)
        fmt1 = "COMMIT:%H%x00%h%x00%an%x00%ae%x00%aI%x00%P%x00%s%x00"
        cmd1 = ["log"] + common_flags + ["-z", "--name-status", "-M", f"--format=format:{fmt1}"]
        if target_file:
            cmd1 += ["--", target_file]

        res1 = self.client.run_command(cmd1)

        # Pass 2: Numerical diff additions, deletions, and binary flags
        fmt2 = "COMMIT:%H%x00"
        cmd2 = ["log"] + common_flags + ["-z", "--numstat", "-M", f"--format=format:{fmt2}"]
        if target_file:
            cmd2 += ["--", target_file]

        res2 = self.client.run_command(cmd2)

        # Parse Pass 2 (Numstats) into lookup table
        numstat_index = self._parse_numstat_stream(res2.stdout)

        # Parse Pass 1 (Name-status + headers) and correlate with numstat metrics
        commits = self._parse_name_status_stream(res1.stdout, numstat_index)

        return commits

    def _parse_numstat_stream(
        self, raw_bytes: bytes
    ) -> Dict[str, Dict[Tuple[str, ...], Tuple[int, int, bool]]]:
        """
        Parse Pass 2 output:
        Maps commit_hash -> {path_key: (added, deleted, is_binary)}.
        For normal files: path_key = (path,)
        For renames:      path_key = (old_path, new_path)
        """
        numstats: Dict[str, Dict[Tuple[str, ...], Tuple[int, int, bool]]] = {}
        if not raw_bytes:
            return numstats

        tokens = raw_bytes.split(b"\x00")
        i = 0
        n = len(tokens)
        cur_hash: Optional[str] = None

        while i < n:
            tok = tokens[i]
            if not tok or tok == b"\n":
                i += 1
                continue

            if tok.startswith(b"COMMIT:"):
                cur_hash = tok[7:].decode("ascii", errors="replace").strip()
                numstats[cur_hash] = {}
                i += 1
                continue

            if cur_hash is None:
                i += 1
                continue

            # Numstat entry: added\tdeleted\tpath or added\tdeleted\t (for renames)
            line = tok.lstrip(b"\n")
            parts = line.split(b"\t")
            if len(parts) >= 3:
                add_str = parts[0].decode("ascii", errors="replace")
                del_str = parts[1].decode("ascii", errors="replace")
                is_binary = (add_str == "-" and del_str == "-")
                added = int(add_str) if not is_binary else 0
                deleted = int(del_str) if not is_binary else 0

                path_part = b"\t".join(parts[2:])
                if path_part == b"":
                    # Rename in -z mode: next two tokens are old_path and new_path
                    if i + 2 >= n:
                        raise GitParsingError(
                            f"Truncated numstat rename record in commit {cur_hash}."
                        )
                    old_path = decode_git_path(tokens[i + 1])
                    new_path = decode_git_path(tokens[i + 2])
                    numstats[cur_hash][(old_path, new_path)] = (added, deleted, is_binary)
                    i += 2
                else:
                    path = decode_git_path(path_part)
                    numstats[cur_hash][(path,)] = (added, deleted, is_binary)
            i += 1

        return numstats

    def _parse_name_status_stream(
        self,
        raw_bytes: bytes,
        numstat_index: Dict[str, Dict[Tuple[str, ...], Tuple[int, int, bool]]],
    ) -> List[CommitRecord]:
        """
        Parse Pass 1 output and join with Pass 2 metrics.
        """
        commits: List[CommitRecord] = []
        if not raw_bytes:
            return commits

        tokens = raw_bytes.split(b"\x00")
        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]
            if not tok or tok == b"\n":
                i += 1
                continue

            if not tok.startswith(b"COMMIT:"):
                # Skip any stray whitespace or boundary padding
                i += 1
                continue

            commit_hash = tok[7:].decode("ascii", errors="replace").strip()
            if i + 6 >= n:
                raise GitParsingError(
                    f"Incomplete commit header stream at commit {commit_hash}."
                )

            short_hash = tokens[i + 1].decode("ascii", errors="replace").strip()
            author_name = tokens[i + 2].decode("utf-8", errors="surrogateescape")
            author_email = tokens[i + 3].decode("utf-8", errors="surrogateescape")
            author_date_str = tokens[i + 4].decode("ascii", errors="replace").strip()
            parents_str = tokens[i + 5].decode("ascii", errors="replace").strip()
            subject = tokens[i + 6].decode("utf-8", errors="surrogateescape")

            parents = [p for p in parents_str.split(" ") if p]
            try:
                author_date = datetime.fromisoformat(author_date_str)
            except ValueError:
                author_date = datetime.utcnow()

            i += 7

            files_changed: List[FileChange] = []
            commit_numstats = numstat_index.get(commit_hash, {})

            # Scan file status tokens until next COMMIT: marker or stream end
            while i < n:
                st_tok = tokens[i]
                if not st_tok or st_tok == b"\n":
                    i += 1
                    continue
                if st_tok.startswith(b"COMMIT:"):
                    # Start of next commit
                    break

                raw_status = st_tok.lstrip(b"\n").decode("ascii", errors="replace").strip()
                if not raw_status:
                    i += 1
                    continue

                status_code = raw_status[0].upper()

                if status_code == "R":
                    # Rename record: next token is old_path, following token is new_path
                    if i + 2 >= n:
                        raise GitParsingError(
                            f"Truncated rename record in commit {commit_hash}."
                        )
                    old_path = decode_git_path(tokens[i + 1])
                    new_path = decode_git_path(tokens[i + 2])
                    i += 2

                    metrics = commit_numstats.get((old_path, new_path))
                    if metrics is None:
                        raise GitParsingError(
                            f"Pass-matching failure: Rename record ('{old_path}' -> '{new_path}') "
                            f"in commit {commit_hash} has no corresponding numstat entry."
                        )
                    added, deleted, is_bin = metrics
                    files_changed.append(
                        FileChange(
                            status="R",
                            path=new_path,
                            old_path=old_path,
                            additions=added,
                            deletions=deleted,
                            is_binary=is_bin,
                        )
                    )
                else:
                    # Regular file change: A, M, D, T
                    if i + 1 >= n:
                        raise GitParsingError(
                            f"Truncated file record in commit {commit_hash}."
                        )
                    path = decode_git_path(tokens[i + 1])
                    i += 1

                    metrics = commit_numstats.get((path,))
                    if metrics is None:
                        raise GitParsingError(
                            f"Pass-matching failure: File change '{path}' (status={status_code}) "
                            f"in commit {commit_hash} has no corresponding numstat entry."
                        )
                    added, deleted, is_bin = metrics
                    files_changed.append(
                        FileChange(
                            status=status_code,
                            path=path,
                            old_path=None,
                            additions=added,
                            deletions=deleted,
                            is_binary=is_bin,
                        )
                    )
                i += 1

            commits.append(
                CommitRecord(
                    full_hash=commit_hash,
                    short_hash=short_hash,
                    author_name=author_name,
                    author_email=author_email,
                    author_date=author_date,
                    parents=parents,
                    subject=subject,
                    is_merge=len(parents) >= 2,
                    files_changed=files_changed,
                )
            )

        return commits
