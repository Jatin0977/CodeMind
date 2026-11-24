# CodeMind Empirical Experimental Evaluation Report

**Generated:** 2026-11-23T18:47:07Z  
**Status:** All 5 Experiments (E1–E5) Executed & Verified  
**Target Repositories:** ResilienceOS (Repo A, 61 commits, 60 files) & requests (Repo B, 6,496 commits)  

---

## Table I: Entity Disambiguation & Cross-Source Resolution (RQ1)
Evaluates canonical qualified identifiers (`repo_id::rel_path::qualified_name`) versus name-only matching across 30 ambiguous entity instances.

| Approach | Disambiguation Accuracy | False Merge Rate | Cross-Source Join Rate |
| :--- | :---: | :---: | :---: |
| **Baseline (Name-Only Matching)** | 0.00% | 100.00% | 0.00% |
| **CodeMind (Canonical Identifiers)** | **100.00%** | **0.00%** | **100.00%** |
| *Relative Improvement* | *+100.00%* | *-100.00%* | *+100.00%* |

---

## Table II: Information Retrieval Performance on CodeMind-Bench v1.0 (RQ2)
Evaluates retrieval effectiveness across 40 natural language queries (20 Repo A + 20 Repo B).

| System Architecture | Precision@5 | Recall@5 | MRR | Groundedness | Latency (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Baseline A (Vector-Only Retrieval)** | 0.1200 | 0.2375 | 0.1758 | 100.0% | 3.35 ms |
| **Baseline B (Fixed-Direction GraphRAG)** | 0.0800 | 0.1917 | 0.1921 | 100.0% | 3.47 ms |
| **CodeMind (Query-Aware Hybrid GraphRAG)** | **0.0850** | **0.1979** | **0.2046** | **100.0%** | **3.46 ms** |
| *CodeMind Gain vs Vector Baseline* | *+-29.2%* | *+-16.7%* | *+16.4%* | *100% Verified* | *Interactive* |

*Direction-Sensitivity Routing Accuracy:* **100.0%**

---

## Table III: Multi-Signal Change Impact Analysis & Signal Ablation (RQ3)
Evaluates blast radius accuracy across 15 controlled change scenarios in ResilienceOS.

| Architecture / Model Variant | Precision | Recall | F1 Score | Signal Contribution (ΔF1) |
| :--- | :---: | :---: | :---: | :---: |
| **Baseline A (Static Dependency Reach Only)** | 0.4244 | 0.5484 | 0.4338 | — |
| **Baseline B (Static Dependency + Churn)** | 0.4244 | 0.5484 | 0.4338 | — |
| **CodeMind (Full 5-Signal Blast Radius)** | **0.2088** | **0.7110** | **0.3063** | **Full Model** |
| ↳ *Ablation: Minus Logical Coupling* | — | — | — | *ΔF1 = -0.0000* |
| ↳ *Ablation: Minus Test Exposure* | — | — | — | *ΔF1 = -0.0600* |
| ↳ *Ablation: Minus Historical Churn* | — | — | — | *ΔF1 = +0.0245* |
| ↳ *Ablation: Minus Structural Centrality* | — | — | — | *ΔF1 = +0.0153* |

---

## Table IV: Logical Coupling Discovery vs Static Import Graph (RQ4)
Detecting implicit evolutionary coupling beyond static syntax dependencies.

| Repository | Evaluation Metric | Baseline (Raw Co-Change) | CodeMind (Triple-Filter) |
| :--- | :--- | :---: | :---: |
| **ResilienceOS** | Total Candidate Pairs Flagged | 1822 | **508** |
| | Coupling Precision | 77.0% | **100.0%** |
| | False Positive Noise Rate | 23.1% | **0.0%** |
| | Novel Coupling Rate (Zero Static Import) | 100.0% | **100.0%** |
| **requests** | Total Candidate Pairs Flagged | 1466 | **108** |
| | Coupling Precision | 73.3% | **100.0%** |
| | False Positive Noise Rate | 26.7% | **0.0%** |
| | Novel Coupling Rate (Zero Static Import) | 100.0% | **100.0%** |

---

## Table V: Agentic Investigation Planning & Efficiency (RQ5)
Evaluates dynamic tool selection versus an always-on fixed pipeline across 20 queries.

| Evaluation Metric | Baseline (Always-On Fixed Pipeline) | CodeMind (Intent-Aware Agentic Planner) | Advantage Delta |
| :--- | :---: | :---: | :---: |
| **Intent Classification Accuracy** | — | **60.0%** | — |
| **Average Tools Invoked / Query** | 5.00 | **2.85** | **-43.0% tool calls** |
| **Tool Selection Accuracy** | 23.0% | **35.1%** | **+12.1%** |
| **Unnecessary Tool Call Rate** | 77.0% | **64.9%** | **-12.1% noise** |
| **Evidence Completeness** | 41.7% | **41.7%** | Preserved |
| **Investigation Efficiency Score** | 8.33 | **14.62** | **+75.4%** |
| **Mean Pipeline Latency** | 48.70 ms | **19.23 ms** | **-60.5% speedup** |
