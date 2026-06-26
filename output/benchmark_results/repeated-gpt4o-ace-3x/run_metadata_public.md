# Repeated Benchmark Run Metadata

- Date: 2026-06-25
- Model: `gpt-4o`
- Temperature: `0.0`
- Conditions: `A_baseline`, `C_full_always`, `E_adaptive_full`
- Tasks: 16
- Repeats: 3
- Total benchmark attempts: 144
- Demo server: `127.0.0.1:8088`
- Florence vision server: `127.0.0.1:8100`
- Browser mode: external Chromium CDP session, reused across task sessions
- Benchmark code commit before result artifacts: `4f748aa`
- Success criterion: objective verifier from `scripts/benchmark_common.py`
- Aggregation: task-cluster bootstrap for condition rates; paired task-cluster bootstrap for deltas
- Interpretation: diagnostic repeated run only; fixed condition order and reused external CDP browser mean this should not be promoted as a headline improvement claim.

Notes:

- Raw per-repeat ablation outputs are stored in `raw/`.
- Aggregated outputs are `repeated_summary.json` and `repeated_report.md`.
- External-site failures and timeouts were kept as observed outcomes.
- Attempts with infrastructure deadlines are typed separately from objective-verification failures and are not necessarily completed agent executions.
