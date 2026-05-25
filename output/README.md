# output/ — Test Artifacts & Benchmark Data

## Directory Structure

### `benchmark_results/` — ★ Primary Evidence

The authoritative benchmark data referenced by the project README.

| File | Description |
|------|-------------|
| `real_world_11_tasks.json` | Machine-readable results: 11 tasks × 2 modes (baseline vs vision), with per-task steps, timing, and success/failure |
| `real_world_11_tasks.md` | Human-readable report with summary tables and key findings |

These are the **canonical results**. The README Performance section is derived from this data.

> `real_world_results.json` is a raw dump from an intermediate benchmark run (12 tasks, many timeouts due to network instability). It is kept for provenance but **superseded** by `real_world_11_tasks.json`.

### `demo_results/` — Early-Stage Demo Artifacts

Single-task comparison artifacts from initial development (icon_only_player baseline vs vision). These predate the full benchmark and demonstrate the original motivation for the project.

| File | Description |
|------|-------------|
| `icon_only_results.json` | Single-task result from `demo_icon_only.py` |
| `demo_report.html` | Visual HTML report of the demo run |

> **Note:** `icon_only_results.json` may show `is_done: false` even when the agent performed the correct action — this is because the baseline agent clicked the right button but did not call the `done()` action to signal task completion. The 11-task benchmark addresses this with improved success criteria.

### `e2e_results/` — E2E Integration Tests

End-to-end test results from `scripts/e2e_test.py` (3 scenarios: icon_only_player, dynamic_spa, color_picker).

| File | Description |
|------|-------------|
| `e2e_results.json` | Per-scenario pass/fail results |
| `e2e_report.html` | Visual HTML report |
