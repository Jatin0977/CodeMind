# CodeMind â€” User Guide

This guide provides a comprehensive, hands-on walkthrough for developers, software architects, and evaluators using CodeMind via both the **Interactive Web Dashboard** and the **Command-Line Interface (CLI)**.

---

## 1. Getting Started & Repository Ingestion

### Via Web Dashboard
1. Start CodeMind: `codemind web --port 8000`
2. Open your browser at `http://localhost:8000`.
3. In the **Repository Source** input box at the top:
   - Enter `.` to scan the current CodeMind codebase.
   - Or enter an absolute folder path (e.g. `C:\Users\...\my-project`).
   - Or enter a path to a `.zip` archive or a remote Git URL (`https://github.com/user/repo.git`).
4. Click **âš¡ Scan & Analyze Codebase**.
5. The dashboard ingests all files, filters noise, parses the concrete Python AST, builds the Software Knowledge Graph, indexes vector chunks, and mines Git history.
6. The top status chips update to show detected components:
   - **Ingestion:** 45 files analyzed
   - **Static AST:** Concrete Python AST parsed
   - **Graph:** Active (372 nodes, 343 edges)
   - **Temporal:** Git Mining active (15 commits)

### Via CLI
```bash
# Ingest and scan the current working directory
codemind scan .

# Ingest an external repository
codemind scan /path/to/another/repo
```

---

## 2. Exploring AST Symbols & Static Metrics

### Web Interface
- **Left Panel (File Explorer):** Use the search bar to filter files by path or name. Click any file (e.g. `codemind/web/app.py`).
- **Center Panel (AST Symbol Inspector):**
  - Displays extracted `Classes` with inheritance bases and docstrings.
  - Displays `Methods` and standalone `Functions` with parameter signatures and return annotations.
  - Displays all `Imports` and dependencies.
  - Selecting any symbol highlights its declaration boundaries in the source code.
- **Center Panel (Static Analysis Overview):**
  - Visualizes file size distributions, line counts, language breakdown, and member counts.

### CLI
```bash
# Inspect AST symbols of a specific file
codemind symbols codemind/parsing/python_parser.py
```

---

## 3. Grounded Codebase Q&A with Citations

CodeMind allows developers to ask natural-language questions about implementation logic, data structures, and algorithms.

### Web Interface
1. Navigate to the **ðŸ¤– Grounded Codebase Q&A** tab.
2. Enter your question in the text area (or click one of the quick sample chips).
3. Select the number of evidence chunks to retrieve (e.g. 3 or 4 chunks).
4. Click **Ask Question** (or press `Ctrl+Enter`).
5. **Inspect Response:**
   - The answer is structured in GitHub-flavored markdown.
   - At the bottom of the answer, expand the **Verified Source Citations** panel.
   - Every citation displays the exact file path, start line, and end line.
   - Click a citation card to inspect the exact retrieved code chunk in the right-hand Code Viewer.

### CLI
```bash
codemind ask "How does the Python parser extract AST classes?"
```

---

## 4. Software Knowledge Graph Exploration

CodeMind models the entire codebase as a multi-relational directed graph:
- **Nodes:** `FILE`, `CLASS`, `FUNCTION`, `METHOD`, `MODULE`, `PACKAGE`, `COMMIT`.
- **Edges:** `CONTAINS`, `CALLS`, `IMPORTS`, `INHERITS`, `COMMITTED_IN`, `CO_CHANGED_WITH`.

### Web Interface
1. Click the **ðŸ•¸ï¸ Software Knowledge Graph** tab.
2. View graph statistics: Total Nodes, Edges, Density, and Component counts.
3. Select an entity type filter (`ALL`, `FILES`, `CLASSES`, `FUNCTIONS`).
4. Click any node in the interactive canvas or search table to inspect its 1-hop and 2-hop topological neighborhood (incoming callers, outgoing calls, imported packages, inheritance tree).

### CLI
```bash
# Query topological neighbors of a function
codemind graph neighbors "func::codemind/web/app.py::create_app"
```

---

## 5. Agentic Investigation Engine

When queries require multi-step reasoning, CodeMind's autonomous **Agentic Investigation Engine** executes a 5-stage workflow: Intent Classification $\to$ Dynamic Planning $\to$ Evidence Collection $\to$ Topological Expansion $\to$ Grounded Synthesis.

### The 5 Canonical Intents

| Intent | Purpose | Example Query |
| :--- | :--- | :--- |
| **`UNDERSTAND`** | Semantic explanation of concepts and algorithms. | *"How does the file filter ignore noisy directories and binary files?"* |
| **`STRUCTURE`** | Architectural hierarchies and class inheritance. | *"Show the class hierarchy and dependencies for SemanticRetriever."* |
| **`IMPACT`** | Blast radius and downstream ripple effects. | *"What is the change impact if we modify the GraphBuilder class?"* |
| **`EVOLUTION`** | Git commit logs, code churn, and author ownership. | *"Show the commit history and churn for auth_service.py."* |
| **`INSIGHTS`** | Technical debt, hotspots, and architectural violations. | *"What are the maintenance hotspots and high-risk modules?"* |

