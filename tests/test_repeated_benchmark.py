from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import repeated_benchmark as rb  # noqa: E402


def _nested_run(run_id: str, *, adaptive_second_success: bool) -> dict:
    return {
        "benchmark_name": "Synthetic repeated ablation",
        "run_id": run_id,
        "results": [
            {
                "task": "icon_music_player",
                "category": "icon-heavy",
                "conditions": {
                    "A_baseline": {"success": False, "steps": 3, "vision_calls": 0, "time_seconds": 9.0},
                    "C_full_always": {"success": True, "steps": 2, "vision_calls": 2, "time_seconds": 12.0},
                    "E_adaptive_full": {"success": True, "steps": 2, "vision_calls": 1, "time_seconds": 10.0},
                },
            },
            {
                "task": "quotes_first_author",
                "category": "dom-rich",
                "conditions": {
                    "A_baseline": {"success": True, "steps": 2, "vision_calls": 0, "time_seconds": 4.0},
                    "C_full_always": {"success": True, "steps": 2, "vision_calls": 2, "time_seconds": 8.0},
                    "E_adaptive_full": {
                        "success": adaptive_second_success,
                        "steps": 2,
                        "vision_calls": 0,
                        "time_seconds": 5.0,
                    },
                },
            },
        ],
    }


def test_aggregates_repeated_nested_ablation_runs_with_bootstrap_ci_and_deltas():
    summary = rb.aggregate_repeated_results(
        [_nested_run("run-1", adaptive_second_success=True), _nested_run("run-2", adaptive_second_success=False)],
        bootstrap_samples=300,
        seed=11,
    )

    assert summary["conditions_order"] == ["A_baseline", "C_full_always", "E_adaptive_full"]
    assert summary["total_records"] == 12

    adaptive = summary["conditions"]["E_adaptive_full"]
    assert adaptive["records"] == 4
    assert adaptive["successes"] == 3
    assert adaptive["success_rate_mean"] == 0.75
    assert adaptive["success_rate_ci95"][0] <= adaptive["success_rate_mean"] <= adaptive["success_rate_ci95"][1]
    assert adaptive["avg_steps"] == 2.0
    assert adaptive["avg_vision_calls"] == 0.5
    assert adaptive["avg_time_seconds"] == 7.5
    assert adaptive["delta_vs_A_baseline"]["success_rate"] == 0.25
    assert adaptive["delta_vs_C_full_always"]["vision_calls"] == -1.5
    assert adaptive["frontier"]["success_per_vision_call"] == 1.5


def test_loads_existing_single_ablation_json_without_running_live_benchmark():
    result_path = ROOT / "output" / "benchmark_results" / "ablation_results.json"

    summary = rb.aggregate_repeated_result_files([result_path], bootstrap_samples=100, seed=3)

    assert summary["source_files"] == [str(result_path)]
    assert summary["conditions_order"] == ["A_baseline", "C_full_always", "E_adaptive_full"]
    assert set(summary["conditions"]) == {"A_baseline", "C_full_always", "E_adaptive_full"}
    assert summary["conditions"]["A_baseline"]["records"] > 0
    assert "category_breakdown" in summary["conditions"]["E_adaptive_full"]


def test_missing_condition_is_reported_as_missing_not_zero_performance():
    payload = {
        "run_id": "run-1",
        "results": [
            {
                "task": "icon_music_player",
                "category": "icon-heavy",
                "conditions": {
                    "A_baseline": {"success": True, "steps": 2, "vision_calls": 0, "time_seconds": 3.0},
                    "C_full_always": {"success": True, "steps": 2, "vision_calls": 3, "time_seconds": 4.0},
                },
            }
        ],
    }

    summary = rb.aggregate_repeated_results([payload], bootstrap_samples=50, seed=7)

    missing = summary["conditions"]["E_adaptive_full"]
    assert missing["status"] == "missing"
    assert missing["records"] == 0
    assert missing["success_rate_mean"] is None
    assert missing["success_rate_ci95"] == [None, None]
    assert missing["delta_vs_A_baseline"] is None
    assert missing["frontier"]["is_pareto_candidate"] is False


