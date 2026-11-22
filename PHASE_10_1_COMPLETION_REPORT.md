# CodeMind Milestone 10.1 Completion Report: Benchmarking & Systematic Evaluation

**Milestone:** 10.1 — Benchmarking & Systematic Evaluation  
**Status:** Completed & Verified  
**Date:** 2026-11-22  
**Base Git Commit (HEAD):** `7a8ce1292863d24e3fd749c90a893997a8737cef` (`docs: add phase 10 master plan`)  
**Tested Revision:** Working-tree modifications on top of `7a8ce12` (uncommitted Milestone 10.1 deliverables)  
**Working Directory:** `c:\Users\user\Desktop\Codemind\CodeMind`  
**Generated Artifacts:**
- `tests/benchmarks/fixtures/` (`repo_small`, `repo_medium`, `repo_large`)
- `tests/benchmarks/golden_dataset.json` (50 curated developer queries)
- `tests/benchmarks/fixture_generator.py` (Deterministic fixture generator)
- `scripts/evaluate_benchmarks.py` (Evaluation runner)
- `tests/test_benchmarks.py` (Benchmark test suite — 5/5 passing)
- `benchmark_results_baseline.json` (Empirical baseline measurements)
- `BENCHMARK_BASELINE_REPORT.md` (Formal baseline evaluation report)

---

## 1. Summary of Completed Deliverables

### 1.1 Deterministic Repository Fixtures (`tests/benchmarks/fixtures/`)
Generated three standardized, reproducible test repositories:
- **`repo_small`**: 15 Python files (10 primary modules, ~287 LOC), clean 3-tier layering (API $\to$ Services $\to$ Models/DB $\to$ Utils) with 3 git commits for churn and author attribution.
- **`repo_medium`**: 58 Python files (50 primary modules, ~1,538 LOC) across 8 packages (`core`, `auth`, `billing`, `services`, `domain`, `adapters`, `storage`, `utils`). Includes intentional package cycle (`billing` $\leftrightarrow$ `services`), upward layer leak (`storage/postgres_db.py` $\to$ `services/notification_service.py`), known God class (`MegaOrderProcessor` with McCabe cyclomatic complexity $>20$), and 15 commits with intentional co-change coupling.
- **`repo_large`**: 265 Python files (250 primary modules, ~28,015 LOC) across 15 packages. Provides a synthetic scalability repository with dense inter-module dependencies for stress-testing ingestion, AST parsing, and graph algorithms.

### 1.2 Golden Evaluation Dataset (`tests/benchmarks/golden_dataset.json`)
Constructed 50 curated developer queries distributed uniformly across all five canonical investigation intents (10 queries each):
1. **UNDERSTAND (Q01–Q10):** Workflow explanations, method mechanics, data serialization.
2. **STRUCTURE (Q11–Q20):** Callers, callees, class hierarchies, import dependencies.
3. **IMPACT (Q21–Q30):** Blast radius, transitive ripple effects, breakage analysis.
4. **EVOLUTION (Q31–Q40):** Historical churn, Git commit logs, author attribution, logical co-change coupling.
5. **INSIGHTS (Q41–Q50):** Architecture overview, package cycles, layer violations, hotspot archetypes, ACI metrics.

Each entry contains ground-truth target files, symbols/chunks, structural facts (callers/dependencies/cycles), and line-range citations.

### 1.3 Systematic Evaluation Runner (`scripts/evaluate_benchmarks.py`)
Implemented standalone evaluation harness with nanosecond precision (`time.perf_counter_ns()`) and memory profiling (`tracemalloc`). Evaluates:
- **Retrieval Quality:** Precision@3, Recall@3, Mean Reciprocal Rank (MRR).
- **Citation Integrity:** File existence, line-range boundary validation, and fabricated citation detection.
- **System Performance:** Ingestion latency (cold vs. warm), AST parsing latency, graph traversal latency, query response latency, peak memory footprint.
- **Groundedness Evaluation:** Lexical and structural grounding checks with explicit documentation that semantic natural-language faithfulness requires external live LLM API access.

---

## 2. Empirical Baseline Measurements (Unoptimized)

The following empirical measurements were recorded directly by executing `python scripts/evaluate_benchmarks.py` on the host machine:

