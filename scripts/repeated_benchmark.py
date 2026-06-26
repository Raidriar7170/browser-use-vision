"""Repeated benchmark aggregation utilities.

This module is intentionally offline-only: it summarizes existing ablation JSON
or repeated live-result JSON files, but it never starts a browser, model, or
vision backend.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

TRIAD_CONDITIONS = ["A_baseline", "C_full_always", "E_adaptive_full"]
INFRA_FAILURE_TYPES = {
    "outer_deadline",
    "internal_timeout",
    "browser_error",
    "llm_error",
    "vision_error",
    "verifier_error",
    "runtime_error",
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _mean_optional(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _bootstrap_ci_binary(values: list[bool], *, samples: int, seed: int) -> list[float]:
    if not values:
        return [0.0, 0.0]
    if samples <= 0:
        mean = _mean([1.0 if v else 0.0 for v in values])
        return [_round(mean), _round(mean)]

    rng = random.Random(seed)
    n = len(values)
    draws = []
    numeric = [1.0 if v else 0.0 for v in values]
    for _ in range(samples):
        draws.append(sum(rng.choice(numeric) for _ in range(n)) / n)
    draws.sort()
    low_idx = int(0.025 * (samples - 1))
    high_idx = int(0.975 * (samples - 1))
    return [_round(draws[low_idx]), _round(draws[high_idx])]


def _bootstrap_ci_numeric(values: list[float], *, samples: int, seed: int) -> list[float]:
    if not values:
        return [0.0, 0.0]
    if samples <= 0:
        mean = _mean(values)
        return [_round(mean), _round(mean)]

    rng = random.Random(seed)
    n = len(values)
    draws = []
    for _ in range(samples):
        draws.append(sum(rng.choice(values) for _ in range(n)) / n)
    draws.sort()
    low_idx = int(0.025 * (samples - 1))
    high_idx = int(0.975 * (samples - 1))
    return [_round(draws[low_idx]), _round(draws[high_idx])]


def _metric_value(metrics: dict[str, Any], *names: str, default: float | None = None) -> float | None:
    for name in names:
        value = metrics.get(name)
        if value is not None:
            return float(value)
    return default


def _failure_type(metrics: dict[str, Any]) -> str:
    existing = metrics.get("failure_type")
    if existing:
        return str(existing)
    if bool(metrics.get("success", False)):
        return "none"

    error = str(metrics.get("error") or "")
    detail = str(metrics.get("verify_detail") or "")
    error_low = error.lower()
    detail_low = detail.lower()
    if error.startswith("Timeout (") or error_low.startswith("outer deadline"):
        return "outer_deadline"
    if "timeout" in error_low or "timeouterror" in error_low:
        return "internal_timeout"
    if any(token in error_low for token in ("browser", "cdp", "playwright", "chrome")):
        return "browser_error"
    if any(token in error_low for token in ("openai", "llm", "rate limit", "api")):
        return "llm_error"
    if any(token in error_low for token in ("florence", "vision", "ocr", "caption")):
        return "vision_error"
    if error:
        return "runtime_error"
    if detail_low.startswith("verify error"):
        return "verifier_error"
    return "objective_verification_failed"


def _record_from_metrics(
    *,
    condition: str,
    metrics: dict[str, Any],
    task_name: str,
    category: str,
    run_id: str,
    source: str | None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "source": source,
        "condition": condition,
        "task_name": task_name,
        "category": category or "unknown",
        "success": bool(metrics.get("success", False)),
        "steps": _metric_value(metrics, "steps"),
        "vision_calls": _metric_value(metrics, "vision_calls", "total_vision_calls"),
        "time_seconds": _metric_value(metrics, "time_seconds", "latency_seconds", "avg_time", "duration_seconds"),
        "failure_type": _failure_type(metrics),
    }


def _normalize_payload(payload: dict[str, Any], *, source: str | None = None, run_prefix: str = "run") -> list[dict]:
    records: list[dict] = []

    if isinstance(payload.get("runs"), list):
        for idx, run in enumerate(payload["runs"]):
            run_id = str(run.get("run_id") or run.get("id") or f"{run_prefix}-{idx + 1}")
            records.extend(_normalize_payload(run, source=source, run_prefix=run_id))
        return records

    run_id = str(payload.get("run_id") or payload.get("id") or (Path(source).stem if source else run_prefix))
    raw_results = payload.get("results") or payload.get("records") or []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("conditions"), dict):
            task_name = str(item.get("task") or item.get("task_name") or item.get("name") or "unknown")
            category = str(item.get("category") or "unknown")
            for condition, metrics in item["conditions"].items():
                if isinstance(metrics, dict):
                    records.append(
                        _record_from_metrics(
                            condition=condition,
                            metrics=metrics,
                            task_name=task_name,
                            category=category,
                            run_id=run_id,
                            source=source,
                        )
                    )
            continue

        condition = item.get("condition") or item.get("label")
        if condition:
            records.append(
                _record_from_metrics(
                    condition=str(condition),
                    metrics=item,
                    task_name=str(item.get("task") or item.get("task_name") or item.get("name") or "unknown"),
                    category=str(item.get("category") or "unknown"),
                    run_id=run_id,
                    source=source,
                )
            )

    return records


def _validate_unique_records(records: list[dict]) -> None:
    seen: dict[tuple[str, str, str], str | None] = {}
    for record in records:
        key = (str(record["run_id"]), str(record["task_name"]), str(record["condition"]))
        if key in seen:
            run_id, task_name, condition = key
            raise ValueError(
                "duplicate benchmark record for "
                f"run_id={run_id!r}, task_name={task_name!r}, condition={condition!r} "
                f"(sources: {seen[key]!r}, {record.get('source')!r})"
            )
        seen[key] = record.get("source")


def _category_breakdown(records: list[dict]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["category"]].append(record)

    breakdown = {}
    for category, rows in sorted(grouped.items()):
        successes = sum(1 for row in rows if row["success"])
        total = len(rows)
        breakdown[category] = {
            "records": total,
            "successes": successes,
            "success_rate": _round(successes / total if total else 0.0),
        }
    return breakdown


def _task_cluster_means(records: list[dict], field: str) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in records:
        value = record.get(field)
        if value is None:
            continue
        grouped[str(record["task_name"])].append(float(value))
    return [_mean(values) for values in grouped.values() if values]


def _task_cluster_success_means(records: list[dict]) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in records:
        grouped[str(record["task_name"])].append(1.0 if record["success"] else 0.0)
    return [_mean(values) for values in grouped.values() if values]


def _condition_summary(records: list[dict], *, bootstrap_samples: int, seed: int) -> dict[str, Any]:
    if not records:
        return {
            "status": "missing",
            "records": 0,
            "attempts": 0,
            "successes": 0,
            "success_rate_mean": None,
            "success_rate_ci95": [None, None],
            "avg_steps": None,
            "avg_vision_calls": None,
            "avg_time_seconds": None,
            "zero_step_count": 0,
            "infra_failure_count": 0,
            "eligible_attempt_count": 0,
            "completion_rate": None,
            "failure_type_counts": {},
            "category_breakdown": {},
            "frontier": {
                "success_per_vision_call": None,
                "is_pareto_candidate": False,
            },
        }

    successes = [bool(row["success"]) for row in records]
    total = len(records)
    success_count = sum(1 for ok in successes if ok)
    success_rate = success_count / total if total else 0.0
    avg_steps = _mean_optional([row["steps"] for row in records])
    avg_vision = _mean_optional([row["vision_calls"] for row in records])
    avg_time = _mean_optional([row["time_seconds"] for row in records])
    success_clusters = _task_cluster_success_means(records)
    missing_metric_counts = {
        name: sum(1 for row in records if row[name] is None) for name in ("steps", "vision_calls", "time_seconds")
    }
    zero_step_count = sum(1 for row in records if row["steps"] == 0)
    failure_type_counts: dict[str, int] = defaultdict(int)
    for row in records:
        failure_type_counts[str(row.get("failure_type") or "none")] += 1
    infra_failure_count = sum(
        count for failure_type, count in failure_type_counts.items() if failure_type in INFRA_FAILURE_TYPES
    )
    eligible_attempt_count = total - infra_failure_count
    return {
        "status": "present",
        "records": total,
        "attempts": total,
        "successes": success_count,
        "task_clusters": len(success_clusters),
        "success_rate_mean": _round(success_rate),
        "success_rate_ci95": _bootstrap_ci_numeric(success_clusters, samples=bootstrap_samples, seed=seed),
        "avg_steps": _round(avg_steps),
        "avg_vision_calls": _round(avg_vision),
        "avg_time_seconds": _round(avg_time),
        "missing_metric_counts": missing_metric_counts,
        "zero_step_count": zero_step_count,
        "infra_failure_count": infra_failure_count,
        "eligible_attempt_count": eligible_attempt_count,
        "completion_rate": _round(eligible_attempt_count / total if total else 0.0),
        "failure_type_counts": dict(sorted(failure_type_counts.items())),
        "category_breakdown": _category_breakdown(records),
        "frontier": {
            "success_per_vision_call": _round(success_rate / avg_vision) if avg_vision and avg_vision > 0 else None,
            "is_pareto_candidate": False,
        },
    }


def _index_records(records: list[dict]) -> dict[tuple[str, str], dict]:
    return {(str(record["run_id"]), str(record["task_name"])): record for record in records}


def _paired_delta(
    current_records: list[dict],
    baseline_records: list[dict],
    *,
    bootstrap_samples: int,
    seed: int,
) -> tuple[dict[str, float] | None, dict[str, list[float]] | None, int]:
    current_index = _index_records(current_records)
    baseline_index = _index_records(baseline_records)
    paired_keys = sorted(set(current_index) & set(baseline_index))
    if not paired_keys:
        return None, None, 0

    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for key in paired_keys:
        task_name = key[1]
        current = current_index[key]
        baseline = baseline_index[key]
        grouped[task_name]["success_rate"].append(
            (1.0 if current["success"] else 0.0) - (1.0 if baseline["success"] else 0.0)
        )
        for metric in ("steps", "vision_calls", "time_seconds"):
            if current[metric] is not None and baseline[metric] is not None:
                grouped[task_name][metric].append(current[metric] - baseline[metric])

    success_deltas = [_mean(values["success_rate"]) for values in grouped.values() if values["success_rate"]]
    step_deltas = [_mean(values["steps"]) for values in grouped.values() if values["steps"]]
    vision_deltas = [_mean(values["vision_calls"]) for values in grouped.values() if values["vision_calls"]]
    time_deltas = [_mean(values["time_seconds"]) for values in grouped.values() if values["time_seconds"]]

    point = {
        "success_rate": _mean(success_deltas),
        "steps": _round(_mean(step_deltas)) if step_deltas else None,
        "vision_calls": _round(_mean(vision_deltas)) if vision_deltas else None,
        "time_seconds": _round(_mean(time_deltas)) if time_deltas else None,
    }
    ci = {
        "success_rate": _bootstrap_ci_numeric(success_deltas, samples=bootstrap_samples, seed=seed),
        "steps": _bootstrap_ci_numeric(step_deltas, samples=bootstrap_samples, seed=seed + 1)
        if step_deltas
        else [None, None],
        "vision_calls": _bootstrap_ci_numeric(vision_deltas, samples=bootstrap_samples, seed=seed + 2)
        if vision_deltas
        else [None, None],
        "time_seconds": _bootstrap_ci_numeric(time_deltas, samples=bootstrap_samples, seed=seed + 3)
        if time_deltas
        else [None, None],
    }
    return point, ci, len(success_deltas)


def _delta(current: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, float] | None:
    if baseline is None or current.get("status") == "missing" or baseline.get("status") == "missing":
        return None

    def _metric_delta(name: str) -> float | None:
        if current[name] is None or baseline[name] is None:
            return None
        return _round(current[name] - baseline[name])

    return {
        "success_rate": current["success_rate_mean"] - baseline["success_rate_mean"],
        "steps": _metric_delta("avg_steps"),
        "vision_calls": _metric_delta("avg_vision_calls"),
        "time_seconds": _metric_delta("avg_time_seconds"),
    }


def _mark_pareto_frontier(condition_summaries: dict[str, dict[str, Any]]) -> None:
    items = list(condition_summaries.items())
    for name, current in items:
        if current.get("status") == "missing":
            current["frontier"]["is_pareto_candidate"] = False
            continue
        dominated = False
        for other_name, other in items:
            if other_name == name:
                continue
            if other.get("status") == "missing":
                continue
            if (
                current["avg_vision_calls"] is None
                or current["avg_time_seconds"] is None
                or other["avg_vision_calls"] is None
                or other["avg_time_seconds"] is None
            ):
                continue
            no_worse = (
                other["success_rate_mean"] >= current["success_rate_mean"]
                and other["avg_vision_calls"] <= current["avg_vision_calls"]
                and other["avg_time_seconds"] <= current["avg_time_seconds"]
            )
            strictly_better = (
                other["success_rate_mean"] > current["success_rate_mean"]
                or other["avg_vision_calls"] < current["avg_vision_calls"]
                or other["avg_time_seconds"] < current["avg_time_seconds"]
            )
            if no_worse and strictly_better:
                dominated = True
                break
        current["frontier"]["is_pareto_candidate"] = not dominated


def _aggregate_records(
    all_records: list[dict],
    *,
    bootstrap_samples: int,
    seed: int,
    conditions: list[str],
) -> dict[str, Any]:
    _validate_unique_records(all_records)

    filtered = [record for record in all_records if record["condition"] in conditions]
    by_condition = {condition: [] for condition in conditions}
    for record in filtered:
        by_condition[record["condition"]].append(record)

    condition_summaries = {
        condition: _condition_summary(rows, bootstrap_samples=bootstrap_samples, seed=seed + idx)
        for idx, (condition, rows) in enumerate(by_condition.items())
    }

    baseline = condition_summaries.get("A_baseline")
    full = condition_summaries.get("C_full_always")
    for condition, summary in condition_summaries.items():
        paired_a, paired_a_ci, paired_a_blocks = _paired_delta(
            by_condition[condition],
            by_condition.get("A_baseline", []),
            bootstrap_samples=bootstrap_samples,
            seed=seed + 100,
        )
        paired_c, paired_c_ci, paired_c_blocks = _paired_delta(
            by_condition[condition],
            by_condition.get("C_full_always", []),
            bootstrap_samples=bootstrap_samples,
            seed=seed + 200,
        )
        summary["delta_vs_A_baseline"] = paired_a or _delta(summary, baseline)
        summary["delta_vs_A_baseline_ci95"] = paired_a_ci
        summary["paired_blocks_vs_A_baseline"] = paired_a_blocks
        summary["delta_vs_C_full_always"] = paired_c or _delta(summary, full)
        summary["delta_vs_C_full_always_ci95"] = paired_c_ci
        summary["paired_blocks_vs_C_full_always"] = paired_c_blocks
        if (
            summary.get("status") != "missing"
            and full
            and full.get("status") != "missing"
            and full["avg_vision_calls"] is not None
            and summary["avg_vision_calls"] is not None
        ):
            summary["frontier"]["vision_call_savings_vs_C_full_always"] = _round(
                full["avg_vision_calls"] - summary["avg_vision_calls"]
            )
        else:
            summary["frontier"]["vision_call_savings_vs_C_full_always"] = None

    _mark_pareto_frontier(condition_summaries)
    return {
        "conditions_order": conditions,
        "total_records": len(filtered),
        "total_attempts": len(filtered),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
        "ci_method": "task-cluster bootstrap for condition rates; paired task-cluster bootstrap for deltas",
        "conditions": condition_summaries,
    }


def aggregate_repeated_results(
    payloads: list[dict[str, Any]],
    bootstrap_samples: int = 1000,
    seed: int = 0,
    conditions: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate one or more benchmark payloads.

    Supported inputs:
    - existing ablation JSON: ``results[].conditions[condition]``
    - repeated wrapper JSON: ``runs[].results``
    - flat result rows: ``results[]`` or ``records[]`` with ``condition``/``label``
    """
    wanted = conditions or TRIAD_CONDITIONS
    all_records: list[dict] = []
    for idx, payload in enumerate(payloads):
        all_records.extend(_normalize_payload(payload, run_prefix=f"run-{idx + 1}"))
    return _aggregate_records(all_records, bootstrap_samples=bootstrap_samples, seed=seed, conditions=wanted)


