# Repeated Benchmark Aggregation

Diagnostic run: condition order was fixed and an external CDP browser was reused across task sessions.
Do not promote this repeated result as a headline improvement claim.

Bootstrap samples: 2000
Bootstrap seed: 20260625
CI method: task-cluster bootstrap for condition rates; paired task-cluster bootstrap for deltas

Note: rows are benchmark attempts, not necessarily completed agent executions. Missing conditions are reported as missing, not zero-performance rows. Delta CIs use paired task-name clusters when available.

| Condition | Attempts | Success Rate Mean | 95% CI | Completion Rate | Infra Failures | Zero-Step | Avg Steps | Avg Vision Calls | Avg Time | Delta vs A | Delta vs C Vision | Frontier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A_baseline | 48 | 0.354 | [0.146, 0.562] | 0.521 | 23 | 21 | 1.958 | 0.000 | 41.592s | +0.000 | -1.33 | yes |
| C_full_always | 48 | 0.375 | [0.188, 0.562] | 0.562 | 21 | 17 | 1.792 | 1.333 | 75.108s | +0.021 | +0.00 | yes |
| E_adaptive_full | 48 | 0.292 | [0.146, 0.479] | 0.479 | 25 | 24 | 1.708 | 1.042 | 67.623s | -0.062 | -0.29 | no |
