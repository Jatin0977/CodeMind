# CodeMind --- Agentic Codebase Intelligence & Software Evolution Platform

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Phases%201%E2%80%934%20Implemented-brightgreen.svg)

**CodeMind** is a codebase-intelligence project that helps developers
explore a repository, inspect Python code structure, search relevant
code and documentation, ask grounded questions with source citations,
and explore static relationships through a software knowledge graph.

> **Current scope:** Repository ingestion, Python AST analysis,
> AST-aware chunking and retrieval, grounded codebase Q&A, a web-based
> code explorer, and a static software knowledge graph. Git-evolution
> intelligence and more advanced agentic workflows are future work.

------------------------------------------------------------------------

## Table of Contents

-   [Implemented Capabilities](#implemented-capabilities)
-   [Architecture](#architecture)
-   [Technology Stack](#technology-stack)
-   [Getting Started](#getting-started)
-   [Run the Web Application](#run-the-web-application)
-   [CLI Reference](#cli-reference)
-   [Knowledge Graph API](#knowledge-graph-api)
-   [Running Tests](#running-tests)
-   [Project Structure](#project-structure)
-   [Current Limitations](#current-limitations)
-   [Roadmap](#roadmap)

------------------------------------------------------------------------

## Implemented Capabilities

### Phase 1 --- Repository Ingestion

-   Recursively loads a local code repository.
-   Filters common generated, dependency, virtual-environment, and
    version-control directories such as `.git/`, `node_modules/`,
    `venv/`, `__pycache__/`, and `dist/`.
-   Detects supported source and documentation files and skips binary
    files.
-   Supports repository loading from a local path and ZIP archive.
-   Exposes repository metadata for downstream analysis.

### Phase 2 --- Static Code Analysis with Python AST

-   Parses Python source using Python's standard-library `ast` module.
-   Extracts classes, functions, methods, imports, docstrings, calls,
    and source line information supported by the parser.
-   Handles syntax errors without stopping the entire ingestion process.
-   Provides CLI inspection of repository structure and symbols.

### Phase 3 --- Semantic Chunking, Retrieval and Grounded Q&A

-   Splits Python code into AST-aware chunks such as classes, methods,
    functions, and module headers.
-   Splits Markdown documentation into header-based chunks.
-   Stores metadata such as relative path, symbol name, chunk type, line
    range, parent symbol, and signature where available.
-   Provides a retrieval layer and in-memory vector store for ranking
    relevant chunks.
-   Includes an embedding-provider abstraction, with a deterministic
    mock embedding provider available for offline tests and
    demonstrations.
-   Uses a grounded RAG pipeline to construct answers from retrieved
    repository evidence.
-   Supports source citations and an insufficient-context response when
    evidence is missing or inadequate.
-   Includes a Gemini LLM provider for live use when configured with a
    valid API key, as well as a mock LLM provider for deterministic
    offline use.

**Important:** Mock providers are useful for testing and demonstrations,
but their behavior and retrieval quality should not be treated as
equivalent to a production semantic embedding or live LLM setup.

### Phase 4 --- Software Knowledge Graph

-   Builds a directed graph from ingested files and parsed Python
    symbols.
-   Represents file, class, function, and method nodes.
-   Models structural relationships such as:
    -   `CONTAINS`
    -   `CALLS`
    -   `IMPORTS`
    -   `INHERITS`
-   Resolves supported intra-repository imports and gracefully handles
    unresolved external symbols.
-   Supports queries for callers, callees, dependencies, dependents,
    dependency depth, cycles, and structural impact tracing.
-   Provides graph data and node details through the API.
-   Includes a web graph explorer with node search/filtering, node
    inspection, source navigation, and impact/cycle views.

The graph is based on static source analysis. It does not execute the
code or guarantee that every dynamic/runtime relationship is captured.

------------------------------------------------------------------------

## Architecture

``` text
                     Local Code Repository
                              |
                              v
                    Repository Ingestion
                              |
                              v
                    Python AST Analysis
                       /            \
                      v              v
             AST-Aware Chunking   Knowledge Graph
                      |              |
                      v              v
             Embedding / Search   Graph Queries
                      |
                      v
               Context Retrieval
                      |
                      v
               Grounded RAG Engine
                      |
                      v
          Answer + Source Citations (when available)
                      |
                      v
              FastAPI Web Application
          Explorer / Q&A / Graph Visualization
```

### Request flow for grounded Q&A

1.  Scan a repository to ingest files and build the available indexes.
2.  Submit a natural-language question.
3.  Retrieve relevant code/documentation chunks.
4.  Assemble evidence and send it to the configured LLM provider.
5.  Return the answer and citation information where available. If
    evidence is insufficient, the system should avoid fabricating
    repository-specific details.

------------------------------------------------------------------------

## Technology Stack

-   **Language:** Python
-   **Static analysis:** Python `ast`
-   **Backend/API:** FastAPI
-   **Knowledge graph:** NetworkX
-   **Web UI:** HTML, CSS, JavaScript
-   **Retrieval:** Project retrieval abstraction and in-memory vector
    store
-   **LLM integration:** Gemini provider and mock provider
-   **Testing:** pytest

------------------------------------------------------------------------

## Getting Started

### Prerequisites

-   Python 3.10 or newer
-   Git
-   Optional: a Gemini API key for live LLM responses

### Clone the repository

``` bash
git clone https://github.com/Jatin0977/CodeMind.git
cd CodeMind
```

### Install dependencies

``` bash
python -m pip install -r requirements.txt
```

If you use a virtual environment, activate it before installing
dependencies.

### Optional: configure Gemini

Set an environment variable if you want to use the live Gemini provider.
Use the variable expected by the current provider configuration
(commonly `GEMINI_API_KEY`).

PowerShell example:

``` powershell
$env:GEMINI_API_KEY = "your-api-key"
```

Do not commit API keys or place them directly in source code. The mock
provider can be used for offline testing without a live API key.

------------------------------------------------------------------------

## Run the Web Application

From the repository root:

``` bash
python -m codemind.cli serve --host 127.0.0.1 --port 8000
```

Open:

``` text
http://127.0.0.1:8000
```

Use the web interface to scan a repository, browse files and symbols,
ask grounded questions, inspect citations, and explore the Software
Knowledge Graph.

> Run a repository scan in the UI before testing repository-specific Q&A
> or graph features.

------------------------------------------------------------------------

## CLI Reference

Run commands from the repository root. Replace `.` with the path to the
repository you want to analyze.

### Inspect repository and symbols

``` bash
python -m codemind.cli inspect .
python -m codemind.cli inspect . --detail
python -m codemind.cli inspect . --json
```

### Chunk a repository

``` bash
python -m codemind.cli chunk .
python -m codemind.cli chunk . --json
```

### Search code and documentation

``` bash
python -m codemind.cli search . "How does file filtering ignore directories?" --top-k 3
python -m codemind.cli search . "Where are classes and functions extracted from Python AST?"
```

### Ask grounded questions

``` bash
# Use the configured LLM provider
python -m codemind.cli ask . "How does the file filter ignore directories and binary files?"

# Use the mock provider for an offline demonstration
python -m codemind.cli ask . "How does the file filter ignore directories?" --mock

# Return structured JSON
python -m codemind.cli ask . "Explain the Python AST parser" --mock --json
```

### Explore the knowledge graph

``` bash
# Build and summarize graph information for the repository
python -m codemind.cli graph .

# Trace impact from a file
python -m codemind.cli graph . --impact file:codemind/ingestion/models.py

# Detect cycles
python -m codemind.cli graph . --cycles

# Return graph output as JSON
python -m codemind.cli graph . --json
```

The graph CLI supports static structural analysis. Impact results
indicate reachable relationships in the analyzed graph; they are not
runtime execution predictions or guaranteed risk scores.

------------------------------------------------------------------------

## Knowledge Graph API

The web application exposes graph endpoints:

  -------------------------------------------------------------------------------------
  Endpoint                                          Purpose
  ------------------------------------------------- -----------------------------------
  `GET /api/graph`                                  Retrieve graph nodes and edges,
                                                    with supported query/type/size
                                                    filters

  `GET /api/graph/node?node_id=...`                 Retrieve details for a graph node

  `GET /api/graph/impact?node_id=...&max_depth=3`   Trace structural impact from a node

  `GET /api/graph/cycles`                           Retrieve detected graph cycles
  -------------------------------------------------------------------------------------

The exact accepted query parameters and response fields are defined by
the API implementation. Use the running application's API responses as
the source of truth if these details change.

------------------------------------------------------------------------

## Running Tests

Run the full automated test suite with pytest:

``` bash
python -m pytest tests -v
```

The latest recorded local run for the current implementation reported:

``` text
58 passed, 1 warning in 3.15s
```

The warning concerned the Starlette `TestClient` integration with
`httpx`; it did not cause a test failure. Test results can change after
code or dependency updates, so rerun the command in your own environment
to verify the current checkout.

------------------------------------------------------------------------

## Project Structure

``` text
CodeMind/
├── codemind/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── file_filter.py
│   │   └── repo_loader.py
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── base_parser.py
│   │   ├── python_parser.py
│   │   └── parser_factory.py
│   ├── chunking/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── base_chunker.py
│   │   ├── ast_chunker.py
│   │   └── doc_chunker.py
│   ├── embeddings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── sentence_transformer_provider.py
│   │   ├── mock_provider.py
│   │   └── factory.py
│   ├── vector_store/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── memory_store.py
│   │   ├── chroma_store.py
│   │   └── factory.py
│   ├── retrieval/
│   │   ├── __init__.py
│   │   └── retriever.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── prompt_templates.py
│   │   ├── engine.py
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── gemini_provider.py
│   │       ├── mock_provider.py
│   │       └── factory.py
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── builder.py
│   │   └── query.py
│   └── web/
│       ├── __init__.py
│       ├── app.py
│       └── static/
│           ├── index.html
│           ├── style.css
│           └── app.js
├── tests/
│   ├── test_ingestion.py
│   ├── test_python_parser.py
│   ├── test_chunking.py
│   ├── test_retrieval.py
│   ├── test_rag.py
│   ├── test_graph.py
│   └── test_web.py
├── requirements.txt
├── README.md
└── .gitignore
```

This is a high-level view of the main project files; minor files may be
omitted.

------------------------------------------------------------------------

## Current Limitations

-   Static AST analysis cannot capture every dynamic import, reflection
    pattern, runtime injection, or runtime-only call relationship.
-   Graph impact tracing reports structural reachability based on
    modeled relationships; it is not a predictive risk score.
-   Mock embeddings and the mock LLM are intended for deterministic
    testing/offline demonstrations and do not represent production model
    quality.
-   Live Gemini Q&A requires valid credentials and working network
    access.
-   The current graph and retrieval behavior should be validated on the
    target repository; a passing test suite does not guarantee every
    possible query will return the correct answer.
-   Git-history intelligence and advanced multi-agent investigation are
    not yet part of the implemented scope described here.

------------------------------------------------------------------------

## Roadmap

-   [x] **Phase 1:** Repository ingestion
-   [x] **Phase 2:** Static code analysis and Python AST parsing
-   [x] **Phase 3:** AST-aware chunking, retrieval, and grounded
    codebase Q&A
-   [x] **Phase 4:** Software Knowledge Graph and graph exploration UI
-   [ ] **Future:** Git evolution intelligence and commit/diff analysis
-   [ ] **Future:** Deeper change-impact analysis and testing
    intelligence
-   [ ] **Future:** Multi-agent orchestration and autonomous code
    investigation

The roadmap describes the current project direction, not a claim that
future items are implemented.

------------------------------------------------------------------------

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE)
for details.
