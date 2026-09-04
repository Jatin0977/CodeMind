# CodeMind — Agentic Codebase Intelligence & Software Evolution Platform

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: Milestone 4 Completed](https://img.shields.io/badge/Module%201-Milestone%204%20Completed-brightgreen.svg)]()

> **CodeMind** is an AI-powered software engineering intelligence system that analyzes source code, documentation, and Git history to help developers investigate, understand, and evolve software repositories.

---

## 🏛️ Platform Architecture & Roadmap

```
                                  Code Repository
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌────────────────┐              ┌────────────────┐              ┌────────────────┐
│ Static Code    │              │ Semantic Vector│              │ Git Evolution  │
│ Analysis       │              │ Indexing       │              │ Intelligence   │
│ (AST & Graphs) │              │ (Embeddings)   │              │ (Commits/Diff) │
└───────┬────────┘              └───────┬────────┘              └───────┬────────┘
        │                               │                               │
        └───────────────────────┬───────┴───────────────────────────────┘
                                ▼
                   Unified Code Intelligence Engine
                                │
                                ▼
                     Agent Orchestrator Layer
                   (Specialized RAG & Analysis)
                                │
                                ▼
                    Evidence Synthesizer
                                │
                                ▼
               Grounded Answers with Exact Citations
                                │
                                ▼
           Interactive Web UI & Visual Code Explorer
```

---

## 🎯 Implemented Module: Module 1 (Ingestion, Semantic Analysis & Visual UI)

### Milestone 1: Repository Ingestion + Python AST Code Parsing
- **Recursive Ingestion**: Traverses repositories, automatically ignoring `.git/`, `node_modules/`, `venv/`, `__pycache__/`, `dist/`, and binary files.
- **Python AST Parser**: Extracts classes, methods, synchronous & asynchronous functions, function calls, imports, docstrings, and exact start/end line numbers.
- **Fault-Tolerant Parsing**: Syntax errors are captured gracefully without crashing ingestion.
- **CLI Inspector**: `python -m codemind.cli inspect <path>`

### Milestone 2: AST-Aware Code Chunking + Semantic Search
- **AST-Aware Code Chunker (`ASTCodeChunker`)**: Splits Python code at logical AST boundaries (classes, methods, top-level functions, module headers) while preserving signatures.
- **Documentation Chunker (`DocChunker`)**: Splits Markdown and documentation files by header hierarchy (`#`, `##`, `###`).
- **Rich Chunk Metadata**: `chunk_id`, `relative_path`, `symbol_name`, `chunk_type`, `start_line`, `end_line`, `parent_symbol`, `signature`.
- **Modular Embedding Layer (`codemind/embeddings/`)**: Local dense semantic embedding model (`sentence-transformers/all-MiniLM-L6-v2`).
- **Vector Store Layer (`codemind/vector_store/`)**: `InMemoryVectorStore` with cosine similarity ranking and `ChromaVectorStore` adapter.
- **Semantic Code Retriever (`codemind/retrieval/`)**: Top-$k$ natural language semantic code retrieval with line spans and similarity scores.

### Milestone 3: Basic Grounded RAG with Precise Source Citations
- **Grounded Prompt Engineering (`codemind/rag/prompt_templates.py`)**: Strict code-QA system prompt instructing the LLM to answer only from retrieved evidence and format citations as `[relative/path.py:start_line-end_line]`.
- **Anti-Hallucination & Insufficient Context**: If retrieved context is missing or irrelevant, the system explicitly reports insufficient repository context rather than fabricating an answer.
- **LLM Providers (`codemind/rag/providers/`)**:
  - `GeminiLLMProvider`: Real Google Gemini API provider (`gemini-2.5-flash` / `gemini-1.5-flash`).
  - `MockLLMProvider`: Fast deterministic offline provider for unit tests and demonstrations without API keys.
- **RAG Engine Orchestrator (`codemind/rag/engine.py`)**: Integrates retrieval, evidence context serialization, model inference, citation parsing, and latency metrics.
- **CLI Q&A Command**: `python -m codemind.cli ask <path> "<question>"`

### Milestone 4: Interactive Web UI & Visual Code Explorer
- **Lightweight Single-Page Dashboard (`codemind/web/`)**: Built using FastAPI backend with glassmorphic dark-theme UI (zero Node.js build step).
- **Codebase Indexing & Summary**: Real-time metrics on scanned files, classes, functions, methods, imports, and chunks.
- **Integrated File Tree & Search**: Interactive file browser with language chips and line counts.
- **AST Symbol Inspector**: Deep symbol tree breakdown (classes, methods, top-level functions, imports) for Python files.
- **Interactive Grounded Q&A**: Ask natural language questions with real-time evidence retrieval, streaming answer cards, confidence banners, and latency measurements.
- **Clickable Citations & Code Highlighting**: Clicking any source citation card or AST symbol automatically navigates to the file and highlights the exact cited line range (`start_line` to `end_line`).
- **CLI Web Server**: `python -m codemind.cli serve --port 8000`

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher
- Git
- (Optional) `GEMINI_API_KEY` or `GOOGLE_API_KEY` for live Gemini RAG

### 2. Installation
```bash
git clone https://github.com/your-username/CodeMind.git
cd CodeMind
python -m pip install -r requirements.txt
```

---

## 💻 CLI & Web Usage Examples

### 1. Launch Interactive Web Dashboard
```bash
python -m codemind.cli serve --host 127.0.0.1 --port 8000
```
Open your browser at `http://127.0.0.1:8000` to interactively scan repositories, inspect symbols, explore code, and ask grounded questions.

### 2. Inspect Codebase Structure & AST Symbols
```bash
python -m codemind.cli inspect .
python -m codemind.cli inspect . --detail
python -m codemind.cli inspect . --json
```

### 3. Chunk Codebase into AST Semantic Units
```bash
python -m codemind.cli chunk .
python -m codemind.cli chunk . --json
```

### 4. Semantic Code Search
```bash
python -m codemind.cli search . "How does file filtering ignore directories?" --top-k 3
python -m codemind.cli search . "Where are classes and functions extracted from Python AST?"
```

### 5. Grounded Codebase Q&A (RAG)
```bash
# Using Google Gemini API (reads GEMINI_API_KEY environment variable)
python -m codemind.cli ask . "How does the file filter ignore directories and binary files?"

# Offline mode (using deterministic Mock LLM provider without API keys)
python -m codemind.cli ask . "How does the file filter ignore directories?" --mock

# Output structured JSON
python -m codemind.cli ask . "Explain the Python AST parser" --mock --json
```

---

## 🧪 Running Automated Tests

Run the complete test suite (all 39 tests across Milestones 1, 2, 3, and 4):

```bash
python -m unittest discover -s tests -v
```

---

## 📂 Project Structure

```
CodeMind/
├── codemind/
│   ├── __init__.py               # Package metadata & version 0.1.0
│   ├── config.py                 # Ingestion & parsing configuration
│   ├── cli.py                    # CLI tool (inspect, chunk, search, ask, serve)
│   ├── ingestion/
│   │   ├── __init__.py           # Ingestion layer exports
│   │   ├── models.py             # SourceFile, IngestionSummary, IngestedRepository
│   │   ├── file_filter.py        # Ignore filter rules & binary detection
│   │   └── repo_loader.py        # Recursive codebase loader with directory pruning
│   ├── parsing/
│   │   ├── __init__.py           # Parsing layer exports
│   │   ├── base_parser.py        # BaseParser, Symbol, ImportStatement, ParsedFile
│   │   ├── python_parser.py      # Standard library AST parser
│   │   └── parser_factory.py     # Extensible parser registry
│   ├── chunking/
│   │   ├── __init__.py           # Chunking layer exports
│   │   ├── models.py             # CodeChunk data model
│   │   ├── base_chunker.py       # BaseChunker abstract interface
│   │   ├── ast_chunker.py        # AST-aware Python code chunker
│   │   └── doc_chunker.py        # Markdown documentation section chunker
│   ├── embeddings/
│   │   ├── __init__.py           # Embedding exports
│   │   ├── base.py               # BaseEmbeddingProvider interface
│   │   ├── sentence_transformer_provider.py  # Primary SentenceTransformers provider
│   │   ├── mock_provider.py      # Fast deterministic provider for testing
│   │   └── factory.py            # Embedding provider factory
│   ├── vector_store/
│   │   ├── __init__.py           # Vector store exports
│   │   ├── base.py               # BaseVectorStore and SearchResult
│   │   ├── memory_store.py       # In-memory cosine vector store
│   │   ├── chroma_store.py       # ChromaDB vector store adapter
│   │   └── factory.py            # Vector store factory
│   ├── retrieval/
│   │   ├── __init__.py           # Retrieval exports
│   │   └── retriever.py          # SemanticRetriever indexing & search orchestrator
│   ├── rag/
│   │   ├── __init__.py           # RAG exports
│   │   ├── models.py             # RAGResponse dataclass
│   │   ├── prompt_templates.py   # Grounded prompt templates & citation extractor
│   │   ├── engine.py             # RAGEngine orchestrator
│   │   └── providers/
│   │       ├── __init__.py       # Provider exports
│   │       ├── base.py           # BaseLLMProvider interface
│   │       ├── gemini_provider.py# Google Gemini API provider
│   │       ├── mock_provider.py  # Deterministic mock LLM provider
│   │       └── factory.py        # LLM provider factory
│   └── web/
│       ├── __init__.py           # Web package exports
│       ├── app.py                # FastAPI REST API endpoints
│       └── static/               # Interactive single-page web UI
│           ├── index.html        # HTML5 layout (Explorer, Code Viewer, RAG Q&A)
│           ├── style.css         # Glassmorphism dark theme styling
│           └── app.js            # JavaScript UI controller & citation jumper
├── tests/
│   ├── test_ingestion.py         # Ingestion & file filtering tests (9 tests)
│   ├── test_python_parser.py     # AST parsing & error resilience tests (7 tests)
│   ├── test_chunking.py          # AST code & doc chunking tests (5 tests)
│   ├── test_retrieval.py         # Embeddings & vector retrieval tests (3 tests)
│   ├── test_rag.py               # Grounded RAG & citation tests (6 tests)
│   └── test_web.py               # FastAPI web endpoints & Explorer tests (9 tests)
├── requirements.txt              # Project dependencies
├── README.md                     # Documentation & usage guide
└── .gitignore                    # Git ignore configurations
```

---

## 🗺️ Roadmap & Milestones

- [x] **Milestone 1**: Repository Ingestion + Python AST Code Parsing + CLI Inspector
- [x] **Milestone 2**: AST-Aware Code Chunking + Semantic Search & Retrieval
- [x] **Milestone 3**: Basic Grounded RAG with Precise Source Code Citations
- [x] **Milestone 4**: Interactive Demonstration Web UI & Visual Code Explorer
- [ ] **Milestone 5**: Code Graph & Knowledge Graph Construction *(Future Evaluation)*
- [ ] **Milestone 6**: Git Evolution Intelligence & Change Impact Analysis *(Future Evaluation)*
- [ ] **Milestone 7**: Multi-Agent Orchestrator & Autonomous Code Review *(Future Evaluation)*
