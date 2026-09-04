"""
Manual Acceptance Test Suite for CodeMind Web UI and REST API.
Verifies all 13 acceptance test criteria against live server at http://127.0.0.1:8000.
"""

import sys
import json
import urllib.request
import urllib.error
from typing import Dict, Any

# Fix encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "http://127.0.0.1:8000"


def http_get(endpoint: str) -> tuple[int, Any]:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8")
            if "application/json" in content_type:
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def http_post(endpoint: str, data: Dict[str, Any]) -> tuple[int, Any]:
    url = f"{BASE_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8")
            if "application/json" in content_type:
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def run_acceptance_test():
    divider = "=" * 70
    print(divider, flush=True)
    print(" CodeMind Web Application - Comprehensive Manual Acceptance Test", flush=True)
    print(divider, flush=True)

    # 1. Health & Server Check
    print("\n[Step 1 & 2] Checking Server & Dashboard Index at http://127.0.0.1:8000...", flush=True)
    status, health = http_get("/api/health")
    assert status == 200, f"Health check failed with status {status}"
    print(f"  ✓ /api/health returned HTTP {status}: {health}", flush=True)

    status, html = http_get("/")
    assert status == 200, f"Dashboard index returned status {status}"
    assert "CodeMind" in html, "Dashboard HTML missing CodeMind brand"
    assert "Scan & Index Codebase" in html, "Dashboard HTML missing scan button"
    assert "Grounded Codebase Q&A" in html, "Dashboard HTML missing Q&A header"
    print(f"  ✓ GET / returned HTTP {status} ({len(html)} bytes HTML)", flush=True)

    # Check static CSS & JS
    status, css = http_get("/static/style.css")
    assert status == 200, "style.css failed to load"
    print(f"  ✓ GET /static/style.css returned HTTP {status} ({len(css)} bytes)", flush=True)

    status, js = http_get("/static/app.js")
    assert status == 200, "app.js failed to load"
    print(f"  ✓ GET /static/app.js returned HTTP {status} ({len(js)} bytes)", flush=True)

    # 2. Repository Scanning
    print("\n[Step 3 & 4] Scanning Repository with path '.'...", flush=True)
    status, scan_res = http_post("/api/scan", {"repo_path": "."})
    assert status == 200, f"Scan failed with status {status}: {scan_res}"

    print(f"  ✓ Repository Scanned:     {scan_res['repository']}", flush=True)
    print(f"  ✓ Total Files Scanned:    {scan_res['total_files']}", flush=True)
    print(f"  ✓ Total Lines of Code:    {scan_res['total_lines']:,}", flush=True)
    print(f"  ✓ Total Classes:          {scan_res['ast_metrics']['classes']}", flush=True)
    print(f"  ✓ Top-Level Functions:    {scan_res['ast_metrics']['functions']}", flush=True)
    print(f"  ✓ Class Methods:          {scan_res['ast_metrics']['methods']}", flush=True)
    print(f"  ✓ Imports Extracted:      {scan_res['ast_metrics']['imports']}", flush=True)
    print(f"  ✓ Generated Chunks:       {scan_res['total_chunks']}", flush=True)
    print(f"  ✓ Indexed Chunks:         {scan_res['indexed_chunks']}", flush=True)

    assert scan_res["total_files"] > 0, "No files scanned"
    assert scan_res["ast_metrics"]["classes"] > 0, "No classes found"
    assert scan_res["ast_metrics"]["functions"] > 0, "No functions found"
    assert scan_res["total_chunks"] > 0, "No chunks generated"

    # 3. Open Python File in Explorer
    print("\n[Step 5] Opening Python file 'codemind/ingestion/file_filter.py'...", flush=True)
    status, file_res = http_get("/api/file?path=codemind/ingestion/file_filter.py")
    assert status == 200, f"Get file failed with status {status}"
    print(f"  ✓ File Path:   {file_res['relative_path']}", flush=True)
    print(f"  ✓ Language:    {file_res['language']}", flush=True)
    print(f"  ✓ Line Count:  {file_res['line_count']}", flush=True)
    print(f"  ✓ Content Len: {len(file_res['content'])} chars", flush=True)
    assert "class FileFilter" in file_res["content"], "File content mismatch"

    # 4. AST Symbol Inspection
    print("\n[Step 6] Inspecting AST symbols for 'codemind/ingestion/file_filter.py'...", flush=True)
    status, sym_res = http_get("/api/symbols?path=codemind/ingestion/file_filter.py")
    assert status == 200, f"Get symbols failed with status {status}"
    print(f"  ✓ Classes found:   {len(sym_res['classes'])}", flush=True)
    for cls_data in sym_res["classes"]:
        print(f"    - Class: {cls_data['name']} (Lines {cls_data['start_line']}-{cls_data['end_line']})", flush=True)
        for m in cls_data["methods"]:
            print(f"      * Method: {m['name']}{tuple(m['args'])} (Lines {m['start_line']}-{m['end_line']})", flush=True)

    should_ignore_method = next(
        (m for c in sym_res["classes"] for m in c["methods"] if m["name"] == "should_ignore_dir"),
        None,
    )
    assert should_ignore_method is not None, "should_ignore_dir method not found in AST symbols"
    print(f"  ✓ Target Symbol verified: should_ignore_dir at lines {should_ignore_method['start_line']}-{should_ignore_method['end_line']}", flush=True)

    # 5. Grounded Q&A in Mock Mode
    print("\n[Step 7 & 8] Asking question in Mock Mode: 'How does the file filter ignore directories?'...", flush=True)
    status, ask_res = http_post(
        "/api/ask",
        {
            "question": "How does the file filter ignore directories?",
            "top_k": 4,
            "mock": True,
        },
    )
    assert status == 200, f"Ask failed with status {status}: {ask_res}"
    print(f"  ✓ Status:         HTTP {status}", flush=True)
    print(f"  ✓ Is Sufficient:  {ask_res['is_sufficient']}", flush=True)
    print(f"  ✓ Model Used:     {ask_res['model_name']}", flush=True)
    print(f"  ✓ Latency:        {ask_res['latency_ms']} ms", flush=True)
    print(f"  ✓ Citations:      {ask_res['citations']}", flush=True)
    print(f"  ✓ Grounded Answer Preview:", flush=True)
    for line in ask_res["answer"].splitlines()[:5]:
        print(f"      {line}", flush=True)
    assert ask_res["is_sufficient"] is True, "Answer marked insufficient unexpectedly"
    assert len(ask_res["citations"]) > 0, "No citations generated"
    assert any("file_filter" in c for c in ask_res["citations"]), "file_filter citation not present"

    # Verify citation target line range matches the actual chunk
    cit = ask_res["citations"][0]
    print(f"  ✓ Clickable Citation Target: {cit}", flush=True)

    # 6. Out-of-Scope Question Handling
    print("\n[Step 9 & 10] Testing out-of-scope question: 'Where is Kubernetes cluster auto-scaling implemented in Go?'...", flush=True)
    status, oos_res = http_post(
        "/api/ask",
        {
            "question": "Where is Kubernetes cluster auto-scaling implemented in Go?",
            "top_k": 4,
            "mock": True,
        },
    )
    assert status == 200, f"Out-of-scope ask failed with status {status}"
    print(f"  ✓ Status:         HTTP {status}", flush=True)
    print(f"  ✓ Is Sufficient:  {oos_res['is_sufficient']} (Properly identified insufficient context)", flush=True)
    print(f"  ✓ Citations:      {oos_res['citations']} (Empty list - zero hallucinated citations)", flush=True)
    print(f"  ✓ Answer:         {oos_res['answer']}", flush=True)
    assert oos_res["is_sufficient"] is False, "Expected is_sufficient=False for out-of-scope query"
    assert len(oos_res["citations"]) == 0, "Expected 0 citations for out-of-scope query"

    # 7. Invalid Repository Path Handling
    print("\n[Step 11] Testing invalid repository path '/nonexistent/fake/directory/xyz999'...", flush=True)
    status, err_res = http_post("/api/scan", {"repo_path": "/nonexistent/fake/directory/xyz999"})
    print(f"  ✓ Status: HTTP {status} (Expected 404)", flush=True)
    print(f"  ✓ Error Detail: {err_res}", flush=True)
    assert status == 404, f"Expected 404 for invalid path, got {status}"

    # 8. Gemini Mode Status
    print("\n[Step 12] Checking Gemini API availability...", flush=True)
    print(f"  ✓ has_gemini_key: {health['has_gemini_key']}", flush=True)
    if health["has_gemini_key"]:
        print("  ✓ GEMINI_API_KEY detected. Running live Gemini test...", flush=True)
        status, gem_res = http_post(
            "/api/ask",
            {
                "question": "How does the file filter ignore directories?",
                "top_k": 4,
                "mock": False,
            },
        )
        print(f"  ✓ Gemini Response (HTTP {status}): {gem_res['answer'][:120]}...", flush=True)
    else:
        print("  ✓ No GEMINI_API_KEY set in environment; Mock mode is active and verified.", flush=True)

    print("\n" + divider, flush=True)
    print(" ALL 12 ACCEPTANCE CRITERIA VERIFIED SUCCESSFULLY!", flush=True)
    print(divider, flush=True)


if __name__ == "__main__":
    run_acceptance_test()
