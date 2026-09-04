"""
File and directory filtering rules for repository ingestion.
"""

import fnmatch
from pathlib import Path
from typing import Tuple, Optional
from ..config import IngestionConfig, DEFAULT_CONFIG


class FileFilter:
    """Filters files and directories based on patterns, sizes, and binary checks."""

    def __init__(self, config: Optional[IngestionConfig] = None):
        self.config = config or DEFAULT_CONFIG

    def should_ignore_dir(self, dir_name: str) -> bool:
        """
        Check if a directory name should be excluded from traversal.
        """
        dir_clean = dir_name.strip()
        if dir_clean in self.config.ignored_directories:
            return True

        for pattern in self.config.ignored_directories:
            if fnmatch.fnmatch(dir_clean, pattern):
                return True

        return False

    def is_binary_by_extension(self, file_path: Path) -> bool:
        """Check if file extension is known to be binary."""
        ext = file_path.suffix.lower()
        return ext in self.config.binary_extensions

    def is_binary_content(self, file_path: Path, sample_size: int = 2048) -> bool:
        """
        Check if the file content appears to be binary by checking for null bytes.
        """
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(sample_size)
                if b"\x00" in chunk:
                    return True
                # Check for high ratio of non-printable characters
                text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
                non_text = chunk.translate(None, text_chars)
                if len(chunk) > 0 and (len(non_text) / len(chunk)) > 0.30:
                    return True
        except Exception:
            return True
        return False

    def should_ignore_file(self, file_path: Path, root_path: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
        """
        Determine if a file should be ignored.
        Returns (should_ignore, reason).
        """
        file_name = file_path.name

        # Check if any parent directory relative to root is ignored
        if root_path is not None:
            try:
                rel_parts = file_path.relative_to(root_path).parts[:-1]
                for part in rel_parts:
                    if self.should_ignore_dir(part):
                        return True, f"Parent directory '{part}' is ignored"
            except ValueError:
                pass

        # Pattern-based file matching (e.g. *.pyc, *.min.js)
        for pattern in self.config.ignored_patterns:
            if fnmatch.fnmatch(file_name, pattern):
                return True, f"Matches ignored pattern '{pattern}'"

        # Check binary by extension
        if self.is_binary_by_extension(file_path):
            return True, f"Binary file extension '{file_path.suffix}'"

        # Check file size limit
        try:
            file_size = file_path.stat().st_size
            if file_size > self.config.max_file_size_bytes:
                return True, f"File size ({file_size} bytes) exceeds limit ({self.config.max_file_size_bytes} bytes)"
            if file_size == 0:
                return True, "Empty file"
        except OSError as e:
            return True, f"Cannot stat file: {e}"

        # Content-based binary check for unfamiliar or extensionless files
        ext = file_path.suffix.lower()
        if ext not in self.config.extension_language_map:
            if self.is_binary_content(file_path):
                return True, "Detected binary content"

        return False, None

    def get_language(self, file_path: Path) -> str:
        """
        Determine the programming or markup language of a file.
        """
        ext = file_path.suffix.lower()
        return self.config.extension_language_map.get(ext, "unknown")
