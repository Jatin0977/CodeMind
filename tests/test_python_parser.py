"""
Unit tests for Python AST parsing and symbol extraction.
"""

import unittest
from codemind.ingestion.models import SourceFile
from codemind.parsing.python_parser import PythonParser
from codemind.parsing.parser_factory import ParserFactory, GLOBAL_PARSER_FACTORY
from codemind.parsing.base_parser import ParsedFile, Symbol


class TestPythonParser(unittest.TestCase):
    """Test AST parsing of Python source code."""

    def setUp(self):
        self.parser = PythonParser()

    def _create_source_file(self, content: str, rel_path: str = "sample.py") -> SourceFile:
        return SourceFile(
            file_path=f"/path/to/{rel_path}",
            relative_path=rel_path,
            file_name=rel_path.split("/")[-1],
            extension=".py",
            language="python",
            file_size=len(content.encode("utf-8")),
            line_count=len(content.splitlines()),
            content=content,
            checksum="dummy_checksum",
        )

    def test_module_docstring_extraction(self):
        code = '"""This is a module docstring."""\nx = 10\n'
        sf = self._create_source_file(code)
        parsed = self.parser.parse(sf)

        self.assertTrue(parsed.is_valid)
        self.assertEqual(parsed.docstring, "This is a module docstring.")

    def test_import_extraction(self):
        code = """import os
import sys as system
from pathlib import Path, PurePath
from ..utils import helper as h
"""
        sf = self._create_source_file(code)
        parsed = self.parser.parse(sf)

        self.assertTrue(parsed.is_valid)
        self.assertEqual(len(parsed.imports), 5)

        imp_dict = {(i.module, i.name, i.alias, i.is_from): i for i in parsed.imports}
        self.assertIn((None, "os", None, False), imp_dict)
        self.assertIn((None, "sys", "system", False), imp_dict)
        self.assertIn(("pathlib", "Path", None, True), imp_dict)
        self.assertIn(("pathlib", "PurePath", None, True), imp_dict)
        self.assertIn(("..utils", "helper", "h", True), imp_dict)

    def test_class_extraction_with_methods(self):
        code = """
@dataclass
class UserService(BaseService, Authenticator):
    \"\"\"Handles user authentication and profiles.\"\"\"

    def __init__(self, db_client: Database):
        \"\"\"Initialize service.\"\"\"
        self.db = db_client

    async def authenticate_user(self, username: str, password: str) -> bool:
        \"\"\"Authenticate user credentials.\"\"\"
        hashed = hash_password(password)
        return self.db.verify(username, hashed)
"""
        sf = self._create_source_file(code)
        parsed = self.parser.parse(sf)

        self.assertTrue(parsed.is_valid)
        self.assertEqual(len(parsed.classes), 1)

        cls_sym = parsed.classes[0]
        self.assertEqual(cls_sym.name, "UserService")
        self.assertEqual(cls_sym.symbol_type, "class")
        self.assertEqual(cls_sym.docstring, "Handles user authentication and profiles.")
        self.assertEqual(cls_sym.bases, ["BaseService", "Authenticator"])
        self.assertIn("dataclass", cls_sym.decorators[0])
        self.assertEqual(len(cls_sym.methods), 2)

        # Method 1: __init__
        init_m = cls_sym.methods[0]
        self.assertEqual(init_m.name, "__init__")
        self.assertEqual(init_m.parent_name, "UserService")
        self.assertEqual(init_m.symbol_type, "method")
        self.assertEqual(init_m.args, ["self", "db_client"])
        self.assertFalse(init_m.is_async)

        # Method 2: authenticate_user (async)
        auth_m = cls_sym.methods[1]
        self.assertEqual(auth_m.name, "authenticate_user")
        self.assertEqual(auth_m.parent_name, "UserService")
        self.assertTrue(auth_m.is_async)
        self.assertEqual(auth_m.args, ["self", "username", "password"])
        self.assertEqual(auth_m.returns, "bool")
        self.assertIn("hash_password", auth_m.calls)
        self.assertIn("self.db.verify", auth_m.calls)

    def test_top_level_function_extraction(self):
        code = """
def calculate_metrics(values: list[float], factor: float = 1.0) -> dict:
    \"\"\"Compute statistical summary.\"\"\"
    total = sum(values)
    count = len(values)
    avg = total / count
    logger.info("Metrics computed")
    return {"avg": avg * factor}
"""
        sf = self._create_source_file(code)
        parsed = self.parser.parse(sf)

        self.assertTrue(parsed.is_valid)
        self.assertEqual(len(parsed.functions), 1)

        fn = parsed.functions[0]
        self.assertEqual(fn.name, "calculate_metrics")
        self.assertEqual(fn.symbol_type, "function")
        self.assertIsNone(fn.parent_name)
        self.assertEqual(fn.args, ["values", "factor"])
        self.assertEqual(fn.returns, "dict")
        self.assertEqual(fn.docstring, "Compute statistical summary.")
        self.assertIn("sum", fn.calls)
        self.assertIn("len", fn.calls)
        self.assertIn("logger.info", fn.calls)

    def test_line_numbers_accurate(self):
        code = """# Comment line 1
# Comment line 2
def first_func():
    return 1

class MyClass:
    def method_one(self):
        pass
"""
        sf = self._create_source_file(code)
        parsed = self.parser.parse(sf)

        self.assertTrue(parsed.is_valid)
        self.assertEqual(parsed.functions[0].start_line, 3)
        self.assertEqual(parsed.functions[0].end_line, 4)

        self.assertEqual(parsed.classes[0].start_line, 6)
        self.assertEqual(parsed.classes[0].end_line, 8)
        self.assertEqual(parsed.classes[0].methods[0].start_line, 7)
        self.assertEqual(parsed.classes[0].methods[0].end_line, 8)

    def test_syntax_error_graceful_handling(self):
        bad_code = """
def broken_syntax(
    print("missing closing paren"
"""
        sf = self._create_source_file(bad_code)
        parsed = self.parser.parse(sf)

        self.assertFalse(parsed.is_valid)
        self.assertIsNotNone(parsed.error)
        self.assertIn("SyntaxError", parsed.error)
        self.assertEqual(len(parsed.classes), 0)
        self.assertEqual(len(parsed.functions), 0)

    def test_parser_factory(self):
        factory = ParserFactory()
        sf_py = self._create_source_file("def hello(): pass", "hello.py")
        parser = factory.get_parser(sf_py)

        self.assertIsNotNone(parser)
        self.assertEqual(parser.supported_language, "python")

        parsed = factory.parse(sf_py)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed.is_valid)
        self.assertEqual(len(parsed.functions), 1)


if __name__ == "__main__":
    unittest.main()
