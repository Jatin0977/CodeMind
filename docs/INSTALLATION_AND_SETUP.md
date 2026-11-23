# CodeMind â€” Installation & Setup Guide

This guide details the step-by-step installation, environment configuration, package build, CLI execution, and troubleshooting procedures for CodeMind.

---

## 1. Prerequisites

Before installing CodeMind, ensure your environment meets the following requirements:

| Component | Minimum Version | Recommended Version | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | 3.11.0 | 3.11.9 or 3.12.x | Standard library AST features require Python $\ge$ 3.11. |
| **Git** | 2.25.0+ | Latest stable | Required for Git temporal intelligence and commit mining. |
| **Pip** | 23.0+ | Latest stable | Python package installer. |
| **Operating System** | Windows 10/11, Ubuntu 22.04+, macOS 13+ | Any | Cross-platform compatible. |

---

## 2. Quickstart Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/Jatin0977/CodeMind.git
cd CodeMind
```

### Step 2: Create and Activate a Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On Linux / macOS (Bash):**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

#### Option A: Development & Testing (Recommended)
Installs runtime dependencies, test tools (pytest, pytest-cov), and links the CLI in editable mode:
```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements-dev.txt
pip install -e .
```

#### Option B: Runtime Only
Installs only minimal runtime dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

#### Option C: Production Wheel Build & Install
Builds the standalone Python wheel (`.whl`) and source distribution (`.tar.gz`) bundling all static web assets:
```bash
pip install build
python -m build
pip install dist/codemind-1.0.0-py3-none-any.whl
```

---

## 3. Environment Configuration

CodeMind is pre-configured to operate **100% offline out-of-the-box** using deterministic mock embeddings and template synthesis. To connect real external LLM providers or customize server bindings, configure the following environment variables:

| Variable | Default Value | Allowed Values | Description |
| :--- | :--- | :--- | :--- |
| `CODEMIND_HOST` | `127.0.0.1` | IP address (e.g. `0.0.0.0`) | Server bind address. |
| `CODEMIND_PORT` | `8000` | Integer (1â€“65535) | Server listen port. |
| `CODEMIND_EMBEDDING_PROVIDER` | `mock` | `mock`, `sentence-transformers` | Embedding engine. `mock` requires zero internet connectivity. |
| `CODEMIND_LLM_PROVIDER` | `mock` | `mock`, `openai`, `anthropic` | LLM generation provider for Q&A and investigation synthesis. |
| `OPENAI_API_KEY` | *None* | `sk-...` | Required if `CODEMIND_LLM_PROVIDER=openai`. |
| `ANTHROPIC_API_KEY` | *None* | `sk-ant-...` | Required if `CODEMIND_LLM_PROVIDER=anthropic`. |

### Setting Environment Variables

**Windows (PowerShell):**
```powershell
$env:CODEMIND_EMBEDDING_PROVIDER = "mock"
$env:CODEMIND_LLM_PROVIDER = "mock"
```

**Linux / macOS (Bash):**
```bash
export CODEMIND_EMBEDDING_PROVIDER="mock"
export CODEMIND_LLM_PROVIDER="mock"
```

---

## 4. Running the Application

### 4.1 Launching the Interactive Web Dashboard

Using the registered console script:
```bash
codemind web --port 8000
```

Or using Uvicorn directly:
```bash
uvicorn codemind.web.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

> [!IMPORTANT]
> **Single-Worker Requirement:**
> Always run Uvicorn with `--workers 1`. CodeMind maintains the Software Knowledge Graph and in-memory search indices in process-local state. Running multiple worker processes partitions state across separate memory address spaces.

Once started, navigate to:
- **Interactive UI:** `http://localhost:8000`
- **Swagger API Docs:** `http://localhost:8000/docs`

---

### 4.2 Using the CodeMind CLI

After installation, the `codemind` command is available directly in your terminal:

```bash
# Display CLI commands and options
codemind --help

# Ingest and scan a repository
codemind scan .

# Run grounded codebase Q&A with citations
codemind ask "How does the Python parser handle syntax errors?"

# Execute an agentic investigation
codemind investigate "What is the change impact if we modify GraphBuilder?"

# Calculate blast radius for specific files
codemind impact codemind/graph/builder.py

# Evaluate architecture conformance and maintenance hotspots
codemind architecture
```

---

## 5. Verification & Health Checks

Verify your installation by running the automated validation suite:

```bash
# 1. Verify CLI smoke check
codemind --help

# 2. Run the full unit and integration test suite (385 tests)
python -m pytest tests -v

# 3. Run performance acceptance benchmark targets
python scripts/benchmark_targets.py
```

Expected Benchmark Target Output:
```
10,000-Node Subgraph Traversal:  ~1.08 ms  (Target <= 150 ms) -> PASSED
Single-File AST Parsing (1.3k LOC): ~9.32 ms  (Target <= 100 ms) -> PASSED
Investigation Planning & Synthesis: ~0.28 ms  (Target <= 5,000 ms) -> PASSED
```

---

## 6. Troubleshooting

### Issue: `SentenceTransformer model 'all-MiniLM-L6-v2' not cached locally`
- **Cause:** No internet access or HuggingFace connection timeout.
- **Resolution:** CodeMind automatically detects network absence and falls back gracefully to its deterministic 64-dimensional mock embedding provider. No action required. To suppress the warning, set:
  ```powershell
  $env:CODEMIND_EMBEDDING_PROVIDER = "mock"
  ```

### Issue: `modified: tests/benchmarks/fixtures/repo_small (untracked content)`
- **Cause:** Historical issue where nested `.git` folders were present in test fixtures.
- **Resolution:** Fully resolved in commit `e020e1c`. If encountered on an older branch, run:
  ```bash
  git rm --cached tests/benchmarks/fixtures/repo_*
  git add tests/benchmarks/fixtures/
  ```

### Issue: `Port 8000 already in use`
- **Cause:** Another process is listening on port 8000.
- **Resolution:** Launch CodeMind on an alternate port:
  ```bash
  codemind web --port 8080
  ```

### Issue: `Lockfile Absence Note`
- CodeMind defines dependency bounds using PEP 517/621 specifications (`pyproject.toml` and `requirements.txt`). An exact hash-pinned lockfile (`requirements.lock`) is not checked into version control. If exact reproducible hashes are required in deployment, generate a lockfile via `pip freeze > requirements.lock`.
