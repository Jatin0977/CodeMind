# CodeMind â€” REST API Reference

CodeMind exposes a RESTful API powered by **FastAPI**. All JSON endpoints use strict schema validation via Pydantic models.

- **Base URL:** `http://localhost:8000`
- **Interactive Documentation:** `http://localhost:8000/docs` (Swagger UI)
- **Alternative Documentation:** `http://localhost:8000/redoc` (ReDoc)
- **Deployment Requirement:** Single-worker process execution (`--workers 1`) to preserve in-memory graph and index consistency.

---

## 1. System & Health Endpoints

### `GET /api/health`
Checks backend application health and initialized subsystem states.

**Response `200 OK`:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-11-23T01:50:00Z",
  "active_repository": "CodeMind",
  "total_files": 45,
  "graph_nodes": 372,
  "graph_edges": 343,
  "git_active": true,
  "embedding_provider": "mock",
  "llm_provider": "mock",
  "concurrency_lock": "active"
}
```

---

## 2. Ingestion & Static Analysis Endpoints

### `POST /api/scan`
Triggers full repository ingestion, AST parsing, Knowledge Graph building, and hybrid vector indexing.

**Request Body:**
```json
{
  "repo_path": "."
}
```
*Note:* `repo_path` accepts a local folder path, path to a `.zip` file, or a Git clone URL.

**Response `200 OK`:**
```json
{
  "status": "success",
  "repository": "CodeMind",
  "repo_path": "C:\\Users\\user\\Desktop\\Codemind\\CodeMind",
  "total_files": 45,
  "total_lines": 5420,
  "languages": { "Python": 45 },
  "static_metrics": {
    "classes": 32,
    "functions": 48,
    "methods": 112,
    "imports": 184,
    "docstrings": 192,
    "syntax_errors": 0
  },
  "indexed_chunks": 210,
  "graph_nodes": 372,
  "graph_edges": 343,
  "git_active": true
}
```

**Errors:**
- `400 Bad Request`: Empty or invalid repository path.
- `404 Not Found`: Repository path does not exist on disk.

---

### `GET /api/file`
Retrieves source file contents and line numbers with path traversal protection.

**Query Parameters:**
- `path` (string, required): Relative path to file (e.g. `codemind/web/app.py`).

**Response `200 OK`:**
```json
{
  "file_path": "codemind/web/app.py",
  "line_count": 850,
  "content": "\"\"\"FastAPI Application Entrypoint...\"\"\"\n..."
}
```

**Errors:**
- `400 Bad Request`: Path traversal attempt (e.g. `../../etc/passwd`).
- `404 Not Found`: File does not exist within the scanned repository.

---

### `GET /api/symbols`
Returns AST symbol metadata for a specific file or the entire repository.

**Query Parameters:**
- `file_path` (string, optional): Specific file path to filter symbols.

**Response `200 OK`:**
```json
{
  "file_path": "codemind/web/app.py",
  "classes": [
    {
      "name": "CodebaseState",
      "start_line": 65,
      "end_line": 210,
      "docstring": "Holds thread-safe in-memory state...",
      "methods": ["scan_and_analyze", "_scan_and_analyze_impl"],
      "bases": []
    }
  ],
  "functions": [
    {
      "name": "create_app",
      "start_line": 215,
      "end_line": 845,
      "docstring": "FastAPI application factory...",
      "args": [],
      "return_type": "FastAPI"
    }
  ],
  "imports": ["fastapi", "networkx", "pathlib", "threading"]
}
```

---

## 3. Grounded Q&A & Agentic Investigation Endpoints

### `POST /api/ask`
Executes hybrid retrieval and grounded Q&A with verifiable code citations.

**Request Body:**
```json
{
  "question": "How does the Python parser extract AST classes?",
  "top_k": 3
}
```

**Response `200 OK`:**
```json
{
  "question": "How does the Python parser extract AST classes?",
  "answer": "The PythonParser class uses Python's standard library `ast.parse()`...",
  "citations": [
    {
      "file": "codemind/parsing/python_parser.py",
      "start_line": 45,
      "end_line": 78,
      "score": 0.8842,
      "code_snippet": "class PythonParser:\n    def parse(self, source: SourceFile) -> ParsedFile:..."
    }
  ],
  "latency_ms": 14.25
}
```

---

### `POST /api/investigate`
Dispatches an end-to-end 5-stage agentic investigation.

**Request Body:**
```json
{
  "query": "What is the change impact if we modify the GraphBuilder class?"
}
```

**Response `200 OK`:**
```json
{
  "query": "What is the change impact if we modify the GraphBuilder class?",
  "intent": "IMPACT",
  "status": "SUCCESS",
  "plan": {
    "stages": ["INTENT_CLASSIFICATION", "DYNAMIC_PLANNING", "TOOL_EXECUTION", "GRAPH_EXPANSION", "GROUNDED_SYNTHESIS"],
    "tools_used": ["calculate_change_impact", "select_affected_tests"]
  },
  "findings": [
    "Modifying GraphBuilder directly impacts 3 dependent modules and 12 downstream functions."
  ],
  "citations": [
    {
      "file": "codemind/graph/builder.py",
      "start_line": 35,
      "end_line": 90,
      "context": "GraphBuilder implementation"
    }
  ],
  "limitations": [],
  "latency_ms": 18.50
}
```

---

## 4. Knowledge Graph & Impact Endpoints

### `GET /api/graph`
Returns the serialized NetworkX software knowledge graph.

**Query Parameters:**
- `limit` (integer, optional, default=500): Maximum nodes to return.
- `node_type` (string, optional): Filter by node type (`FILE`, `CLASS`, `FUNCTION`).

**Response `200 OK`:**
```json
{
  "node_count": 372,
  "edge_count": 343,
  "nodes": [
    { "id": "file::codemind/web/app.py", "type": "FILE", "label": "app.py" }
  ],
  "edges": [
    { "source": "file::codemind/web/app.py", "target": "class::CodebaseState", "type": "CONTAINS" }
  ]
}
```

---

### `POST /api/impact/analyze`
Computes the blast radius score and downstream dependency impact of modified files.

**Request Body:**
```json
{
  "modified_files": ["codemind/graph/builder.py"],
  "max_depth": 2
}
```

**Response `200 OK`:**
```json
{
  "target_files": ["codemind/graph/builder.py"],
  "blast_radius_score": 0.4520,
  "affected_files": [
    "codemind/web/app.py",
    "codemind/retrieval/hybrid_retriever.py"
  ],
  "affected_symbols_count": 18,
  "depth_reached": 2
}
```

---

### `POST /api/impact/tests`
Identifies and prioritizes regression tests covering modified files.

**Request Body:**
```json
{
  "modified_files": ["codemind/graph/builder.py"]
}
```

**Response `200 OK`:**
```json
{
  "modified_files": ["codemind/graph/builder.py"],
  "selected_tests": [
    { "test_file": "tests/test_graph.py", "confidence": 1.0, "reason": "Direct module import" },
    { "test_file": "tests/test_hybrid_retrieval.py", "confidence": 0.85, "reason": "Downstream dependency" }
  ],
  "total_tests_selected": 2
}
```

---

## 5. Git Temporal Intelligence Endpoints

### `GET /api/git/status`
Returns Git repository status and active commit pointer.

**Response `200 OK`:**
```json
{
  "is_git_repo": true,
  "branch": "main",
  "head_commit": "e020e1c",
  "is_dirty": false,
  "total_commits": 15
}
```

---

### `GET /api/git/churn`
Returns additions, deletions, net growth, and commit frequency per file.

**Response `200 OK`:**
```json
{
  "total_commits_analyzed": 15,
  "top_churn_files": [
    { "file_path": "services/order_processor.py", "additions": 420, "deletions": 110, "total_churn": 530 }
  ]
}
```

---

### `GET /api/git/coupling`
Returns logically coupled file pairs based on co-change history.

**Response `200 OK`:**
```json
{
  "couplings": [
    {
      "file_a": "domain/cart.py",
      "file_b": "services/order_processor.py",
      "co_commit_count": 8,
      "jaccard_similarity": 0.7273
    }
  ]
}
```

---

## 6. Architecture & Risk Analytics Endpoints

### `GET /api/architecture/overview`
Returns module hierarchy, layers, and quotient graph topology.

**Response `200 OK`:**
```json
{
  "modules": {
    "codemind.web": { "package": "codemind", "layer": "PRESENTATION", "file_count": 4 },
    "codemind.retrieval": { "package": "codemind", "layer": "APPLICATION", "file_count": 3 }
  },
  "layers": [
    { "name": "PRESENTATION", "level": 1, "modules": ["codemind.web"] },
    { "name": "APPLICATION", "level": 2, "modules": ["codemind.retrieval", "codemind.investigation"] },
    { "name": "DOMAIN", "level": 3, "modules": ["codemind.ingestion", "codemind.chunks"] }
  ],
  "quotient_graph": {
    "node_count": 8,
    "edge_count": 14
  }
}
```

---

### `GET /api/architecture/conformance`
Computes the Architecture Conformance Index (ACI) and enumerates rule violations.

**Query Parameters:**
- `strict_layering` (boolean, optional, default=false): Enforce strict adjacent layer transitions.

**Response `200 OK`:**
```json
{
  "aci": 0.9412,
  "total_imports": 34,
  "conforming_imports": 32,
  "violations_count": 2,
  "layer_leak_count": 1,
  "forbidden_import_count": 1,
  "layer_skipping_count": 0,
  "violations": [
    {
      "source_module": "storage",
      "target_module": "services",
      "source_file": "storage/postgres_db.py",
      "rule_type": "LAYER_LEAK",
      "message": "Storage layer imports services (upward layer leak)",
      "line_number": 12
    }
  ]
}
```

---

### `GET /api/architecture/cycles`
Detects package-level dependency cycles via Tarjan's Strongly Connected Components algorithm.

**Response `200 OK`:**
```json
{
  "has_cycles": true,
  "cycle_count": 1,
  "cycles": [
    ["billing", "services", "billing"]
  ],
  "package_sccs": [
    ["billing", "services"]
  ]
}
```

---

### `GET /api/architecture/hotspots`
Calculates composite maintenance risk scores, evidence coverage, and debt archetypes.

**Response `200 OK`:**
```json
{
  "repository_risk_score": 0.6840,
  "hotspots": [
    {
      "module_name": "services/order_processor.py",
      "hotspot_score": 0.8125,
      "archetype": "CRITICAL_ACCUMULATOR",
      "cyclomatic_complexity": 24.5,
      "centrality": 0.72,
      "churn": 0.85,
      "coupling": 0.68,
      "confidence": 0.95
    }
  ],
  "evidence_coverage": {
    "completeness_ratio": 1.0,
    "is_partial": false,
    "missing_signals": []
  }
}
```

---

### `GET /api/benchmarks/summary`
Returns verified quantitative benchmark results, baseline comparisons, and acceptance target statuses.

**Response `200 OK`:**
```json
{
  "dataset": {
    "total_queries": 50,
    "canonical_intents": ["UNDERSTAND", "STRUCTURE", "IMPACT", "EVOLUTION", "INSIGHTS"],
    "queries_per_intent": 10
  },
  "retrieval_metrics": {
    "mean_precision_at_3": 0.5133,
    "precision_at_3_target": ">= 0.7000",
    "precision_at_3_status": "NOT MET (Bounded)",
    "precision_at_3_ceiling": 0.5400,
    "mean_recall_at_3": 0.7117,
    "recall_at_3_target": ">= 0.8000",
    "recall_at_3_status": "NOT MET",
    "mean_reciprocal_rank_mrr": 0.8333,
    "mrr_target": ">= 0.7500",
    "mrr_status": "MET / PASSED",
    "average_latency_ms": 17.75,
    "latency_target_ms": "<= 5000",
    "latency_status": "MET / PASSED"
  },
  "baseline_comparison": {
    "baseline_precision_at_3": 0.1867,
    "baseline_recall_at_3": 0.3350,
    "baseline_mrr": 0.2633,
    "baseline_latency_ms": 18.06,
    "precision_gain": "+175%",
    "recall_gain": "+112%",
    "mrr_gain": "+216%"
  },
  "performance_targets": {
    "graph_traversal_10k_ms": { "measured_median": 1.081, "target": "<= 150", "status": "PASSED" },
    "ast_parsing_complexity_ms": { "measured_median": 9.320, "target": "<= 100", "status": "PASSED" },
    "investigation_planning_ms": { "measured_median": 0.283, "target": "<= 5000", "status": "PASSED" }
  }
}
```
