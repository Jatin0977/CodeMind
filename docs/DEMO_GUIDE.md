# CodeMind â€” Live Demonstration & Presentation Script

**Project Title:** CodeMind: Grounded Repository Intelligence & Agentic Codebase Investigation
**Duration:** 10â€“15 Minutes
**Target Audience:** Final-Year B.Tech CSE Project Evaluation Committee & External Viva Examiners
**Prerequisites:** Python 3.10+, Git repository clone, Web browser

---

## Demonstration Overview & Timing

| Segment | Topic / Capability | Duration | Mode |
|---|---|---|---|
| **Phase 1** | System Ingestion & Multi-Language AST Parsing | 2.0 min | CLI & Web |
| **Phase 2** | Grounded Hybrid RAG & Anti-Hallucination Citations | 2.5 min | Web Explorer |
| **Phase 3** | Software Knowledge Graph & Topological Querying | 2.5 min | Interactive Graph |
| **Phase 4** | Agentic Multi-Step Investigation Engine | 2.5 min | Investigation Tab |
| **Phase 5** | Git Temporal Intelligence & Co-Change Coupling | 2.0 min | Evolution Tab |
| **Phase 6** | Change Impact Blast Radius & Regression Test Selection | 2.0 min | Impact Tab |
| **Phase 7** | Architecture Conformance, Tarjan Cycles & Hotspots | 2.0 min | Architecture Dashboard |
| **Phase 8** | Phase 10 Quantitative Benchmarks & Summary | 1.0 min | Dashboard & Q&A |

---

## Preparation Before Demonstration

1. Open a terminal in the project directory:
   ```bash
   cd C:\Users\user\Desktop\Codemind\CodeMind
   ```
2. Verify virtual environment or Python executable:
   ```bash
   python -m codemind.cli --help
   ```
3. Set deterministic offline mode or ensure Gemini API key is configured in `.env`:
   ```bash
   # Offline / local deterministic mode
   $env:CODEMIND_EMBEDDING_PROVIDER="mock"
   # Or with Gemini API key
   # $env:GEMINI_API_KEY="your-gemini-api-key"
   ```
4. Start the CodeMind web server:
   ```bash
   python -m uvicorn codemind.web.app:app --host 127.0.0.1 --port 8000 --workers 1
   ```
5. Open your web browser to `http://localhost:8000`.

---

## Scripted Walkthrough

### Part 1: System Overview & Fast Ingestion (2 Minutes)

#### A. Examiner Talking Point
> *"Examiners, standard developer tools like grep, ctags, or naive RAG pipelines suffer from major shortcomings: text search lacks semantic context, and naive RAG chops code into arbitrary text chunks, breaking syntax, slicing classes in half, and hallucinating answers. CodeMind solves this by combining AST syntax parsing, dense vector embeddings, a topological knowledge graph, and Git temporal mining into a unified codebase intelligence platform."*

#### B. Action Steps
1. **CLI Demonstration:**
   Run CLI repository inspection in your terminal:
   ```bash
   python -m codemind.cli inspect . --detail
   ```
   - Highlight the total lines of code, language breakdown, classes, functions, and import count.
2. **Web Demonstration:**
   - In the top header bar of `http://localhost:8000`, enter `.` (or path to repository) and click **"âš¡ Scan & Analyze Codebase"**.
   - Watch the animated metrics update: Total Files, Total Lines, AST Classes, Methods, Semantic Chunks, and Graph Nodes.
   - Point out the status pill in the top right: `Mock LLM Mode` (or `Gemini API Ready`), `64-dim embeddings`, and `Graph: Active`.

---

### Part 2: Grounded Hybrid RAG & Verification (2.5 Minutes)

#### A. Examiner Talking Point
> *"Unlike standard LLM code assistants that often hallucinate non-existent files and functions, CodeMind utilizes a multi-stage Grounded Retrieval-Augmented Generation pipeline. It indexes code using AST-aware semantic chunking and enforces strict citation verification. If a cited symbol or file does not exist in the repository, the hallucination is caught and suppressed."*

