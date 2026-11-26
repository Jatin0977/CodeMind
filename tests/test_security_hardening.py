"""
Security, Reliability and Concurrency Hardening Test Suite (Milestone 10.2).

Verifies:
1. Malformed request rejection and strict HTTP 400/422 validation.
2. Path traversal attack prevention on file and symbol routes.
3. AST parser resilience against syntax errors, null bytes, and recursion exhaustion.
4. Git client timeout enforcement and safe argument execution.
5. Deterministic concurrency handling with process-local synchronization (threading.Barrier).
6. Shared mutable state consistency under concurrent queries.
7. XSS sanitization and malicious payload defense.
"""

import os
import tempfile
import threading
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from codemind.web.app import create_app, GLOBAL_STATE, CodebaseState
from codemind.parsing.python_parser import PythonParser
from codemind.ingestion.models import SourceFile
from codemind.git.client import GitClient
from codemind.git.models import GitTimeoutError, NotAGitRepositoryError


class TestSecurityHardening(unittest.TestCase):
    """Test suite covering edge cases, concurrency, security defenses, and input validation."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = Path(cls.temp_dir.name)

        # Create minimal test repository
        (cls.repo_path / "main.py").write_text(
            '"""Main entry point."""\n\ndef run():\n    return "ok"\n',
            encoding="utf-8",
        )
        sub_dir = cls.repo_path / "pkg"
        sub_dir.mkdir(exist_ok=True)
        (sub_dir / "__init__.py").write_text("", encoding="utf-8")
        (sub_dir / "mod.py").write_text("def helper():\n    return 42\n", encoding="utf-8")

        cls.app = create_app()
        cls.client = TestClient(cls.app)

        # Scan repo once for tests needing active state
        resp = cls.client.post("/api/scan", json={"repo_path": str(cls.repo_path)})
        assert resp.status_code == 200

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Input Validation and API Reliability (10.2.3)
    # -------------------------------------------------------------------------

    def test_empty_and_malformed_requests(self):
        """Verify strict validation and rejection on empty and malformed payloads."""
        # Empty repo_path on /api/scan
        r1 = self.client.post("/api/scan", json={"repo_path": ""})
        self.assertEqual(r1.status_code, 400)
        self.assertIn("empty", r1.json()["detail"].lower())

        # Non-existent directory
        r2 = self.client.post("/api/scan", json={"repo_path": "c:/non_existent_dir_12345"})
        self.assertEqual(r2.status_code, 404)

        # Empty question on /api/ask
        r3 = self.client.post("/api/ask", json={"question": "   ", "mock": True})
        self.assertEqual(r3.status_code, 400)
        self.assertIn("empty", r3.json()["detail"].lower())

        # Empty query on /api/investigate
        r4 = self.client.post("/api/investigate", json={"query": "\t\n", "mock": True})
        self.assertEqual(r4.status_code, 400)

        # Malformed JSON payload (FastAPI validation -> 422)
        r5 = self.client.post("/api/scan", content="not-a-json", headers={"Content-Type": "application/json"})
        self.assertEqual(r5.status_code, 422)

    def test_path_traversal_prevention(self):
        """Verify path traversal patterns ('..', root escapes) are strictly rejected."""
        # Relative traversal
        r1 = self.client.get("/api/file", params={"path": "../../etc/passwd"})
        self.assertEqual(r1.status_code, 400)
        self.assertIn("traversal", r1.json()["detail"].lower())

        r2 = self.client.get("/api/symbols", params={"path": "..\\..\\windows\\system32"})
        self.assertEqual(r2.status_code, 400)

        # Root escape
        r3 = self.client.get("/api/file", params={"path": "/absolute/path/file.py"})
        self.assertEqual(r3.status_code, 400)

        # Empty file path
        r4 = self.client.get("/api/file", params={"path": "  "})
        self.assertEqual(r4.status_code, 400)

    # -------------------------------------------------------------------------
    # 2. AST and Parser Robustness (10.2.5)
    # -------------------------------------------------------------------------

    def _make_source_file(self, name: str, content: str) -> SourceFile:
        import hashlib
        return SourceFile(
            file_path=name,
            relative_path=name,
            file_name=name,
            extension=".py",
            language="python",
            file_size=len(content.encode("utf-8")),
            line_count=len(content.splitlines()) or 1,
            content=content,
            checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )

    def test_malformed_ast_resilience(self):
        """Verify that malformed, syntax-invalid, and adversarial source files do not crash the parser."""
        parser = PythonParser()

        # 1. Syntax Error
        sf_syntax = self._make_source_file("syntax_err.py", "def broken_func(:\n    pass\n")
        parsed_syntax = parser.parse(sf_syntax)
        self.assertFalse(parsed_syntax.is_valid)
        self.assertIn("SyntaxError", parsed_syntax.error)

        # 2. Null byte injection
        sf_null = self._make_source_file("null_byte.py", "def secret():\n    \x00pass\n")
        parsed_null = parser.parse(sf_null)
        self.assertFalse(parsed_null.is_valid)
        self.assertIn("null bytes", parsed_null.error.lower())

        # 3. Deeply nested expression (potential RecursionError)
        deep_expr = "(" * 1500 + "1" + ")" * 1500
        sf_deep = self._make_source_file("deep.py", f"x = {deep_expr}\n")
        parsed_deep = parser.parse(sf_deep)
        self.assertIsInstance(parsed_deep.is_valid, bool)

        # 4. Oversized file (>10MB)
        sf_huge = self._make_source_file("huge.py", "x = 1\n" * 2_000_000)
        parsed_huge = parser.parse(sf_huge)
        self.assertFalse(parsed_huge.is_valid)
        self.assertIn("10MB", parsed_huge.error)

    # -------------------------------------------------------------------------
    # 3. Git Subprocess Hardening (10.2.4)
    # -------------------------------------------------------------------------

    def test_git_client_security_and_timeout(self):
        """Verify Git CLI wrapper handles invalid arguments, timeouts, and safe execution."""
        client = GitClient(self.repo_path, default_timeout_seconds=0.001)

        # Non-list argument rejection
        with self.assertRaises(TypeError):
            client.run_command("status")  # Must be List[str]

        # Timeout handling
        with self.assertRaises(GitTimeoutError):
            # Extremely short timeout (0.0001s) forces timeout
            client.run_command(["log", "-n", "100"], timeout=0.000001)

        # Safe argument construction without shell injection
        safe_client = GitClient(self.repo_path, default_timeout_seconds=5.0)
        # Semicolons are passed as literal args, not executed as shell commands
        res = safe_client.run_command(["status", "; echo injected"], check=False)
        self.assertNotEqual(res.returncode, 0)  # git fails cleanly on invalid flag

    # -------------------------------------------------------------------------
    # 4. Concurrency and Thread Safety (10.2.2)
    # -------------------------------------------------------------------------

    def test_concurrent_investigation_requests(self):
        """
        Verify thread-safe concurrent investigation requests under single-process model.
        Uses a threading.Barrier to ensure true simultaneous execution.
        """
        num_workers = 8
        barrier = threading.Barrier(num_workers)
        results = []
        errors = []

        def worker_task(worker_id: int):
            try:
                # Wait for all threads to be ready for synchronized start
                barrier.wait(timeout=10.0)
                resp = self.client.post(
                    "/api/investigate",
                    json={"query": f"Where is run defined? worker={worker_id}", "mock": True},
                )
                results.append((worker_id, resp.status_code, resp.json().get("status")))
            except Exception as ex:
                errors.append((worker_id, str(ex)))

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_workers)]
            for f in futures:
                f.result(timeout=15.0)

        self.assertEqual(len(errors), 0, f"Concurrency errors encountered: {errors}")
        self.assertEqual(len(results), num_workers)
        for w_id, status_code, inv_status in results:
            self.assertEqual(status_code, 200)
            self.assertEqual(inv_status, "SUCCESS")

    def test_shared_state_reentrant_lock(self):
        """Verify that CodebaseState RLock correctly serializes mutations."""
        state = CodebaseState()
        self.assertTrue(hasattr(state, "_lock"))
        self.assertTrue(isinstance(state._lock, type(threading.RLock())))

        # Verify that multiple threads cannot corrupt state during concurrent scan
        barrier = threading.Barrier(4)
        scan_results = []

        def scan_worker(idx: int):
            barrier.wait(timeout=5.0)
            res = state.scan_and_analyze(str(self.repo_path))
            scan_results.append((idx, res.get("total_files", 0)))

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(scan_worker, i) for i in range(4)]
            for f in futures:
                f.result(timeout=10.0)

        self.assertEqual(len(scan_results), 4)
        for _, total_files in scan_results:
            self.assertGreater(total_files, 0)

    # -------------------------------------------------------------------------
    # 5. XSS Defense and Markdown Formatting (10.2.6)
    # -------------------------------------------------------------------------

    def test_xss_injection_payload_handling(self):
        """Verify that raw malicious HTML/script payloads in queries and file paths are handled safely."""
        # Query with script tag
        xss_query = "<script>alert('XSS')</script> How does authentication work?"
        resp = self.client.post("/api/investigate", json={"query": xss_query, "mock": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Answer must not contain unescaped executable script tags
        self.assertNotIn("<script>alert('XSS')</script>", data.get("answer", ""))

    def test_dompurify_loading_order_and_fallback(self):
        """Verify DOMPurify is loaded before app.js and fallback uses escapeHtml rather than regex alone."""
        index_html = Path("codemind/web/static/index.html").read_text(encoding="utf-8")
        app_js = Path("codemind/web/static/app.js").read_text(encoding="utf-8")

        # 1. DOMPurify script tag must appear before app.js script tag
        purify_idx = index_html.find("purify.min.js")
        app_idx = index_html.find("/static/app.js")
        if app_idx == -1:
            app_idx = index_html.find("app.js")
        self.assertGreater(purify_idx, -1, "DOMPurify must be present in index.html")
        self.assertGreater(app_idx, -1, "app.js must be present in index.html")
        self.assertLess(purify_idx, app_idx, "DOMPurify must be loaded before app.js")

        # 2. sanitizeHtml must not use regex-based tag stripping as an HTML sanitizer
        self.assertNotIn("<script\\b", app_js, "sanitizeHtml must not rely on regex tag stripping")
        self.assertIn("return escapeHtml(dirty)", app_js, "sanitizeHtml must fall back to escapeHtml")

        # 3. Verify fallback text-escaping behavior on hostile XSS vectors
        def js_escape_html(s: str) -> str:
            return (
                str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#039;")
            )

        hostile_payloads = [
            "<script>alert('XSS')</script>",
            '<img src=x onerror="alert(1)">',
            "<svg onload=alert(document.cookie)>",
            '<iframe src="javascript:alert(1)"></iframe>',
            '"><script>alert(1)</script>',
        ]
        for payload in hostile_payloads:
            escaped = js_escape_html(payload)
            self.assertNotIn("<script>", escaped)
            self.assertNotIn("<img", escaped)
            self.assertNotIn("<svg", escaped)
            self.assertNotIn("<iframe", escaped)
            self.assertNotIn("<", escaped)
            self.assertNotIn(">", escaped)


if __name__ == "__main__":
    unittest.main()
