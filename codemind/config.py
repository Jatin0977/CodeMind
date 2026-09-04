"""
Configuration settings for CodeMind repository ingestion and analysis.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, Dict


@dataclass
class IngestionConfig:
    """Configuration for codebase scanning and filtering."""

    # Default directories to ignore during ingestion
    ignored_directories: Set[str] = field(default_factory=lambda: {
        ".git",
        ".svn",
        ".hg",
        ".bzr",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "eggs",
        ".eggs",
        "*.egg-info",
        ".tox",
        ".nox",
        ".idea",
        ".vscode",
        ".history",
        ".cache",
        "coverage",
        "htmlcov",
        "site-packages",
    })

    # Default file patterns / extensions to ignore
    ignored_patterns: Set[str] = field(default_factory=lambda: {
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.so",
        "*.dll",
        "*.dylib",
        "*.exe",
        "*.bin",
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        "*.log",
        "*.tmp",
        "*.bak",
        "*.swp",
        "*.DS_Store",
        "Thumbs.db",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "*.min.js",
        "*.min.css",
        "*.map",
    })

    # Non-text / binary extensions
    binary_extensions: Set[str] = field(default_factory=lambda: {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz",
        ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".img",
        ".pyc", ".class", ".o", ".obj",
        ".pkl", ".pickle", ".parquet", ".feather", ".npy", ".npz",
        ".db", ".sqlite", ".sqlite3"
    })

    # Supported source code and doc extensions mapped to language
    extension_language_map: Dict[str, str] = field(default_factory=lambda: {
        ".py": "python",
        ".pyw": "python",
        ".md": "markdown",
        ".markdown": "markdown",
        ".rst": "restructuredtext",
        ".txt": "text",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".scss": "scss",
        ".sql": "sql",
        ".sh": "shell",
        ".bash": "shell",
        ".ps1": "powershell",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
    })

    # Maximum allowed single file size in bytes (e.g. 5 MB) to avoid memory overload
    max_file_size_bytes: int = 5 * 1024 * 1024

    # Character encoding preference
    default_encoding: str = "utf-8"


DEFAULT_CONFIG = IngestionConfig()
