# RQ3 Methodology and Reproducibility Audit Report

## 1. Benchmark Construction and Ground Truth
- **Repository**: `ResilienceOS` (Healthcare Infrastructure Resilience Simulation Engine, Python/FastAPI/SQLAlchemy).
- **Git Commit Hash**: `f354dd9361eed0fb2dad6f34e25d04fc771993b3`.
- **Benchmark Scope**: 15 controlled change scenarios stratified across 3 architectural tiers (5 Leaf, 5 Service, 5 Core).
- **Ground Truth Universe**: Exactly 64 scenario-target instances (52 code components, 12 regression test suites).
- **Independence Guarantee**: Ground truth targets were established by dynamic execution traces and manual commit inspection, independent of static heuristic mining.

## 2. Prediction Task and Target Inclusion
- **Task Definition**: Given a changed repository file $s$, predict the set of affected repository code components and relevant regression-test files.
- **Target Inclusion Rule**: The changed target file itself is explicitly included in the component prediction set because modifying a component inherently affects that component. This rule is applied uniformly across all evaluated systems.

## 3. Path Normalization and Exact Matching Protocol
- **No Substring Matching**: Substring matching (`p in g or g in p`) is strictly banned. Evaluation uses exact path equality (`p == g`) on canonical repository-relative paths.
- **Normalization**: Converts all path separators to `/`, strips absolute repository prefixes, trims `./`, and applies lowercase normalization for consistent cross-platform matching.
- **Deduplication**: Predictions are deduplicated within each scenario before evaluation.

## 4. Compared Systems and Baselines
1. **Baseline A (Structural Only)**: Static AST reverse dependency traversal (CALLS, INHERITS, IMPORTS) with target file included. No temporal co-change, no test recommendations.
2. **Baseline B (Structural + Temporal)**: Static AST reverse dependency traversal + strictly 1-hop temporal co-change expansion mined from Git history. No test recommendations.
3. **CodeMind Minus Temporal Coupling**: Static AST reverse dependency traversal + test intelligence recommendations. No temporal co-change.
4. **CodeMind Full**: Static AST reverse dependency traversal + 1-hop temporal co-change + test intelligence recommendations.

## 5. Ablations and Multi-Signal Target Risk Scorer
- **Synthetic Multiplier Removal**: All synthetic metric multipliers (e.g., `* 0.92`, `* 0.95`) have been completely deleted. All ablations represent actual executions of the software system.
- **Scorer Decoupling**: The six-signal impact scorer computes target-level risk $S_{\text{impact}}(s) \in [0, 1]$ and signal contributions. It is descriptively reported and strictly decoupled from candidate set prediction.\n\n## 6. Reproducibility Statement
The entire benchmark can be reproduced with a single command:
```bash
python research_experiments/e3_impact_scoring.py
```
All execution logs, per-scenario predictions, ground-truth paths, and test metrics are persisted in `research_experiments/results/rq3_final/`.
