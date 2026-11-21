# CodeMind — Agentic Codebase Intelligence & Software Evolution Platform

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Phases%201%E2%80%939%20Implemented-brightgreen.svg)
![Tests](https://img.shields.io/badge/Tests-362%20Passing-success.svg)

**CodeMind** is an advanced codebase-intelligence and software evolution platform that enables developers to explore complex codebases, inspect Python AST structures, query multi-relational software knowledge graphs, analyze historical Git evolution, evaluate multi-signal change impact, enforce architectural layering conformance, and uncover maintenance hotspots with debt archetype classification.

> **Current scope:** Comprehensive implementation spanning **Phases 1 through 9**: Multi-source repository ingestion, Python AST analysis, AST-aware chunking and vector retrieval, Grounded RAG with source citations, Multi-Relational Knowledge Graph, Hybrid Graph-Aware Retrieval, Agentic Investigation Engine, Git Temporal Mining, Multi-Signal Change Impact & Test Intelligence, and Full Architecture Intelligence & Risk Analytics.

---

## Table of Contents

- [Implemented Capabilities](#implemented-capabilities)
  - [Phase 1 — Repository Ingestion](#phase-1--repository-ingestion)
  - [Phase 2 — Static Code Analysis with Python AST](#phase-2--static-code-analysis-with-python-ast)
  - [Phase 3 — Semantic Chunking, Retrieval & Grounded Q&A](#phase-3--semantic-chunking-retrieval--grounded-qa)
  - [Phase 4 — Software Knowledge Graph](#phase-4--software-knowledge-graph)
  - [Phase 5 — Hybrid Graph-Aware Retrieval](#phase-5--hybrid-graph-aware-retrieval)
  - [Phase 6 — Agentic Investigation Engine](#phase-6--agentic-investigation-engine)
  - [Phase 7 — Git Temporal Intelligence](#phase-7--git-temporal-intelligence)
  - [Phase 8 — Change Impact & Test Intelligence](#phase-8--change-impact--test-intelligence)
  - [Phase 9 — Architecture Intelligence & Risk Analytics](#phase-9--architecture-intelligence--risk-analytics)
- [System Architecture](#system-architecture)
- [Architecture & Risk Metrics Interpretation](#architecture--risk-metrics-interpretation)
- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
- [Run the Web Application](#run-the-web-application)
- [CLI Reference](#cli-reference)
- [REST API Reference](#rest-api-reference)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [Analysis Limitations & Boundaries](#analysis-limitations--boundaries)
- [Roadmap](#roadmap)

---

## Implemented Capabilities

### Phase 1 — Repository Ingestion
- Multi-source repository intake: local directories, ZIP archives, and Git clone URLs.
- Multi-tier file filtering, noise exclusion (`.git/`, `node_modules/`, `venv/`, `__pycache__/`, `dist/`), binary detection, and metadata extraction.
- Deterministic ingestion summaries with language breakdowns, file statistics, and line counts.

### Phase 2 — Static Code Analysis with Python AST
- Concrete Python AST parsing via Python standard-library `ast`.
- Extraction of classes, functions, methods, parameters, return annotations, docstrings, imports, decorators, and call sites.
- Syntax-error resilience: graceful failure recovery ensuring corrupt or unparseable files do not halt ingestion.

### Phase 3 — Semantic Chunking, Retrieval & Grounded Q&A
- AST-aligned chunking: structural splitting by classes, methods, functions, and module headers.
- Markdown documentation chunking preserving header hierarchies.
- In-memory vector store and embedding-provider abstractions (SentenceTransformers with deterministic mock fallback for offline operation).
- Grounded RAG synthesis with exact file and line citation tags (`[path:start-end]`).
- Insufficient-context protection: explicit limitation reporting when code evidence is missing or ambiguous.

### Phase 4 — Software Knowledge Graph
- Multi-relational directed graph ($G = (V, E)$) constructed via NetworkX.
- Explicit structural relationship edges: `CONTAINS`, `CALLS`, `IMPORTS`, `INHERITS`.
- Topological graph queries: callers, callees, dependencies, dependents, dependency depth, and cycle detection.
- Interactive canvas graph visualizer in the web dashboard.

### Phase 5 — Hybrid Graph-Aware Retrieval
- Dual-mode retrieval combining dense vector similarity with graph topological expansion.
- Forward expansion for execution flows and reverse expansion for blast-radius impact analysis.
- Unified ranking balancing semantic relevance with structural connectivity.

### Phase 6 — Agentic Investigation Engine
- Deterministic five-intent classification: `UNDERSTAND`, `STRUCTURE`, `IMPACT`, `EVOLUTION`, `INSIGHTS`.
- Dynamic investigation planner generating reproducible, dependency-ordered tool execution DAGs.
- Grounded evidence collector capturing line-level references, confidence scores, and provenance.
- Deterministic offline fallback synthesis with prompt-injection defense and untrusted content sandboxing.

### Phase 7 — Git Temporal Intelligence
- Automated commit history mining, author attribution, and revision tracking.
- File-level code churn analytics: commit counts, additions, deletions, and total churn.
- Logical coupling discovery: data-mined co-change patterns via Jaccard similarity, conditional confidence, and support counts.
- Dynamic materialization of temporal co-change edges into the knowledge graph.

### Phase 8 — Change Impact & Test Intelligence
- Multi-Signal Impact Scorer integrating graph reachability, topological centrality, Git churn, and logical coupling.
- Graph-traversal blast-radius analyzer tracing direct and transitive dependents with depth bounds.
- Test Intelligence Engine: discovers and ranks regression test targets across blast radius using heuristic and structural evidence.

### Phase 9 — Architecture Intelligence & Risk Analytics
- **Module Hierarchy Discovery & Source Root Resolution**:
  - Deterministic source root resolver (`repository root` > `src/` > `lib/` > `app/`) with collision detection.
  - Logical package and module grouping with heuristic and config-based layer mapping (`Presentation`, `Domain`, `Infrastructure`, `Utilities`, `UNCLASSIFIED`).
  - PEP 508 dependency manifest parsing (`requirements.txt`, `pyproject.toml`, `setup.py`).
  - Module Quotient Graph ($G_M$) condensation aggregating cross-module physical file edges.
- **AST Complexity Analyzer**:
  - Cyclomatic complexity (McCabe) counting branching statements (`if`, `while`, `for`, `except`, `with`, `assert`).
  - Cognitive branching analysis: boolean operators (`and`, `or`), comprehensions, match-case patterns, and guards.
  - Subtree boundary isolation: prevents double-counting nested closures and class definitions.
  - Weighted Methods per Class (WMC) and module-level aggregation.
- **Architecture Conformance Engine**:
  - Validates cross-module dependencies against configured layer rules.
  - Detects **Upward Layer Leaks** (lower layers importing higher layers; weight 1.0).
  - Detects **Forbidden Imports** (explicitly prohibited dependencies; weight 1.0).
  - Detects **Strict Layer Skipping** (dependencies bypassing adjacent layers; configurable weight 0.4).
  - Calculates the **Architecture Conformance Index (ACI)** using directed cross-module file edges and maximum violation weight deduplication.
- **Package Dependency Cycle Detection**:
  - Tarjan's Strongly Connected Components (SCC) algorithm on the condensed module quotient graph $G_M$.
  - Canonical lexicographical rotation for deterministic cycle path representation.
  - Non-simple SCC member reporting without false simple-cycle path fabrication.
- **Maintenance Hotspots & Risk Intelligence**:
  - Multi-signal hotspot scorer evaluating Cyclomatic Complexity (0.30), PageRank Centrality (0.25), Git Churn (0.30), and Coupling Intensity (0.15).
  - Dynamic active-signal weight renormalization: missing signals (e.g. absent Git history) are proportionally redistributed rather than defaulting to zero.
  - Piecewise continuous synergy interaction multiplier ($\mu \in [1.0, 1.5]$) rewarding compounded risk across high churn, complexity, and centrality ($\theta \ge 0.60$).
  - 95th-percentile clipped min-max normalization guaranteeing bounded scores $[0.0, 1.0]$ resistant to extreme file outliers.
  - Deterministic tie-breaking: `(hotspot_score DESC, base_score DESC, entity_path ASC)`.
  - Calculates the **Repository Risk Score (RRS)** as the mean score of the top-5 hotspot modules.
- **Hotspot Debt Archetypes**:
  - **Brain Module**: High cyclomatic complexity coupled with central architectural bottleneck status.
  - **Volatile Fragile Hotspot**: Rapidly mutating code (high churn) coupled with high cyclomatic complexity.
  - **Shotgun Surgery Catalyst**: High logical/structural coupling and high centrality requiring ripple changes across dependencies.
  - **God Class Candidate / Confirmed God Class**: High WMC, excessive methods, large SLOC, and high centrality.
  - **Stable Core**: High centrality sink with low churn and low complexity.
  - **Normal Component**: Balanced metrics within standard operational thresholds.
- **Evidence Coverage & Analysis State Tracking**:
  - Quantified coverage metric ($C_{\text{evidence}} \in [0.0, 1.0]$) spanning AST parsing, dependency graph, Git churn, temporal coupling, structural coupling, and class graph.
  - Transparent analysis states: `FULL_MULTIDIMENSIONAL`, `PARTIAL_STATIC_ONLY`, `DEGRADED_ANALYSIS`.
  - Missing signal audit: flags `GIT_CHURN_HISTORY_UNAVAILABLE`, `TEMPORAL_COUPLING_INSUFFICIENT_COMMITS`, `INCOMPLETE_AST_PARSING`, etc.
- **Agentic Tool Activation**:
  - Five dedicated architecture investigation tools registered in the agentic tool registry: `GetArchitectureOverviewTool`, `CheckArchitectureConformanceTool`, `DetectPackageCyclesTool`, `DetectMaintenanceHotspotsTool`, `GetEvidenceCoverageTool`.
  - Automatic planning and query routing for `INSIGHTS` intent queries.

---

## System Architecture

```text
                                Local Code Repository / Git / ZIP
                                                |
                                                v
                                  Repository Ingestion Engine
                                                |
                                                v
                                  Python AST Static Analyzer
                                /               |              \
                               v                v               v
                      AST Semantic Chunking   Knowledge Graph   Module Hierarchy & Roots
                               |                |               |
                               v                v               v
                      Dense Vector Store    Graph Engine   Quotient Graph G_M
                               \                /               |
                                v              v                v
                             Hybrid Graph-Aware Retrieval   Architecture Conformance (ACI)
                                       |                    Package Cycles (Tarjan SCC)
                                       v                    Hotspot Detector (RRS)
                             Agentic Investigation Engine       |
                              (Intent / Planner / Tools)        |
                                       |                        |
                                       +------------------------+
                                       |
                                       v
                               Evidence Collector & Synthesizer
                              (Line Citations & Integrity Guard)
                                       |
                     +-----------------+-----------------+
                     |                                   |
                     v                                   v
             FastAPI Web Dashboard               CLI Investigation
            (REST API / Visualizer)             (Structured Markdown / JSON)
```

---

## Architecture & Risk Metrics Interpretation

### 1. Architecture Conformance Index (ACI)
The **Architecture Conformance Index** measures how closely repository module dependencies adhere to defined architectural layering rules:

$$ACI = 100 \times \left(1 - \frac{\sum_{e \in E_{\text{violating}}} w_{\text{eff}}(e)}{|E_{\text{cross}}|}\right)$$

- $|E_{\text{cross}}|$: Count of unique directed cross-module physical file dependency edges $(f_{\text{src}} \to f_{\text{tgt}})$.
- $w_{\text{eff}}(e)$: Maximum violation weight on edge $e$ ($\max(w_v)$):
  - **Upward Layer Leak**: $w = 1.0$ (lower architectural layer imports higher layer).
  - **Forbidden Import**: $w = 1.0$ (explicitly prohibited cross-layer dependency).
  - **Strict Layer Skipping**: $w = 0.4$ (dependency skips an intermediate layer when strict layering is enabled).
- **Scale**: $[0.0\%, 100.0\%]$. $100\%$ indicates total architectural conformance.

### 2. Repository Risk Score (RRS)
The **Repository Risk Score** quantifies overall architectural maintenance debt across the codebase:

$$RRS = \frac{1}{\min(k, |M|)} \sum_{i=1}^{\min(k, |M|)} H_i$$

where $H_i$ represents the final hotspot score of the $i$-th ranked module, and $k = 5$.
- **Scale**: $[0.0, 1.0]$. Lower scores indicate stable, maintainable architectures; scores $\ge 0.50$ indicate significant structural and churn risks.

### 3. Hotspot Score & Weight Renormalization
For each module, the base risk score combines four normalized signals:

$$\text{Base Score} = \sum_{s \in S_{\text{active}}} w_{\text{eff}}(s) \cdot \widetilde{x}_s, \quad w_{\text{eff}}(s) = \frac{w_{\text{base}}(s)}{\sum_{s' \in S_{\text{active}}} w_{\text{base}}(s')}$$

- Base weights: Cyclomatic Complexity ($0.30$), PageRank Centrality ($0.25$), Git Churn ($0.30$), Coupling Intensity ($0.15$).
- When Git data is missing, weights renormalize dynamically over active static signals (Complexity: $0.4286$, Centrality: $0.3571$, Coupling: $0.2143$).
- Multiplied by synergy multiplier $\mu \in [1.0, 1.5]$ for compounding risks, clamped at $1.0$.

### 4. Deterministic PageRank Centrality
Centrality is computed using power iteration with strict lexicographical node ordering and explicit dangling-node redistribution ($d = 0.85$, $\varepsilon = 10^{-6}$), ensuring identical IEEE-754 floating-point results across platforms regardless of input edge ordering.

---

## Technology Stack

- **Language:** Python 3.10+
- **Static Analysis:** Python standard-library `ast`
- **Graph Processing:** NetworkX
- **Backend / Web API:** FastAPI, Uvicorn, Starlette TestClient
- **Vector Retrieval:** In-memory vector store & SentenceTransformers (with deterministic mock fallback)
- **Temporal Mining:** Git CLI wrapper and commit diff miner
- **Testing:** pytest (359 passing tests)

---

## Getting Started

### Prerequisites
- Python 3.10 or newer
- Git

### Installation
```bash
git clone https://github.com/Jatin0977/CodeMind.git
cd CodeMind
python -m pip install -r requirements.txt
```

### Optional: Configure Live LLM
To enable live Gemini-powered synthesis (offline fallback is used by default when unset):
```powershell
$env:GEMINI_API_KEY = "your-api-key"
```

---

## Run the Web Application

Launch the FastAPI application:
```bash
python -m codemind.cli serve --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000` in your browser. From the dashboard:
1. Scan any local repository, ZIP archive, or local path.
2. Explore file trees, AST symbols, and interactive knowledge graphs.
3. Inspect Git churn, logical coupling, and change impact blast radius.
4. Execute architecture investigation queries and review ACI conformance, package cycles, and maintenance hotspots.

---

## CLI Reference

### Agentic Investigation (Phase 6–9)
Run agentic investigations across any repository target:

```bash
# Architecture overview & module hierarchy
python -m codemind.cli investigate "Show the architecture overview and module hierarchy"

# Architecture conformance and layer violations
python -m codemind.cli investigate "Check architecture conformance and layer violations"

# Package-level dependency cycles
python -m codemind.cli investigate "Detect package cycles and circular dependencies"

# Maintenance hotspots and risk archetypes
python -m codemind.cli investigate "Find high-risk maintenance hotspots and explain why"

# Architecture Conformance Index (ACI)
python -m codemind.cli investigate "What is the architecture conformance index (ACI)?"

# Evidence coverage and analysis limitations
python -m codemind.cli investigate "Show architecture evidence coverage and analysis limitations"

# Emit full structured JSON output
python -m codemind.cli investigate "Check architecture conformance" --json
```

### Static Inspection & Symbols (Phases 1–2)
```bash
python -m codemind.cli inspect .
python -m codemind.cli inspect . --detail
python -m codemind.cli inspect . --json
```

### Chunking & Retrieval (Phase 3)
```bash
python -m codemind.cli chunk .
python -m codemind.cli search . "How does file filtering ignore directories?" --top-k 3
python -m codemind.cli ask . "How does the Python AST parser extract functions?" --mock
```

### Knowledge Graph & Impact (Phases 4 & 8)
```bash
python -m codemind.cli graph .
python -m codemind.cli graph . --impact file:codemind/ingestion/models.py
python -m codemind.cli graph . --cycles
```

---

## REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Service health, version, and loaded module capabilities |
| `POST` | `/api/scan` | Ingest and analyze repository (AST, chunks, graph, Git, architecture) |
| `POST` | `/api/ask` | Grounded RAG codebase question-answering with citations |
| `POST` | `/api/investigate` | Full agentic investigation across all 5 canonical intents |
| `GET` | `/api/architecture/overview` | Logical module hierarchy, source roots, and quotient graph summary |
| `GET` | `/api/architecture/conformance` | Architecture Conformance Index (ACI) and layer violations |
| `GET` | `/api/architecture/cycles` | Package-level dependency cycles via Tarjan SCC |
| `GET` | `/api/architecture/hotspots` | Maintenance hotspot ranking, archetypes, and Repository Risk Score |
| `GET` | `/api/graph` | Filtered knowledge graph nodes and edges |
| `GET` | `/api/graph/node` | Direct callers, callees, dependencies, and dependents of a node |
| `GET` | `/api/graph/cycles` | Structural cycle detection across knowledge graph |
| `POST` | `/api/impact/analyze` | Multi-signal change impact and blast-radius traversal |
| `POST` | `/api/impact/tests` | Ranked candidate regression tests for change target |
| `GET` | `/api/git/status` | Git repository availability and branch metadata |
| `GET` | `/api/git/churn` | File-level commit churn hotspot ranking |
| `GET` | `/api/git/coupling` | Data-mined logical co-change coupling pairs |

---

## Running Tests

Run the complete automated test suite:
```bash
python -m pytest tests -v
```

Latest test execution status:
```text
======================== 359 passed, 1 warning in 18.42s ========================
```

Targeted test execution:
```bash
# Phase 9 Architecture Intelligence suite (65 tests)
python -m pytest tests -k "architecture" -v

# Investigation and API suite (27 tests)
python -m pytest tests/test_investigation_*.py tests/test_web.py -v
```

---

## Project Structure

```text
CodeMind/
├── codemind/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py
│   ├── ingestion/             # Phase 1: Repo intake, filtering, models
│   ├── parsing/               # Phase 2: Python AST parser & factory
│   ├── chunking/              # Phase 3: AST & Markdown chunkers
│   ├── embeddings/            # Phase 3: SentenceTransformers & Mock providers
│   ├── vector_store/          # Phase 3: In-memory vector store & factory
│   ├── retrieval/             # Phase 3 & 5: Semantic & Hybrid Graph retrieval
│   ├── rag/                   # Phase 3: Grounded RAG engine & LLM providers
│   ├── graph/                 # Phase 4: Software Knowledge Graph & queries
│   ├── investigation/         # Phase 6 & 9.4: Agentic Investigation Engine
│   │   ├── engine.py          # Orchestration engine
│   │   ├── intent.py          # Five-intent classifier & entity extraction
│   │   ├── planner.py         # Dynamic DAG execution planner
│   │   ├── collector.py       # Grounded evidence collector
│   │   ├── synthesizer.py     # Grounded markdown answer synthesizer
│   │   └── tools/             # Standardized tool implementations
│   │       ├── base.py
│   │       ├── code_tools.py
│   │       ├── graph_tools.py
│   │       ├── temporal_tools.py
│   │       ├── impact_tools.py
│   │       └── architecture_tools.py # Phase 9 investigation tools
│   ├── git/                   # Phase 7: Git mining, churn & coupling
│   ├── impact/                # Phase 8: Multi-Signal Impact & Test Intelligence
│   ├── architecture/          # Phase 9: Architecture Intelligence Subsystem
│   │   ├── __init__.py        # Public module exports
│   │   ├── models.py          # ModuleEntity, LayerDefinition, ConformanceReport, Hotspots
│   │   ├── complexity.py      # AST Cyclomatic & Cognitive complexity analyzer
│   │   ├── discovery.py       # Module discovery, source roots, quotient graph G_M
│   │   ├── conformance.py     # Rule engine, upward leaks, forbidden imports, ACI
│   │   └── hotspots.py        # Multi-signal hotspot detector, RRS, debt archetypes
│   └── web/                   # Web application & REST endpoints
│       ├── app.py
│       └── static/            # Dashboard UI, CSS, interactive canvas visualizer
├── tests/                     # 359 automated tests covering Phases 1–9
├── requirements.txt
├── README.md
└── .gitignore
```

---

## Analysis Limitations & Boundaries

1. **Static AST Analysis Boundary**:
   - Analysis is based on static AST parsing; dynamic imports (`__import__`, `importlib`), runtime reflection, and dynamic dependency injection cannot be fully captured without execution.
2. **Git Temporal Intelligence Boundary**:
   - Churn and logical coupling reflect repository commit log records; shallow clones (`--depth 1`), squashed history, or repository re-writes influence statistical confidence.
3. **Graph Impact Reachability**:
   - Graph impact analysis evaluates structural reachability in the analyzed AST graph; it represents potential change blast radius, not guaranteed dynamic runtime failures.
4. **Offline Mock Mode**:
   - In environments without live Gemini API credentials, deterministic mock providers and offline rule-based synthesizers ensure reproducible execution without external network dependency.

---

## Roadmap

The project implementation follows the master roadmap across the 10 technical phases:

- [x] **Phase 1: Foundation and Repository Ingestion**
- [x] **Phase 2: Static Code Analysis (Python AST)**
- [x] **Phase 3: Semantic Intelligence (AST Chunking, Vector Retrieval, Grounded Q&A)**
- [x] **Phase 4: Software Knowledge Graph (NetworkX Multi-Relational Graph)**
- [x] **Phase 5: Hybrid Graph-Aware Retrieval (Vector + Topological Expansion)**
- [x] **Phase 6: Agentic Investigation Engine (Intent, Planning, Synthesis)**
- [x] **Phase 7: Git Temporal Intelligence (Commit Mining, Churn, Logical Coupling)**
- [x] **Phase 8: Change Impact and Test Intelligence (Multi-Signal Impact, Test Discovery)**
- [x] **Phase 9: Architecture Intelligence & Risk Insights (Hierarchy, Conformance, Cycles, Hotspots, RRS)**
- [ ] **Phase 10: Evaluation, Optimization and Deployment (Systematic Benchmarking & Packaging)**

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
