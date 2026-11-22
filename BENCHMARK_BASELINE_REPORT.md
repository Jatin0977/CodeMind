# CodeMind Milestone 10.1: Benchmark Baseline Evaluation Report

**Generated:** 2026-11-22T18:42:24Z  
**Phase:** Phase 10 — Evaluation, Optimization & Deployment  
**Status:** Empirical Baseline Established (Pre-Optimization)  

---

## 1. Evaluation Environment & System Configuration

| Attribute | Value |
| :--- | :--- |
| **Operating System** | Windows-11-10.0.26300-SP0 |
| **CPU Architecture** | Intel64 Family 6 Model 197 Stepping 2, GenuineIntel (16 logical cores) |
| **Physical Memory (RAM)** | 15.23 GB |
| **Python Version** | 3.12.9 (tags/v3.12.9:fdb8142) |
| **Embedding Provider** | mock (Deterministic) |
| **Evaluator Engine** | deterministic_offline_mock |

### Key Dependency Versions
| Package | Version |
| :--- | :--- |
| `pydantic` | 2.14.1 |
| `fastapi` | 0.143.3 |
| `sentence_transformers` | 6.1.0 |
| `torch` | 2.14.1+cpu |
| `chromadb` | 1.5.9 |
| `networkx` | 3.7 |
| `pytest` | 9.1.1 |

---

## 2. Repository Scalability Benchmarks (Cold vs. Warm)

| Scale Metric | `repo_small` | `repo_medium` | `repo_large` |
| :--- | :--- | :--- | :--- |
| **Source Files** | 15 | 58 | 265 |
| **Total LOC** | 287 | 1538 | 28015 |
| **AST Chunks** | 55 | 359 | 2765 |
| **Knowledge Graph Nodes** | 58 | 372 | 2766 |
| **Knowledge Graph Edges** | 80 | 343 | 2765 |
| **Cold Ingestion Latency** | 597.47 ms | 671.88 ms | 3458.60 ms |
| **Warm Ingestion Latency** | 4.38 ms | 11.95 ms | 48.16 ms |
| **AST Parsing Latency** | 8.57 ms | 39.85 ms | 1178.29 ms |
| **Graph Traversal Latency** | 0.17 ms | 0.12 ms | 0.24 ms |
| **Peak Memory Footprint** | 0.75 MB | 2.64 MB | 18.32 MB |

---

## 3. Aggregate Retrieval & Citation Quality Metrics

| Evaluation Metric | Baseline Measurement | Proposed Milestone Target | Target Status |
| :--- | :--- | :--- | :--- |
| **Mean Precision@3** | **0.1867** | $\ge 0.7000$ | NOT MET (Baseline Recorded) |
| **Mean Recall@3** | **0.3350** | $\ge 0.8000$ | NOT MET (Baseline Recorded) |
| **Mean Reciprocal Rank (MRR)** | **0.2633** | $\ge 0.7500$ | NOT MET (Baseline Recorded) |
| **Intent Classification Accuracy** | **100.00%** | $\ge 90.00\%$ | PASSED |
| **Citation Validity Rate** | **100.00%** | $100.00\%$ | PASSED |
| **Fabricated Citation Rate** | **0.00%** | $0.00\%$ | PASSED |
| **Average Query Latency** | **18.06 ms** | $\le 5000\text{ ms}$ | PASSED |

---

## 4. Per-Intent Performance Breakdown (50 Golden Queries)

| Investigation Intent | Queries | Intent Accuracy | Precision@3 | Recall@3 | MRR | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **UNDERSTAND** | 10 | 100.0% | 0.1000 | 0.2000 | 0.1500 | 0.95 ms |
| **STRUCTURE** | 10 | 100.0% | 0.2333 | 0.6000 | 0.3500 | 0.53 ms |
| **IMPACT** | 10 | 100.0% | 0.3333 | 0.3417 | 0.4333 | 0.56 ms |
| **EVOLUTION** | 10 | 100.0% | 0.2333 | 0.4333 | 0.2833 | 85.89 ms |
| **INSIGHTS** | 10 | 100.0% | 0.0333 | 0.1000 | 0.1000 | 2.35 ms |

---

## 5. Groundedness Evaluation & Analysis Limitations

> [!IMPORTANT]
> **Methodological Grounding Notice:**
> Heuristic citation checks alone do not prove semantic natural-language faithfulness. In this offline evaluation suite:
> 1. **Citation Verification:** Every citation returned was deterministically resolved against the physical file AST and line boundaries.
> 2. **Lexical Evidence Alignment:** Chunks retrieved via hybrid dense vector similarity + graph expansion were matched against golden ground truth.
> 3. **LLM Evaluator Boundary:** External LLM-as-a-judge semantic faithfulness scoring is disabled during offline CI benchmarking to eliminate synthetic metric fabrication.

### Known Limitations & Bottlenecks for Optimization (Milestone 10.3)
1. **Single-threaded Ingestion:** Sequential AST parsing on `repo_large` (250 files) represents the primary wall-clock bottleneck.
2. **Pure-Python Centrality:** PageRank power iteration in `hotspots.py` iterates sequentially in pure Python without vectorized matrix multiplication.
3. **Quotient Graph Re-computation:** Module quotient graph is currently recomputed on every architecture scan without SHA-based caching.

---
**Conclusion:** Milestone 10.1 quantitative baseline has been successfully established and recorded. Ready for Milestone 10.2 Reliability & Hardening.