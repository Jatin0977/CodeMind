"""
Repository loader for scanning and ingesting local codebases.
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Optional, Union, List

from .models import SourceFile, IngestionSummary, IngestedRepository
from .file_filter import FileFilter
from ..config import IngestionConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class RepositoryLoader:
    """Recursively scans a local repository, filters files, and builds SourceFile models."""

    def __init__(self, config: Optional[IngestionConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.file_filter = FileFilter(self.config)

    def load_repository(self, repo_path: Union[str, Path]) -> IngestedRepository:
        """
        Scan and ingest a repository from a local path, ZIP archive, or Git clone URL.

        Args:
            repo_path: Local folder path, path to a .zip archive, or a Git URL (e.g. https://github.com/user/repo.git).

        Returns:
            IngestedRepository containing all ingested files and summary statistics.

        Raises:
            FileNotFoundError: If the provided local path or zip does not exist.
            NotADirectoryError: If the provided path is not a directory or supported archive.
        """
        raw_path_str = str(repo_path).strip()

        # Handle Git URLs (https://, http://, git@)
        if raw_path_str.startswith(("http://", "https://", "git@")):
            return self._load_git_repository(raw_path_str)

        path_obj = Path(repo_path).resolve()

        if not path_obj.exists():
            raise FileNotFoundError(f"Repository path does not exist: {path_obj}")

        # Handle ZIP archives
        if path_obj.is_file() and path_obj.suffix.lower() == ".zip":
            return self._load_zip_repository(path_obj)

        if not path_obj.is_dir():
            raise NotADirectoryError(f"Provided path is neither a directory nor a zip archive: {path_obj}")

        return self._scan_directory(path_obj, repo_name=path_obj.name)

    def _load_git_repository(self, git_url: str) -> IngestedRepository:
        """Clone a remote Git repository to a temporary directory and ingest it."""
        import tempfile
        import subprocess
        import shutil

        temp_dir = tempfile.mkdtemp(prefix="codemind_git_")
        # Extract repo name from URL
        repo_name = git_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        try:
            logger.info(f"Cloning remote repository {git_url} to {temp_dir}...")
            result = subprocess.run(
                ["git", "clone", "--depth", "1", git_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Git clone failed: {result.stderr.strip() or result.stdout.strip()}")

            return self._scan_directory(Path(temp_dir), repo_name=repo_name, original_path=git_url)
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to clone and ingest repository from URL '{git_url}': {e}")

    def _load_zip_repository(self, zip_path: Path) -> IngestedRepository:
        """Extract a ZIP archive to a temporary directory and ingest it."""
        import tempfile
        import zipfile

        temp_dir = tempfile.mkdtemp(prefix="codemind_zip_")
        repo_name = zip_path.stem

        try:
            logger.info(f"Extracting ZIP archive {zip_path} to {temp_dir}...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)

            return self._scan_directory(Path(temp_dir), repo_name=repo_name, original_path=str(zip_path))
        except Exception as e:
            raise RuntimeError(f"Failed to extract and ingest ZIP archive '{zip_path}': {e}")

    def _scan_directory(
        self,
        path_obj: Path,
        repo_name: str,
        original_path: Optional[str] = None,
    ) -> IngestedRepository:
        """Recursively scan a directory, apply filters, and build IngestedRepository model."""
        source_files: List[SourceFile] = []
        summary = IngestionSummary()

        for root, dirs, files in os.walk(path_obj, topdown=True):
            # Prune ignored directories in-place to avoid unnecessary recursion
            dirs[:] = [d for d in dirs if not self.file_filter.should_ignore_dir(d)]

            root_path = Path(root)

            for file_name in sorted(files):
                file_path = root_path / file_name

                should_ignore, reason = self.file_filter.should_ignore_file(file_path, root_path=path_obj)
                if should_ignore:
                    rel_path_str = str(file_path.relative_to(path_obj)).replace("\\", "/")
                    summary.skipped_count += 1
                    summary.skipped_files.append({"path": rel_path_str, "reason": reason or "Ignored"})
                    continue

                # Read file content safely
                source_file = self._read_file(file_path, root_path=path_obj)
                if source_file is not None:
                    source_files.append(source_file)
                    summary.total_files += 1
                    summary.total_size_bytes += source_file.file_size
                    summary.total_lines += source_file.line_count
                    summary.language_breakdown[source_file.language] = (
                        summary.language_breakdown.get(source_file.language, 0) + 1
                    )
                else:
                    rel_path_str = str(file_path.relative_to(path_obj)).replace("\\", "/")
                    summary.skipped_count += 1
                    summary.skipped_files.append({"path": rel_path_str, "reason": "Failed to decode content"})

        return IngestedRepository(
            repo_path=original_path or str(path_obj),
            repo_name=repo_name,
            files=source_files,
            summary=summary,
        )

    def _read_file(self, file_path: Path, root_path: Path) -> Optional[SourceFile]:
        """Read and construct a SourceFile model, handling encoding gracefully."""
        try:
            # Read bytes first
            raw_bytes = file_path.read_bytes()
            file_size = len(raw_bytes)

            # Try primary encoding (UTF-8) with fallback to UTF-8 with BOM or latin-1
            content: Optional[str] = None
            for enc in (self.config.default_encoding, "utf-8-sig", "latin-1"):
                try:
                    content = raw_bytes.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if content is None:
                logger.warning(f"Could not decode file content: {file_path}")
                return None

            checksum = hashlib.sha256(raw_bytes).hexdigest()
            line_count = len(content.splitlines())
            rel_path = str(file_path.relative_to(root_path)).replace("\\", "/")
            language = self.file_filter.get_language(file_path)

            return SourceFile(
                file_path=str(file_path),
                relative_path=rel_path,
                file_name=file_path.name,
                extension=file_path.suffix.lower(),
                language=language,
                file_size=file_size,
                line_count=line_count,
                content=content,
                checksum=checksum,
            )

        except Exception as e:
            logger.warning(f"Error reading file {file_path}: {e}")
            return None