### 2.1 Host Environment
- **OS:** Windows-11-10.0.26300-SP0 (AMD64)
- **CPU:** Intel64 Family 6 Model 197 Stepping 2, 16 logical cores
- **RAM:** 15.23 GB physical memory
- **Python:** 3.12.9
- **Core Dependencies:** `fastapi 0.143.3`, `pydantic 2.14.1`, `sentence_transformers 6.1.0`, `torch 2.14.1+cpu`, `chromadb 1.5.9`, `networkx 3.7`, `pytest 9.1.1`

### 2.2 Scalability Profile Across Repository Scales
| Repository | Files | LOC | AST Chunks | Graph Nodes / Edges | Cold Ingestion | Warm Ingestion | AST Parse | Peak Memory |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`repo_small`** | 15 | 287 | 55 | 58 / 62 | 560.19 ms | 2.12 ms | 10.07 ms | 0.74 MB |
| **`repo_medium`** | 58 | 1,538 | 359 | 248 / 312 | 701.22 ms | 6.45 ms | 39.06 ms | 2.64 MB |
| **`repo_large`** | 265 | 28,015 | 2,765 | 1,420 / 1,850 | 3,310.42 ms | 28.14 ms | 1,197.67 ms | 18.32 MB |

### 2.3 Quality and Integrity Metrics
| Metric | Baseline Measurement | Proposed Milestone Target | Target Status |
| :--- | :--- | :--- | :--- |
| **Intent Classification Accuracy** | **100.00%** (50/50) | $\ge 90.00\%$ | PASSED |
| **Retrieval Mean Precision@3** | **0.1867** | $\ge 0.7000$ | NOT MET (Baseline Recorded) |
| **Retrieval Mean Recall@3** | **0.3350** | $\ge 0.8000$ | NOT MET (Baseline Recorded) |
| **Retrieval Mean Reciprocal Rank (MRR)** | **0.2633** | $\ge 0.7500$ | NOT MET (Baseline Recorded) |
| **Citation Validity Rate** | **100.00%** | $100.00\%$ | PASSED |
| **Fabricated Citation Rate** | **0.00%** | $0.00\%$ | PASSED |
| **Average Query Latency** | **18.66 ms** | $\le 5,000\text{ ms}$ | PASSED |

> [!NOTE]
> **Baseline Recording vs. Milestone Acceptance:**
> Proposed milestone targets for retrieval quality (Precision@3, Recall@3, MRR) are explicitly **NOT MET** on the pre-optimization baseline. These measurements reflect the unoptimized retrieval pipeline and establish the empirical baseline against which Milestone 10.3 (Performance Optimization and Scalability) will be measured. Integrity metrics (citation validity, non-fabrication, latency, intent classification) all PASSED.

### 2.4 Per-Intent Performance Breakdown
| Intent | Queries | Accuracy | Precision@3 | Recall@3 | MRR | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **UNDERSTAND** | 10 | 100.0% | 0.1667 | 0.3000 | 0.2333 | 12.45 ms |
| **STRUCTURE** | 10 | 100.0% | 0.2000 | 0.3500 | 0.2833 | 14.82 ms |
| **IMPACT** | 10 | 100.0% | 0.1667 | 0.3000 | 0.2333 | 22.10 ms |
| **EVOLUTION** | 10 | 100.0% | 0.2333 | 0.4000 | 0.3167 | 24.35 ms |
| **INSIGHTS** | 10 | 100.0% | 0.1667 | 0.3250 | 0.2500 | 19.58 ms |

---

## 3. Test Suite Verification Gate

1. **Benchmark Test Suite:**
   `python -m pytest tests/test_benchmarks.py -v`
   - **Result:** **5 passed in 6.15s** (100% pass rate).
   - Validated dataset schema, intent distribution, mathematical correctness of Precision@K, Recall@K, and MRR, citation validity, and hardware info collection.
2. **Complete Existing Test Suite:**
   `python -m pytest tests -q`
   - **Result:** **365 passed, 2 failed in 26.83s** across 367 items.
   - Zero regressions. The only two failures remain the pre-identified issues in `test_investigation_api.py` slated for Milestone 10.2.

---

## 4. Verification Gate Approval & Hand-off

Milestone 10.1 acceptance criteria have been fully satisfied. The quantitative empirical baseline is established without synthetic score inflation.
We now proceed to **Milestone 10.2: Reliability & Production Hardening**.
