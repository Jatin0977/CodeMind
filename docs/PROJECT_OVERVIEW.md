# CodeMind â€” Project Overview

## 1. Executive Summary

**CodeMind** is an enterprise-grade codebase intelligence, static architecture analysis, and agentic investigation platform designed for repository-level software comprehension. It integrates concrete Python Abstract Syntax Tree (AST) parsing, topological Software Knowledge Graphs, Git temporal intelligence, multi-signal change impact analysis, and hybrid lexical-semantic retrieval into a cohesive, grounded investigation engine.

Modern software repositories suffer from architectural erosion, hidden package cycles, unmanaged maintenance hotspots, and opaque change blast radiuses. Generic Large Language Models (LLMs) applied naively to codebases struggle with hallucinated citations, lack structural grounding, and cannot navigate multi-hop call graphs or historical co-change patterns. CodeMind bridges this gap by combining deterministic graph theory, static analysis, and grounded retrieval-augmented generation (RAG).

```
                      +---------------------------------------+
                      |         Developer Interaction         |
                      |     (Web Dashboard / CLI Engine)      |
                      +-------------------+-------------------+
                                          |
                      +-------------------v-------------------+
                      |      Agentic Investigation Engine     |
                      |  Intent -> Plan -> Collect -> Synthesize  |
                      +-------------------+-------------------+
                                          |
        +---------------------------------+---------------------------------+
        |                                 |                                 |
+-------v-------+                 +-------v-------+                 +-------v-------+
|  Static AST   |                 | Knowledge     |                 | Git Temporal  |
|  & Hierarchy  |                 | Graph (Nx)    |                 | Mining        |
+-------+-------+                 +-------+-------+                 +-------+-------+
        |                                 |                                 |
        +---------------------------------+---------------------------------+
                                          |
                      +-------------------v-------------------+
                      |   Hybrid Graph-Aware Retrieval Engine |
                      |    (BM25 Lexical + Dense Embeddings)  |
                      +---------------------------------------+
```

---

## 2. The Problem CodeMind Solves

### The Breakdown of Naive Code Search and Generic LLMs
1. **Context Window Saturation:** Large software repositories (50,000+ LOC) exceed LLM context windows. Naive chunking (e.g. fixed 500-token chunks) slices functions in half, breaking semantic AST boundaries.
2. **Topological Blindness:** Pure vector search retrieves textually similar tokens but cannot determine whether `Function A` calls `Function B`, or whether `Module X` violates architectural layering by importing `Module Y`.
3. **Hallucinated Citations:** Standard RAG pipelines frequently output fabricated line numbers or cite files that do not exist.
4. **Ignorance of Code Evolution:** Software risk is dynamic. A complex module that has never changed poses low operational risk; a moderately complex module modified in 50 consecutive pull requests by 10 different developers is a high-risk churn hotspot.
5. **Architectural Drift:** Over time, deadline-driven development introduces circular dependencies, upward layer leaks, and God classes that violate clean architecture.

---

## 3. Core Subsystems & Capabilities

| Subsystem | Core Module | Primary Capability |
| :--- | :--- | :--- |
| **Repository Ingestion** | `codemind.ingestion` | Multi-source intake (local, ZIP, Git clone), noise filtering, metadata extraction. |
| **Static Code Analysis** | `codemind.parsing` | Standard-library Python AST parsing, symbol extraction, syntax error resilience. |
| **Semantic Chunking** | `codemind.chunks` | Class- and function-level AST chunking, docstring extraction, boundary preservation. |
| **Knowledge Graph** | `codemind.graph` | Multi-relational NetworkX directed graph (`CONTAINS`, `CALLS`, `IMPORTS`, `INHERITS`). |
| **Hybrid Retrieval** | `codemind.retrieval` | Reciprocal rank fusion of BM25 lexical search and dense embeddings with graph expansion. |
| **Agentic Investigation** | `codemind.investigation` | 5-stage planner, tool registry, evidence collection, and grounded synthesis. |
| **Git Temporal Intelligence** | `codemind.git` | Commit history mining, additions/deletions churn metrics, Jaccard logical coupling. |
| **Change Impact Analysis** | `codemind.impact` | Blast-radius scoring (depth, fan-out, churn, coupling) and test selection. |
| **Architecture Intelligence** | `codemind.architecture` | Module discovery, layer conformance (ACI), Tarjan SCC cycle detection, hotspot risk archetypes. |
| **Web & CLI Interfaces** | `codemind.web`, `codemind.cli` | Responsive interactive dashboard and full-featured command-line interface. |

---

## 4. Key Differentiators

1. **Deterministic Grounding:** Every insight and answer produced by CodeMind is backed by concrete code citations verified against line boundaries (`start_line` to `end_line`) with 0.00% hallucinated citations.
2. **Dual-Lens Intelligence:** Synthesizes spatial structure (AST symbols and call graphs) with temporal history (Git churn and co-change couplings).
3. **Offline Reliability:** Fully capable of running in 100% offline environments using local BM25 indexing, mock embeddings, and deterministic template synthesis when external LLMs or internet connectivity are unavailable.
4. **Architectural Conformance Index (ACI):** Quantifies architectural compliance into a mathematical index:
   $$\text{ACI} = 1.0 - \frac{\text{Total Violations}}{\text{Total Module Imports}}$$
5. **Formal Risk Archetypes:** Classifies maintainability debt into distinct actionable archetypes: `CRITICAL_ACCUMULATOR`, `UNSTABLE_BOTTLENECK`, `COMPLEX_LEGACY`, and `VOLATILE_SURFACE`.

---

## 5. Technology Stack Summary

- **Backend Runtime:** Python 3.11 / 3.12 (Standard Library `ast`, `asyncio`, `pathlib`)
- **API Framework:** FastAPI 0.115+, Uvicorn (Single-worker process model)
- **Graph Engine:** NetworkX 3.4+ (Directed Multi-Graph representation)
- **Version Control Mining:** GitPython 3.1+ (Subprocess stream decoding)
- **Frontend Stack:** Vanilla JavaScript (ES6+), Modern HTML5, Responsive CSS3 with CSS Custom Properties, DOMPurify for strict XSS defense.
- **Testing & Packaging:** Pytest, Pytest-Cov, Flake8, PEP 517/621 Setuptools build system.
