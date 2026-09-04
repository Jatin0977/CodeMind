"""
Unit tests for CodeMind repository ingestion, file filtering, and metadata extraction.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from codemind.config import IngestionConfig
from codemind.ingestion.file_filter import FileFilter
from codemind.ingestion.models import SourceFile, IngestionSummary, IngestedRepository
from codemind.ingestion.repo_loader import RepositoryLoader


class TestFileFilter(unittest.TestCase):
    """Test file and directory filtering rules."""

    def setUp(self):
        self.config = IngestionConfig()
        self.file_filter = FileFilter(self.config)

    def test_should_ignore_ignored_directories(self):
        self.assertTrue(self.file_filter.should_ignore_dir(".git"))
        self.assertTrue(self.file_filter.should_ignore_dir("node_modules"))
        self.assertTrue(self.file_filter.should_ignore_dir("venv"))
        self.assertTrue(self.file_filter.should_ignore_dir("__pycache__"))
        self.assertTrue(self.file_filter.should_ignore_dir(".pytest_cache"))
        self.assertTrue(self.file_filter.should_ignore_dir("dist"))
        self.assertTrue(self.file_filter.should_ignore_dir("build"))

    def test_should_not_ignore_source_directories(self):
        self.assertFalse(self.file_filter.should_ignore_dir("src"))
        self.assertFalse(self.file_filter.should_ignore_dir("codemind"))
        self.assertFalse(self.file_filter.should_ignore_dir("tests"))
        self.assertFalse(self.file_filter.should_ignore_dir("docs"))

    def test_is_binary_by_extension(self):
        self.assertTrue(self.file_filter.is_binary_by_extension(Path("image.png")))
        self.assertTrue(self.file_filter.is_binary_by_extension(Path("compiled.pyc")))
        self.assertTrue(self.file_filter.is_binary_by_extension(Path("app.exe")))
        self.assertTrue(self.file_filter.is_binary_by_extension(Path("data.sqlite")))
        self.assertFalse(self.file_filter.is_binary_by_extension(Path("script.py")))
        self.assertFalse(self.file_filter.is_binary_by_extension(Path("README.md")))

    def test_language_detection(self):
        self.assertEqual(self.file_filter.get_language(Path("test.py")), "python")
        self.assertEqual(self.file_filter.get_language(Path("notes.md")), "markdown")
        self.assertEqual(self.file_filter.get_language(Path("config.json")), "json")
        self.assertEqual(self.file_filter.get_language(Path("schema.yaml")), "yaml")
        self.assertEqual(self.file_filter.get_language(Path("unknown.xyz123")), "unknown")


class TestRepositoryLoader(unittest.TestCase):
    """Test repository scanning and ingestion."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

        # Create a sample repository structure
        # Valid files
        (self.root / "README.md").write_text("# Test Project\nSample doc content.", encoding="utf-8")
        src_dir = self.root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "main.py").write_text("def run():\n    print('hello')\n", encoding="utf-8")
        (src_dir / "utils.py").write_text("import os\n\ndef helper():\n    return 42\n", encoding="utf-8")

        # Nested directory
        sub_dir = src_dir / "sub"
        sub_dir.mkdir()
        (sub_dir / "module.py").write_text("class Sample:\n    pass\n", encoding="utf-8")

        # Ignored directory (.git)
        git_dir = self.root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")

        # Ignored directory (node_modules)
        nm_dir = self.root / "node_modules"
        nm_dir.mkdir()
        (nm_dir / "package.json").write_text("{}", encoding="utf-8")

        # Ignored directory (__pycache__)
        pycache_dir = src_dir / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "main.cpython-312.pyc").write_bytes(b"\x00\x01\x02\x03")

        # Binary file
        (self.root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_repository_success(self):
        loader = RepositoryLoader()
        repo = loader.load_repository(self.root)

        self.assertIsInstance(repo, IngestedRepository)
        self.assertEqual(repo.summary.total_files, 4)  # README.md, main.py, utils.py, module.py

        rel_paths = {f.relative_path for f in repo.files}
        expected_paths = {"README.md", "src/main.py", "src/utils.py", "src/sub/module.py"}
        self.assertEqual(rel_paths, expected_paths)

    def test_ignored_directories_not_scanned(self):
        loader = RepositoryLoader()
        repo = loader.load_repository(self.root)

        rel_paths = [f.relative_path for f in repo.files]
        for path in rel_paths:
            self.assertNotIn(".git", path)
            self.assertNotIn("node_modules", path)
            self.assertNotIn("__pycache__", path)
            self.assertFalse(path.endswith(".png"))
            self.assertFalse(path.endswith(".pyc"))

    def test_source_file_metadata(self):
        loader = RepositoryLoader()
        repo = loader.load_repository(self.root)

        main_file = repo.get_file_by_relative_path("src/main.py")
        self.assertIsNotNone(main_file)
        self.assertEqual(main_file.language, "python")
        self.assertEqual(main_file.extension, ".py")
        self.assertEqual(main_file.line_count, 2)
        self.assertTrue(main_file.is_python)
        self.assertFalse(main_file.is_documentation)
        self.assertTrue(len(main_file.checksum) == 64)  # SHA-256 length

        readme_file = repo.get_file_by_relative_path("README.md")
        self.assertIsNotNone(readme_file)
        self.assertEqual(readme_file.language, "markdown")
        self.assertTrue(readme_file.is_documentation)

    def test_helpers_get_python_and_doc_files(self):
        loader = RepositoryLoader()
        repo = loader.load_repository(self.root)

        py_files = repo.get_python_files()
        doc_files = repo.get_doc_files()

        self.assertEqual(len(py_files), 3)
        self.assertEqual(len(doc_files), 1)

    def test_invalid_path_raises_error(self):
        loader = RepositoryLoader()
        with self.assertRaises(FileNotFoundError):
            loader.load_repository(self.root / "non_existent_directory")


if __name__ == "__main__":
    unittest.main()
