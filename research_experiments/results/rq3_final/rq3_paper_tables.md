# RQ3 Publication-Ready Tables

## Table 1: Comparative Evaluation of CodeMind against Baselines on RQ3 (N=15 Scenarios, 64 GT Instances)

| System Configuration | Preds | TP | FP | FN | Micro Prec | Micro Rec | Micro F1 | Macro Prec | Macro Rec | Macro F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Baseline A (Structural Only) | 94 | 31 | 63 | 33 | 33.0\% | 48.4\% | 0.3924 | 42.4\% | 54.8\% | 0.4338 |
| Baseline B (Structural + Temporal) | 118 | 35 | 83 | 29 | 29.7\% | 54.7\% | 0.3846 | 32.6\% | 59.4\% | 0.4022 |
| **CodeMind (Full Multi-Signal)** | **197** | **45** | **152** | **19** | **22.8\%** | **70.3\%** | **0.3448** | **25.0\%** | **74.7\%** | **0.3560** |

## Table 2: Category-Specific Decomposition: Code Components vs. Regression Tests

| System | Code Preds | Code GT | Code TP | Code Rec | Code Prec | Test Preds | Test GT | Test TP | Test Rec | Test Prec |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Baseline A | 94 | 52 | 31 | 59.6\% | 33.0\% | 0 | 12 | 0 | 0.0\% | N/A |
| Baseline B | 118 | 52 | 35 | 67.3\% | 29.7\% | 0 | 12 | 0 | 0.0\% | N/A |
| Minus Temporal | 94 | 52 | 31 | 59.6\% | 33.0\% | 65 | 12 | 10 | 83.3\% | 15.4\% |
| **CodeMind Full** | **118** | **52** | **35** | **67.3\%** | **29.7\%** | **79** | **12** | **10** | **83.3\%** | **12.7\%** |

## Table 3: Genuinely Isolated Ablation Study (All Executed on Benchmark)

| Experimental Configuration | Predictions | TP | FP | FN | Micro Recall | Micro F1 | Macro F1 | Delta F1 (Macro) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Full System | 197 | 45 | 152 | 19 | 70.3\% | 0.3448 | 0.3560 | Ref |
| Minus Temporal Coupling | 159 | 41 | 118 | 23 | 64.1\% | 0.3677 | 0.4255 | +0.0695 |
| Minus Test Intelligence (= Baseline B) | 118 | 35 | 83 | 29 | 54.7\% | 0.3846 | 0.4022 | +0.0463 |
| Structural Only (= Baseline A) | 94 | 31 | 63 | 33 | 48.4\% | 0.3924 | 0.4338 | +0.0778 |

## Table 4: Descriptive Summary of Multi-Signal Impact Scorer Across Scenarios

| Scenario ID | Tier | Target File | S1 (Reach) | S2 (Cent) | S3 (Churn) | S4 (Coup) | S5 (Test) | S6 (CCN) | Composite Score | Risk Level | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SCEN-01 | Leaf | `simulation/report_generator.py` | 0.73 | 0.04 | 0.10 | 0.00 | 0.00 | 0.00 | **0.2432** | LOW | 1.00 |
| SCEN-02 | Leaf | `models/api_responses.py` | 0.68 | 0.05 | 0.10 | 0.50 | 0.02 | 0.00 | **0.3063** | MEDIUM | 1.00 |
| SCEN-03 | Leaf | `backend/app/core/logging_config.py` | 0.38 | 0.04 | 0.10 | 0.67 | 0.00 | 0.00 | **0.2353** | LOW | 1.00 |
| SCEN-04 | Leaf | `database/models/simulation_run.py` | 0.15 | 0.07 | 0.05 | 0.00 | 0.53 | 0.00 | **0.1186** | LOW | 1.00 |
| SCEN-05 | Leaf | `simulation/explanation_engine.py` | 0.62 | 0.04 | 0.05 | 0.00 | 0.94 | 0.00 | **0.2953** | MEDIUM | 1.00 |
| SCEN-06 | Service | `simulation/resilience_index.py` | 0.99 | 0.06 | 0.15 | 0.22 | 0.00 | 0.00 | **0.3656** | MEDIUM | 1.00 |
| SCEN-07 | Service | `simulation/state_engine.py` | 1.00 | 0.13 | 0.50 | 0.49 | 0.00 | 0.00 | **0.4753** | MEDIUM | 1.00 |
| SCEN-08 | Service | `graph/traversals.py` | 0.68 | 0.08 | 0.05 | 0.00 | 0.00 | 0.00 | **0.2277** | LOW | 1.00 |
| SCEN-09 | Service | `backend/app/services/hospital_service.py` | 0.18 | 0.07 | 0.05 | 0.00 | 0.53 | 0.00 | **0.1279** | LOW | 1.00 |
| SCEN-10 | Service | `models/infrastructure.py` | 1.00 | 0.16 | 0.15 | 0.00 | 0.00 | 0.00 | **0.3536** | MEDIUM | 1.00 |
| SCEN-11 | Core | `simulation/cascade_engine.py` | 0.56 | 0.04 | 0.20 | 0.00 | 0.43 | 0.00 | **0.2497** | LOW | 1.00 |
| SCEN-12 | Core | `graph/topology_builder.py` | 1.00 | 0.05 | 0.25 | 0.80 | 0.00 | 0.00 | **0.4673** | MEDIUM | 1.00 |
| SCEN-13 | Core | `backend/app/api/simulation.py` | 0.98 | 0.04 | 0.50 | 0.49 | 0.00 | 0.00 | **0.4494** | MEDIUM | 1.00 |
| SCEN-14 | Core | `database/session.py` | 0.32 | 0.04 | 0.20 | 0.20 | 0.05 | 0.00 | **0.1705** | LOW | 1.00 |
| SCEN-15 | Core | `models/service.py` | 0.99 | 0.15 | 0.05 | 0.00 | 0.00 | 0.00 | **0.3347** | MEDIUM | 1.00 |
