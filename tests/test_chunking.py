"""
Unit tests for AST-aware code chunking and document chunking.
"""

import unittest
from codemind.ingestion.models import SourceFile
from codemind.chunking.models import CodeChunk
from codemind.chunking.ast_chunker import ASTCodeChunker
from codemind.chunking.doc_chunker import DocChunker
from codemind.chunking.chunker_factory import ChunkerFactory, GLOBAL_CHUNKER_FACTORY


class TestChunking(unittest.TestCase):
    """Test ASTCodeChunker and DocChunker logic."""

    def _create_source_file(
        self,
        content: str,
        rel_path: str = "src/example.py",
        language: str = "python",
    ) -> SourceFile:
        return SourceFile(
            file_path=f"/repo/{rel_path}",
            relative_path=rel_path,
            file_name=rel_path.split("/")[-1],
            extension="." + rel_path.split(".")[-1],
            language=language,
            file_size=len(content.encode("utf-8")),
            line_count=len(content.splitlines()),
            content=content,
            checksum="dummy_checksum",
        )

    def test_function_chunking(self):
        code = """def add_numbers(a: int, b: int) -> int:
    \"\"\"Add two numbers.\"\"\"
    return a + b
"""
        sf = self._create_source_file(code, "src/math.py", "python")
        chunker = ASTCodeChunker()
        chunks = chunker.chunk(sf)

        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        self.assertEqual(len(func_chunks), 1)

        c = func_chunks[0]
        self.assertEqual(c.symbol_name, "add_numbers")
        self.assertIsNone(c.parent_symbol)
        self.assertEqual(c.start_line, 1)
        self.assertEqual(c.end_line, 3)
        self.assertIn("def add_numbers(a, b) -> int", c.signature)
        self.assertEqual(c.relative_path, "src/math.py")
        self.assertEqual(c.language, "python")
        self.assertTrue(len(c.chunk_id) == 16)

    def test_class_and_method_chunking(self):
        code = """class AuthService:
    \"\"\"Authentication service class.\"\"\"

    def login(self, username: str) -> bool:
        \"\"\"Log user in.\"\"\"
        return True

    def logout(self) -> None:
        \"\"\"Log user out.\"\"\"
        pass
"""
        sf = self._create_source_file(code, "src/auth.py", "python")
        chunker = ASTCodeChunker()
        chunks = chunker.chunk(sf)

        # Should produce 1 class header chunk + 2 method chunks
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        method_chunks = [c for c in chunks if c.chunk_type == "method"]

        self.assertEqual(len(class_chunks), 1)
        self.assertEqual(class_chunks[0].symbol_name, "AuthService")
        self.assertIn("class AuthService:", class_chunks[0].signature)

        self.assertEqual(len(method_chunks), 2)

        login_m = next(m for m in method_chunks if "login" in m.symbol_name)
        self.assertEqual(login_m.symbol_name, "AuthService.login")
        self.assertEqual(login_m.parent_symbol, "AuthService")
        self.assertEqual(login_m.start_line, 4)
        self.assertEqual(login_m.end_line, 6)

        logout_m = next(m for m in method_chunks if "logout" in m.symbol_name)
        self.assertEqual(logout_m.symbol_name, "AuthService.logout")
        self.assertEqual(logout_m.parent_symbol, "AuthService")
        self.assertEqual(logout_m.start_line, 8)
        self.assertEqual(logout_m.end_line, 10)

    def test_module_header_chunking(self):
        code = """\"\"\"Module documentation header.\"\"\"
import os
import sys
from pathlib import Path

def run():
    pass
"""
        sf = self._create_source_file(code, "src/main.py", "python")
        chunker = ASTCodeChunker()
        chunks = chunker.chunk(sf)

        header_chunks = [c for c in chunks if c.chunk_type == "module_header"]
        self.assertEqual(len(header_chunks), 1)
        hc = header_chunks[0]
        self.assertEqual(hc.start_line, 1)
        self.assertEqual(hc.end_line, 4)
        self.assertIn("Module documentation header.", hc.content)
        self.assertIn("from pathlib import Path", hc.content)

    def test_doc_chunking(self):
        markdown_text = """# CodeMind Platform

CodeMind is an agentic platform.

## Architecture

Here is the system architecture.

### Ingestion Subsystem

Details on file ingestion.

## Getting Started

Run `python -m codemind.cli inspect .`
"""
        sf = self._create_source_file(markdown_text, "docs/README.md", "markdown")
        chunker = DocChunker()
        chunks = chunker.chunk(sf)

        self.assertEqual(len(chunks), 4)

        titles = [c.symbol_name for c in chunks]
        self.assertIn("CodeMind Platform", titles)
        self.assertIn("Architecture", titles)
        self.assertIn("Ingestion Subsystem", titles)
        self.assertIn("Getting Started", titles)

        # Check parent hierarchy for 'Ingestion Subsystem'
        sub_chunk = next(c for c in chunks if c.symbol_name == "Ingestion Subsystem")
        self.assertEqual(sub_chunk.parent_symbol, "Architecture")
        self.assertEqual(sub_chunk.chunk_type, "doc_section")

    def test_chunker_factory_dispatch(self):
        factory = ChunkerFactory()
        py_sf = self._create_source_file("def foo(): pass", "foo.py", "python")
        md_sf = self._create_source_file("# Title", "guide.md", "markdown")

        py_chunks = factory.chunk_file(py_sf)
        md_chunks = factory.chunk_file(md_sf)

        self.assertTrue(len(py_chunks) > 0)
        self.assertTrue(len(md_chunks) > 0)
        self.assertEqual(py_chunks[0].chunk_type, "function")
        self.assertEqual(md_chunks[0].chunk_type, "doc_section")


if __name__ == "__main__":
    unittest.main()