#### B. Action Steps
1. Navigate to the **"ðŸ’¬ Grounded Code Q&A"** tab.
2. Ask a structural question:
   ```text
   How does the semantic chunker split code while preserving syntax boundaries?
   ```
3. Highlight:
   - **Retrieved Evidence Cards:** Expand the retrieved chunk cards. Note the exact file path, start line, end line, and AST parent scope (`codemind/chunking/semantic_chunker.py`).
   - **Grounded Answer:** The LLM cites specific code lines.
   - **Anti-Hallucination Citation Verification:** Point out the citation validity pill `âœ“ 100% Valid Citations (0 Fabricated)` displayed below the response.

---

### Part 3: Software Knowledge Graph & Topology (2.5 Minutes)

#### A. Examiner Talking Point
> *"Vector search alone cannot understand code relationships such as call graphs, inheritance hierarchies, or import dependencies. CodeMind constructs a multi-layer in-memory NetworkX Software Knowledge Graph that connects files, classes, methods, functions, and modules."*

#### B. Action Steps
1. Click on the **"ðŸ•¸ï¸ Knowledge Graph"** tab.
2. Click **"Render Full Graph"** or filter by node type (`class`, `function`).
3. Click on a central node (e.g. `SemanticChunker` or `KnowledgeGraph`):
   - Notice the node details panel showing incoming callers, outgoing callees, dependencies, and depth metrics.
4. Demonstrate structural reachability:
   - In the target reachability box, enter `class:codemind.chunking.semantic_chunker:SemanticChunker` and click **"Trace Reachability"**.
   - Show the highlighted transitive dependency sub-tree.

---

### Part 4: Agentic Multi-Step Investigation Engine (2.5 Minutes)

#### A. Examiner Talking Point
> *"Complex developer questions cannot be answered in a single retrieval step. CodeMind features an autonomous Agentic Investigation Subsystem modeled on an iterative ReAct pattern: Planner â†’ Evidence Collector â†’ State Evaluator â†’ Synthesizer."*

#### B. Action Steps
1. Navigate to the **"ðŸ•µï¸ Agentic Investigation"** tab.
2. Enter the prompt:
   ```text
   Trace the end-to-end data flow from AST parsing to knowledge graph construction.
   ```
3. Click **"Investigate Codebase"**.
4. Walk the committee through the live execution trace:
   - **Iteration 1 (Plan):** Agent determines starting symbols (`BaseParser`, `PythonParser`).
   - **Iteration 2 (Collect):** Tool execution calls `inspect_symbol` and `trace_dependencies`.
   - **Iteration 3 (Evaluate):** Agent evaluates if evidence threshold is met.
   - **Iteration 4 (Synthesize):** Agent produces a structured technical report complete with sequence flow and verified file references.

---

### Part 5: Git Temporal Intelligence & Historical Co-Change (2 Minutes)

#### A. Examiner Talking Point
> *"Static code analysis only shows how code is structured today; it misses how code evolves over time. CodeMind mines the local Git commit history without relying on external GitHub API rate limits to compute code churn hotspots and logical co-change coupling."*

#### B. Action Steps
1. Switch to the **"â³ Evolution & Git Intelligence"** tab.
2. Click **"Mine Repository Git History"**.
3. Point out:
   - **Code Churn Hotspots:** Modules with high churn (commit frequency + lines added/deleted) represent maintenance risk.
   - **Logical Co-Change Coupling:** Table showing pairs of files that frequently commit together despite having no static import edge. Explain that this reveals hidden architectural coupling!

---

### Part 6: Change Impact Analysis & Regression Test Selection (2 Minutes)