def aggregate_repeated_result_files(
    paths: list[str | Path],
    bootstrap_samples: int = 1000,
    seed: int = 0,
    conditions: list[str] | None = None,
) -> dict[str, Any]:
    all_records: list[dict] = []
    source_files = []
    wanted = conditions or TRIAD_CONDITIONS
    for idx, path_like in enumerate(paths):
        path = Path(path_like)
        source_files.append(str(path))
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        all_records.extend(_normalize_payload(payload, source=str(path), run_prefix=f"run-{idx + 1}"))

    summary = _aggregate_records(
        all_records,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
        conditions=wanted,
    )
    summary["source_files"] = source_files
    return summary


def build_markdown_report(summary: dict[str, Any]) -> str:
    def _fmt(value: float | None, suffix: str = "") -> str:
        if value is None:
            return "missing"
        return f"{value:.3f}{suffix}"

    def _fmt_ci(ci: list[float | None]) -> str:
        if ci == [None, None]:
            return "missing"
        return f"[{ci[0]:.3f}, {ci[1]:.3f}]"

    def _fmt_delta(value: float | None, digits: int = 3) -> str:
        if value is None:
            return "missing"
        return f"{value:+.{digits}f}"

    lines = [
        "# Repeated Benchmark Aggregation",
        "",
        "Diagnostic run: condition order was fixed and an external CDP browser was reused across task sessions.",
        "Do not promote this repeated result as a headline improvement claim.",
        "",
        f"Bootstrap samples: {summary.get('bootstrap_samples', 0)}",
        f"Bootstrap seed: {summary.get('bootstrap_seed', 0)}",
        f"CI method: {summary.get('ci_method', 'task-run bootstrap')}",
        "",
        "Note: rows are benchmark attempts, not necessarily completed agent executions. Missing conditions are reported as missing, not zero-performance rows. Delta CIs use paired task-name clusters when available.",
        "",
        "| Condition | Attempts | Success Rate Mean | 95% CI | Completion Rate | Infra Failures | Zero-Step | Avg Steps | Avg Vision Calls | Avg Time | Delta vs A | Delta vs C Vision | Frontier |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for condition in summary["conditions_order"]:
        item = summary["conditions"][condition]
        ci = item["success_rate_ci95"]
        delta_a = item.get("delta_vs_A_baseline") or {}
        delta_c = item.get("delta_vs_C_full_always") or {}
        frontier = "yes" if item["frontier"]["is_pareto_candidate"] else "no"
        lines.append(
            f"| {condition} | {item.get('attempts', item['records'])} | {_fmt(item['success_rate_mean'])} | {_fmt_ci(ci)} "
            f"| {_fmt(item.get('completion_rate'))} | {item.get('infra_failure_count', 0)} | {item.get('zero_step_count', 0)} "
            f"| {_fmt(item['avg_steps'])} | {_fmt(item['avg_vision_calls'])} | {_fmt(item['avg_time_seconds'], 's')} "
            f"| {_fmt_delta(delta_a.get('success_rate'))} | {_fmt_delta(delta_c.get('vision_calls'), 2)} | {frontier} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate repeated browser-use-vision benchmark JSON files.")
    parser.add_argument("files", nargs="+", type=Path, help="Existing ablation or repeated-result JSON files")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    summary = aggregate_repeated_result_files(args.files, bootstrap_samples=args.bootstrap_samples, seed=args.seed)
    if args.json_output:
        args.json_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = build_markdown_report(summary)
    if args.markdown_output:
        args.markdown_output.write_text(report, encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