### Web Interface
1. Click the **ðŸ•µï¸ Agentic Investigation** tab.
2. Enter your query or click an intent chip.
3. CodeMind dynamically displays:
   - **Identified Intent:** Displayed as a colored badge (`UNDERSTAND`, `IMPACT`, etc.).
   - **Execution Plan:** The exact ordered tools executed by the planner.
   - **Findings & Synthesis:** Grounded synthesis formatted in clear markdown.
   - **Verified Citations:** File and line references confirming zero hallucination.
   - **Analysis Boundaries:** Explicit notes on any partial or unavailable signals.

### CLI
```bash
codemind investigate "What is the change impact if we modify the GraphBuilder class?"
```

---

## 6. Git Temporal Intelligence & Historical Evolution

CodeMind mines the commit history to uncover temporal risks that static analysis alone cannot detect.

### Web Interface
1. Click the **â³ Evolution & Git Intelligence** tab.
2. **Commit History Stream:** Scroll through chronological commits with author, hash, and date.
3. **Code Churn Hotspots:**
   - Table sorting files by Total Churn, Additions, Deletions, and Commit Count.
   - Identifies volatile files with rapid growth or high deletion ratios.
4. **Logical Couplings (Co-Change Analysis):**
   - Displays file pairs that frequently change together across pull requests.
   - Shows Jaccard similarity coefficient and co-commit counts, uncovering hidden architectural couplings.

---

## 7. Change Impact Analysis & Test Selection

Before modifying code or merging a pull request, evaluate its ripple effects across the repository.

### Web Interface
1. Click the **ðŸŽ¯ Change Impact & Tests** tab.
2. Select or enter target files to be modified (e.g. `codemind/graph/builder.py`).
3. Set the traversal depth (1 to 3 hops).
4. Click **Analyze Change Impact**.
5. **Inspect Results:**
   - **Blast Radius Score:** Normalized risk score in $[0.0, 1.0]$.
   - **Directly Affected Files:** Upstream and downstream dependent modules.
   - **Recommended Regression Tests:** Automatically selected test files covering the affected dependency subgraph with confidence ratings.

### CLI
```bash
# Calculate blast radius for a file
codemind impact codemind/graph/builder.py --depth 2

# Select regression tests
codemind test-select codemind/graph/builder.py
```

---

## 8. Architecture Intelligence Dashboard

The dedicated **Architecture Intelligence & Risk Dashboard** provides an executive summary of software health.

### Dashboard Sections
1. **Repository Health Overview:**
   - Repository name, file count, line count, language breakdown, and Knowledge Graph scale.
2. **Architecture Conformance & ACI:**
   - Displays the **Architecture Conformance Index (ACI)** gauge (e.g. `94.1% Conformance`).
   - Conforming imports count vs. Rule violations count.
   - Layer structure overview (`PRESENTATION` $\to$ `APPLICATION` $\to$ `DOMAIN` $\to$ `INFRASTRUCTURE`).
   - Violations Table detailing: Rule Type (`LAYER_LEAK`, `FORBIDDEN_IMPORT`, `LAYER_SKIPPING`), Source Module, Target Module, Source File, and Exact Line Number.
3. **Dependency Cycle Detection:**
   - Evaluates Tarjan's Strongly Connected Components (SCC) on the package quotient graph.
   - Alerts whether circular dependencies exist (e.g. `billing <-> services`).
4. **Maintenance Hotspots & Risk Archetypes:**
   - Sortable table of modules ranked by **Hotspot Risk Score** ($[0.0, 1.0]$).
   - Classified **Debt Archetype** badges:
     - ðŸš¨ `CRITICAL_ACCUMULATOR`: High complexity + high churn + high centrality.
     - âš ï¸ `UNSTABLE_BOTTLENECK`: High centrality + high churn.
     - ðŸ“¦ `COMPLEX_LEGACY`: High complexity + low churn.
     - ðŸŒŠ `VOLATILE_SURFACE`: High churn + low complexity.
   - Metric columns: Cyclomatic Complexity, Network Centrality, Churn Score, Coupling Score, and Confidence.
   - **Evidence Coverage Pill:** Indicates whether all metrics were available (`100% Complete`) or if weights were dynamically renormalized.
5. **Benchmark Verification Summary:**
   - Displays verified Information Retrieval scores: **Precision@3 (0.5133)**, **Recall@3 (0.7117)**, **MRR (0.8333)**.
   - Honestly labels unmet targets and displays the exact mathematical unique-file ceiling ($0.5400$).
   - Shows latency benchmarks (Graph Traversal: 1.08 ms, AST Parse: 9.32 ms, Investigation: 0.28 ms).
