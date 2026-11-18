"""
Tests for CodeMind Phase 6 Milestone 6: CLI Investigation Command (codemind.cli investigate).
"""

import json
import tempfile
import unittest
from pathlib import Path
from io import StringIO
from unittest.mock import patch

from codemind.cli import investigate_repository


class TestInvestigationCLI(unittest.TestCase):
    """Test suite for the CLI investigate command."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = Path(cls.temp_dir.name)

        service_py = cls.repo_path / "auth_service.py"
        service_py.write_text(
            '"""Authentication service."""\n\n'
            "class AuthService:\n"
            '    """Manages credentials and authentication tokens."""\n'
            "    def verify_token(self, token: str) -> bool:\n"
            '        """Check token validity."""\n'
            '        return token == "valid-token"\n\n'
            "def login_user(token: str) -> bool:\n"
            "    service = AuthService()\n"
            "    return service.verify_token(token)\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_cli_investigate_text_output(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            code = investigate_repository(
                repo_path=str(self.repo_path),
                query="Explain the AuthService class and its methods",
                mock=True,
                as_json=False,
            )
            self.assertEqual(code, 0)
            output = fake_out.getvalue()
            self.assertIn("Agentic Investigation Engine", output)
            self.assertIn("AuthService", output)
            self.assertIn("Execution Plan & Steps", output)

    def test_cli_investigate_json_output(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            code = investigate_repository(
                repo_path=str(self.repo_path),
                query="Who calls verify_token?",
                mock=True,
                as_json=True,
            )
            self.assertEqual(code, 0)
            output = fake_out.getvalue().strip()
            # Must parse as valid JSON
            data = json.loads(output)
            self.assertEqual(data["query"], "Who calls verify_token?")
            self.assertEqual(data["intent"].lower(), "structure")
            self.assertIn(data["status"], ["SUCCESS", "PARTIAL_SUCCESS"])
            self.assertIn("step_results", data)
            self.assertIn("final_answer", data)
            self.assertIn("citations", data)

    def test_cli_investigate_empty_query_returns_error(self):
        with patch("sys.stdout", new=StringIO()), patch("sys.stderr", new=StringIO()):
            code = investigate_repository(
                repo_path=str(self.repo_path),
                query="   ",
                mock=True,
                as_json=False,
            )
            self.assertEqual(code, 1)

    def test_cli_investigate_nonexistent_repo_returns_error(self):
        with patch("sys.stdout", new=StringIO()), patch("sys.stderr", new=StringIO()):
            code = investigate_repository(
                repo_path="nonexistent_folder_xyz_12345",
                query="Where is AuthService defined?",
                mock=True,
                as_json=False,
            )
            self.assertEqual(code, 1)

    def test_cli_investigate_deferred_capability(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            code = investigate_repository(
                repo_path=str(self.repo_path),
                query="Show the commit history of auth_service.py",
                mock=True,
                as_json=True,
            )
            self.assertEqual(code, 0)
            data = json.loads(fake_out.getvalue().strip())
            self.assertEqual(data["intent"].lower(), "evolution")
            has_deferred = any(
                "DEFERRED" in sr.get("status", "") for sr in data.get("step_results", [])
            )
            self.assertTrue(has_deferred)
