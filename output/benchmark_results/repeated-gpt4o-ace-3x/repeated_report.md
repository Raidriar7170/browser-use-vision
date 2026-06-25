# Repeated Benchmark Aggregation

Bootstrap samples: 2000
Bootstrap seed: 20260625
CI method: task-cluster bootstrap for condition rates; paired task-cluster bootstrap for deltas

Note: missing conditions are reported as missing, not zero-performance rows. Delta CIs use paired task-name clusters when available.

| Condition | Success Rate Mean | 95% CI | Avg Steps | Avg Vision Calls | Avg Time | Delta vs A | Delta vs C Vision | Frontier |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A_baseline | 0.354 | [0.146, 0.562] | 1.958 | 0.000 | 41.592s | +0.000 | -0.88 | yes |
| C_full_always | 0.375 | [0.188, 0.562] | 1.792 | 1.333 | 75.108s | +0.062 | +0.00 | yes |
| E_adaptive_full | 0.292 | [0.146, 0.479] | 1.708 | 1.042 | 67.623s | +0.062 | +0.25 | no |