#### A. Examiner Talking Point
> *"Before refactoring or pushing a commit, developers need to know: what breaks if I change this function? And which regression tests do I need to run? CodeMind's Change Impact subsystem performs reverse transitive BFS traversal across the graph combined with commit co-change weights to calculate blast radius and recommend prioritized regression tests."*

#### B. Action Steps
1. Switch to the **"ðŸŽ¯ Change Impact & Tests"** tab.
2. In Target Symbol or File, enter:
   ```text
   codemind/parsing/python_parser.py
   ```
3. Click **"Analyze Impact"**.
4. Highlight:
   - **Composite Risk Badge:** `HIGH` or `CRITICAL` with numerical composite risk score.
   - **Blast Radius Tree:** Nodes impacted at Depth 1 (direct dependents), Depth 2, and Depth 3.
   - **Prioritized Regression Tests:** Tier 0 (direct target test), Tier 1 (direct caller tests), and Tier 2 (transitive tests).

---

### Part 7: Architecture Conformance, Tarjan Cycles & Hotspots (2 Minutes)

#### A. Examiner Talking Point
> *"In Milestone 9 and 10, we implemented full Architecture Intelligence. CodeMind defines architectural layers (Presentation, Application, Domain, Infrastructure), measures the Architecture Conformance Index (ACI), detects cyclic package dependencies using Tarjan's Strongly Connected Components algorithm, and classifies maintenance debt archetypes."*

#### B. Action Steps
1. Switch to the newly built **"ðŸ›ï¸ Architecture & Risk Dashboard"** tab.
2. Walk the examiners through the 6 panels:
   - **Top Cards:** Architecture Conformance Index (ACI), Package Cycles counter (0 cycles = Acyclic ADP satisfied), Repository Risk Score, and Evidence Coverage (100%).
   - **Layer Hierarchy:** Explain the 4-tier layer model. Check **"Strict Layering"** and show the instantaneous re-computation of rule violations.
   - **Package Cycles Container:** Point out the green banner confirming zero circular package dependencies.
   - **Maintenance Hotspots Table:** Sort by **Hotspot Risk** or filter by Archetype (`Critical Accumulator`, `Unstable Bottleneck`). Show that raw AST complexity, graph centrality, churn, and coupling combine non-linearly to classify debt.
   - **Investigation Trigger Chips:** Click **"Explain Hotspots"** to demonstrate cross-tab navigation back to the Agentic engine!

---

### Part 8: Quantitative Evaluation & Benchmark Results (1 Minute)

#### A. Examiner Talking Point
> *"For our Phase 10 engineering closure, we conducted rigorous benchmarking over 50 golden queries and 3 repository scale tiers (15, 58, and 265 files). We established honest academic integrity: Mean Reciprocal Rank (MRR) achieved 0.8333 (exceeding our 0.75 target), while Precision@3 achieved 0.5133 against a mathematical single-target dataset ceiling of 0.5400, which we transparently document as NOT MET rather than manipulating ground truth."*

#### B. Action Steps
1. Scroll to **Section F** of the Architecture Dashboard:
   - Highlight the 50 Golden Queries summary.
   - Point out MRR (0.8333 MET) and Query Latency (17.75 ms vs 18.06 ms baseline).
   - Point out honest NOT MET status badges for Precision@3 and Recall@3.
2. Conclude the demonstration and invite questions from the panel.

---

## Contingency & Troubleshooting Guide

| Issue | Quick Fix |
|---|---|
| **Port 8000 already in use** | Run on alternate port: `python -m uvicorn codemind.web.app:app --port 8080 --workers 1` |
| **No repository scanned message** | Ensure you entered `.` in the top repo path input and clicked "Scan & Analyze Codebase". |
| **No Gemini API Key available** | Ensure `CODEMIND_EMBEDDING_PROVIDER="mock"`. All AST parsing, graphs, architecture, and tests work 100% offline without any API keys. |
| **Browser tab styling looks unrefreshed** | Hard refresh using `Ctrl + F5` to clear cached JavaScript and CSS. |
