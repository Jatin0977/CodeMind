"""
Integration tests for Milestone 5: Git API endpoints and CLI commands.
Verifies /api/git/status, /api/git/history, /api/git/churn, /api/git/coupling,
and git-history, git-churn, git-coupling CLI entrypoints in isolated temporary repositories.
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from codemind.web.app import create_app, GLOBAL_STATE
from codemind.cli import git_history_cli, git_churn_cli, git_coupling_cli


@pytest.fixture
def temp_git_repo():
    """Create an isolated, temporary Git repository with synthetic commits."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Committer"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "committer@example.com"], cwd=repo_path, check=True, capture_output=True)

        src_dir = repo_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        # Commit 1: add file_a and file_b
        file_a = src_dir / "service.py"
        file_b = src_dir / "db.py"
        file_a.write_text("def run_service():\n    return 42\n", encoding="utf-8")
        file_b.write_text("def connect_db():\n    return 'connected'\n", encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: initial service and db"], cwd=repo_path, check=True, capture_output=True)

        # Commit 2: co-change both files
        file_a.write_text("def run_service():\n    db = connect_db()\n    return 43\n", encoding="utf-8")
        file_b.write_text("def connect_db():\n    # reconnect logic\n    return 'connected_v2'\n", encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fix: wire service to db"], cwd=repo_path, check=True, capture_output=True)

        yield str(repo_path)


def test_git_api_endpoints_with_scanned_repo(temp_git_repo):
    """Test FastAPI Git endpoints (/api/git/*) against scanned temporary Git repository."""
    app = create_app()
    client = TestClient(app)

    # 1. Scan the repository
    scan_res = client.post("/api/scan", json={"repo_path": temp_git_repo})
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    assert scan_data["git_status"]["is_git_repo"] is True
    assert scan_data["git_commits_count"] >= 2

    # 2. GET /api/git/status
    status_res = client.get("/api/git/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["is_git_repo"] is True
    assert status_data["is_empty"] is False

    # 3. GET /api/git/history
    hist_res = client.get("/api/git/history?limit=10")
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert hist_data["total_commits"] >= 2
    assert len(hist_data["commits"]) >= 2
    # Verify commit details
    c0 = hist_data["commits"][0]
    assert "short_hash" in c0
    assert "author_name" in c0
    assert "subject" in c0

    # History with path filter
    hist_filtered = client.get("/api/git/history?path=src/service.py")
    assert hist_filtered.status_code == 200
    assert hist_filtered.json()["total_commits"] >= 2

    # 4. GET /api/git/churn
    churn_res = client.get("/api/git/churn?limit=10&sort_by=commits")
    assert churn_res.status_code == 200
    churn_data = churn_res.json()
    assert "summary" in churn_data
    assert "hotspots" in churn_data
    assert churn_data["total_returned"] >= 2
    paths = [h["path"] for h in churn_data["hotspots"]]
    assert any("service.py" in p for p in paths)

    # 5. GET /api/git/coupling
    coupling_res = client.get("/api/git/coupling?min_support=1&min_confidence=0.1")
    assert coupling_res.status_code == 200
    coupling_data = coupling_res.json()
    assert "couplings" in coupling_data


def test_git_cli_commands(temp_git_repo, capsys):
    """Test CLI commands (git-history, git-churn, git-coupling) in temporary Git repository."""
    # 1. git-history CLI
    ret_hist_json = git_history_cli(repo_path=temp_git_repo, limit=10, as_json=True)
    assert ret_hist_json == 0
    captured = capsys.readouterr()
    assert "feat: initial service and db" in captured.out or "fix: wire service to db" in captured.out

    ret_hist_text = git_history_cli(repo_path=temp_git_repo, limit=10, as_json=False)
    assert ret_hist_text == 0
    captured_text = capsys.readouterr()
    assert "Git Commit History" in captured_text.out

    # 2. git-churn CLI
    ret_churn_json = git_churn_cli(repo_path=temp_git_repo, limit=10, as_json=True)
    assert ret_churn_json == 0
    captured_churn = capsys.readouterr()
    assert "service.py" in captured_churn.out

    ret_churn_text = git_churn_cli(repo_path=temp_git_repo, limit=10, as_json=False)
    assert ret_churn_text == 0
    captured_churn_text = capsys.readouterr()
    assert "Code Churn Hotspots" in captured_churn_text.out

    # 3. git-coupling CLI
    ret_coup_json = git_coupling_cli(repo_path=temp_git_repo, min_support=1, min_confidence=0.1, as_json=True)
    assert ret_coup_json == 0

    ret_coup_text = git_coupling_cli(repo_path=temp_git_repo, min_support=1, min_confidence=0.1, as_json=False)
    assert ret_coup_text == 0
    captured_coup_text = capsys.readouterr()
    assert "Logical Coupling Discovery" in captured_coup_text.out

    # 4. Error handling on non-git directory
    with tempfile.TemporaryDirectory() as empty_dir:
        ret_non_git = git_history_cli(repo_path=empty_dir)
        assert ret_non_git == 1
        err_out = capsys.readouterr()
        assert "not a Git repository" in err_out.err


def test_git_state_reset_when_scanning_non_git_repo_after_git_repo(temp_git_repo):
    """
    Regression test: verify that scanning a Git repository followed by a non-Git
    repository using the same CodebaseState (GLOBAL_STATE) completely resets Git
    components and ensures the investigation engine uses deferred Phase 7 tools.
    """
    app = create_app()
    client = TestClient(app)

    # 1. First scan: Git repository
    scan_git = client.post("/api/scan", json={"repo_path": temp_git_repo})
    assert scan_git.status_code == 200
    assert GLOBAL_STATE.git_miner is not None
    assert GLOBAL_STATE.git_client is not None
    assert GLOBAL_STATE.git_churn_analyzer is not None
    assert GLOBAL_STATE.git_coupling_analyzer is not None
    assert GLOBAL_STATE.git_status is not None
    assert GLOBAL_STATE.git_status.get("is_git_repo") is True
    assert len(GLOBAL_STATE.git_commits) > 0
    assert len(GLOBAL_STATE.git_couplings) >= 0

    # Verify that during Git repo scan, /api/investigate registers active Git tools
    inv_git = client.post(
        "/api/investigate",
        json={"query": "Show commit history of src/service.py", "mock": True},
    )
    assert inv_git.status_code == 200
    inv_git_data = inv_git.json()
    assert inv_git_data["intent"].lower() == "evolution"
    # In Git repo, git_commit_history should NOT be DEFERRED
    git_step_statuses = [sr.get("status", "") for sr in inv_git_data.get("step_results", [])]
    assert not any("DEFERRED" in s for s in git_step_statuses)

    # 2. Second scan: Non-Git repository using the same CodebaseState
    with tempfile.TemporaryDirectory() as non_git_dir:
        non_git_path = Path(non_git_dir)
        test_file = non_git_path / "calc.py"
        test_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        scan_non_git = client.post("/api/scan", json={"repo_path": str(non_git_path)})
        assert scan_non_git.status_code == 200

        # Verify all Git components are reset and cleared
        assert GLOBAL_STATE.git_client is None
        assert GLOBAL_STATE.git_miner is None
        assert GLOBAL_STATE.git_churn_analyzer is None
        assert GLOBAL_STATE.git_coupling_analyzer is None
        assert GLOBAL_STATE.git_status is None or GLOBAL_STATE.git_status.get("is_git_repo") is False
        assert GLOBAL_STATE.git_commits == []
        assert GLOBAL_STATE.git_churn_summary is None
        assert GLOBAL_STATE.git_couplings == []

        # 3. Verify /api/investigate uses deferred Phase 7 tools for the non-Git repository
        inv_non_git = client.post(
            "/api/investigate",
            json={"query": "Show the commit history of calc.py", "mock": True},
        )
        assert inv_non_git.status_code == 200
        inv_non_git_data = inv_non_git.json()
        assert inv_non_git_data["intent"].lower() == "evolution"

        # Check deferred tool indication in step_results
        has_deferred = any(
            "DEFERRED" in sr.get("status", "") for sr in inv_non_git_data.get("step_results", [])
        )
        assert has_deferred is True