def test_delta_ci_uses_paired_run_task_blocks():
    payload = {
        "run_id": "run-1",
        "results": [
            {
                "task": "task_one",
                "category": "icon-heavy",
                "conditions": {
                    "A_baseline": {"success": False, "steps": 4, "vision_calls": 0, "time_seconds": 4.0},
                    "E_adaptive_full": {"success": True, "steps": 2, "vision_calls": 1, "time_seconds": 5.0},
                },
            },
            {
                "task": "task_two",
                "category": "dom-rich",
                "conditions": {
                    "A_baseline": {"success": True, "steps": 2, "vision_calls": 0, "time_seconds": 2.0},
                    "E_adaptive_full": {"success": False, "steps": 3, "vision_calls": 0, "time_seconds": 3.0},
                },
            },
        ],
    }

    summary = rb.aggregate_repeated_results(
        [payload],
        bootstrap_samples=0,
        conditions=["A_baseline", "E_adaptive_full"],
    )

    adaptive = summary["conditions"]["E_adaptive_full"]
    assert adaptive["delta_vs_A_baseline"]["success_rate"] == 0.0
    assert adaptive["delta_vs_A_baseline_ci95"]["success_rate"] == [0.0, 0.0]
    assert adaptive["paired_blocks_vs_A_baseline"] == 2


def test_missing_numeric_metrics_do_not_become_zero_latency_or_zero_steps():
    payload = {
        "run_id": "run-1",
        "results": [
            {
                "task": "task_one",
                "category": "icon-heavy",
                "conditions": {
                    "A_baseline": {"success": True},
                    "C_full_always": {"success": True, "steps": 2, "vision_calls": 3, "time_seconds": 4.0},
                },
            },
            {
                "task": "task_two",
                "category": "icon-heavy",
                "conditions": {
                    "A_baseline": {"success": True, "steps": 8, "vision_calls": 0, "time_seconds": 12.0},
                    "C_full_always": {"success": True, "steps": 3, "vision_calls": 4, "time_seconds": 6.0},
                },
            },
        ],
    }

    summary = rb.aggregate_repeated_results([payload], bootstrap_samples=0, conditions=["A_baseline", "C_full_always"])

    baseline = summary["conditions"]["A_baseline"]
    assert baseline["avg_steps"] == 8.0
    assert baseline["avg_vision_calls"] == 0.0
    assert baseline["avg_time_seconds"] == 12.0
    assert baseline["missing_metric_counts"] == {"steps": 1, "vision_calls": 1, "time_seconds": 1}


def test_condition_ci_uses_task_name_clusters_not_independent_rows():
    payload = {
        "runs": [
            {
                "run_id": "r1",
                "results": [
                    {
                        "task": "stable_task",
                        "category": "dom-rich",
                        "conditions": {"A_baseline": {"success": True}},
                    },
                    {
                        "task": "flaky_task",
                        "category": "icon-heavy",
                        "conditions": {"A_baseline": {"success": False}},
                    },
                ],
            },
            {
                "run_id": "r2",
                "results": [
                    {
                        "task": "stable_task",
                        "category": "dom-rich",
                        "conditions": {"A_baseline": {"success": True}},
                    },
                    {
                        "task": "flaky_task",
                        "category": "icon-heavy",
                        "conditions": {"A_baseline": {"success": True}},
                    },
                ],
            },
        ]
    }

    summary = rb.aggregate_repeated_results([payload], bootstrap_samples=0, conditions=["A_baseline"])

    baseline = summary["conditions"]["A_baseline"]
    assert "task-cluster" in summary["ci_method"]
    assert baseline["task_clusters"] == 2
    assert baseline["success_rate_ci95"] == [0.75, 0.75]
