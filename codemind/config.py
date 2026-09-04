"""
Configuration settings for CodeMind repository ingestion and analysis.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, Dict, Optional


def load_dotenv_if_present(env_path: Optional[Path] = None) -> None:
    """Load key-value pairs from .env file into os.environ if not already set."""
    if env_path is None:
        candidates = [Path.cwd() / ".env", Path(__file__).parent.parent / ".env"]
    else:
        candidates = [env_path]

    for p in candidates:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass
            break


# Auto-load .env file if available
load_dotenv_if_present()


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
