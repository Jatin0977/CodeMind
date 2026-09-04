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
        Scan and ingest a repository at the specified local path.

        Args:
            repo_path: Path to the root of the codebase directory.

        Returns:
            IngestedRepository containing all ingested files and summary statistics.

        Raises:
            FileNotFoundError: If the provided path does not exist.
            NotADirectoryError: If the provided path is not a directory.
        """
        path_obj = Path(repo_path).resolve()

        if not path_obj.exists():
            raise FileNotFoundError(f"Repository directory does not exist: {path_obj}")

        if not path_obj.is_dir():
            raise NotADirectoryError(f"Provided path is not a directory: {path_obj}")

        repo_name = path_obj.name
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
            repo_path=str(path_obj),
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
