"""
Browser-Use Vision Enhancement — Ablation Study

系统性关闭各组件，测量每个模块的独立贡献:
  A. Baseline     — 纯 DOM，无视觉，无 SoM
  B. SoM Only     — SoM 截图标注，无视觉后端
  C. Full Always  — 每步都跑完整视觉（OCR + Region Caption），不自适应
  D. OCR Only     — 每步只跑 OCR，无 Region Caption
  E. Adaptive Full— 自适应策略 + 完整视觉（当前默认配置）
  F. Adaptive No SoM — 自适应视觉，但关闭 SoM 标注

成功判定: 客观校验（DOM / URL / 实时 API），而非 Agent 自报 done()。
任务定义、校验器与运行引擎均来自 scripts/benchmark_common.py（单一真相来源）。

用法:
  # 先启动 demo server 和 vision server:
  #   python -m http.server 8088 --directory demo/
  #   python -m browser_use_vision.server --backend florence --port 8100

  PYTHONUNBUFFERED=1 XDG_CONFIG_HOME=~/browser-use-config \
  PYTHONPATH=. python scripts/ablation_benchmark.py

  # 可选: 只跑部分条件
  PYTHONPATH=. python scripts/ablation_benchmark.py --conditions A,B,E
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark_common as bc  # noqa: E402

bc.setup_env()


# ────────────────────────────────────────────
# Ablation conditions
# ────────────────────────────────────────────

ABLATION_CONDITIONS = {
    "A_baseline": {
        "description": "Pure DOM agent, no vision backend, no SoM annotation",
        "use_vision_agent": False,
    },
    "B_som_only": {
        "description": "SoM screenshot annotation only, no vision backend",
        "use_vision_agent": True,
        "vision_backend": None,
        "enable_som": True,
        "enable_adaptive": True,
    },
    "C_full_always": {
        "description": "Vision always FULL (OCR + Region Caption every step), no adaptive skip",
        "use_vision_agent": True,
        "vision_backend": "florence",
        "enable_som": True,
        "enable_adaptive": False,
        "enable_dense_caption": True,
    },
    "D_ocr_only": {
        "description": "Vision OCR only (no Region Caption), every step",
        "use_vision_agent": True,
        "vision_backend": "florence",
        "enable_som": True,
        "enable_adaptive": False,
        "enable_dense_caption": False,
    },
    "E_adaptive_full": {
        "description": "Adaptive vision (SKIP/LIGHTWEIGHT/FULL based on DOM confidence) — default config",
        "use_vision_agent": True,
        "vision_backend": "florence",
        "enable_som": True,
        "enable_adaptive": True,
        "enable_dense_caption": True,
    },
    "F_adaptive_no_som": {
        "description": "Adaptive vision without SoM annotation",
        "use_vision_agent": True,
        "vision_backend": "florence",
        "enable_som": False,
        "enable_adaptive": True,
        "enable_dense_caption": True,
    },
}

INFRA_FAILURE_TYPES = {
    "outer_deadline",
    "internal_timeout",
    "browser_error",
    "llm_error",
    "vision_error",
    "verifier_error",
    "runtime_error",
}


def make_builder(condition: dict, model: str = "gpt-4o-mini"):
    """Return a build_agent(task, session) closure for the given ablation condition."""

    def build(task, session):
        if not condition.get("use_vision_agent", False):
            from browser_use.agent.service import Agent

            return Agent(
                task=task.task,
                llm=bc.make_llm(model=model),
                browser_session=session,
                use_vision=False,
                max_steps=task.max_steps,
            )

        from browser_use_vision.enhanced_agent import VisionEnhancedAgent

        backend = None
        if condition.get("vision_backend") == "florence":
            from browser_use_vision.grounding.florence import FlorenceBackend

            backend = FlorenceBackend(remote_url=bc.VISION_API)

        return VisionEnhancedAgent(
            task=task.task,
            llm=bc.make_llm(model=model),
            browser_session=session,
            vision_backend=backend,
            use_vision=backend is not None,
            enable_som=condition.get("enable_som", True),
            enable_adaptive=condition.get("enable_adaptive", True),
            enable_dense_caption=condition.get("enable_dense_caption", True),
            max_steps=task.max_steps,
        )

    return build


def make_run_id(model: str, selected_conditions: list[str]) -> str:
    env_run_id = os.environ.get("BROWSER_USE_RUN_ID")
    if env_run_id:
        return env_run_id
    model_token = model.replace("/", "-")
    condition_token = "".join(cond.split("_", 1)[0] for cond in selected_conditions)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ablation-{model_token}-{condition_token}-{stamp}"


# ────────────────────────────────────────────
# Report generation
# ────────────────────────────────────────────


def build_summary(results: list[bc.TaskResult]) -> dict:
    conditions_run = [cond for cond in ABLATION_CONDITIONS if any(r.label == cond for r in results)]
    categories = ["icon-heavy", "mixed", "dom-rich"]

    by_condition = {}
    for cond in ABLATION_CONDITIONS:
        cond_results = [r for r in results if r.label == cond]
        n = len(cond_results)
        successes = sum(1 for r in cond_results if r.success)
        if not n:
            by_condition[cond] = {
                "status": "not_run",
                "success_rate": None,
                "successes": 0,
                "total": 0,
                "attempts": 0,
                "avg_steps": None,
                "avg_time": None,
                "total_vision_calls": None,
                "zero_step_count": 0,
                "infra_failure_count": 0,
                "eligible_attempt_count": 0,
                "completion_rate": None,
                "failure_type_counts": {},
            }
            continue

        failure_type_counts = {}
        for result in cond_results:
            failure_type = result.failure_type or bc.classify_failure_type(
                success=result.success,
                error=result.error,
                verify_detail=result.verify_detail,
            )
            failure_type_counts[failure_type] = failure_type_counts.get(failure_type, 0) + 1
        infra_failure_count = sum(
            count for failure_type, count in failure_type_counts.items() if failure_type in INFRA_FAILURE_TYPES
        )
        eligible_attempt_count = n - infra_failure_count
        by_condition[cond] = {
            "status": "present",
            "success_rate": round(successes / n, 3),
            "successes": successes,
            "total": n,
            "attempts": n,
            "avg_steps": round(sum(r.steps for r in cond_results) / n, 2),
            "avg_time": round(sum(r.time_seconds for r in cond_results) / n, 1),
            "total_vision_calls": sum(r.vision_calls for r in cond_results),
            "zero_step_count": sum(1 for r in cond_results if r.steps == 0),
            "infra_failure_count": infra_failure_count,
            "eligible_attempt_count": eligible_attempt_count,
            "completion_rate": round(eligible_attempt_count / n, 3),
            "failure_type_counts": dict(sorted(failure_type_counts.items())),
        }

    by_category = {}
    for cat in categories:
        by_category[cat] = {}
        for cond in ABLATION_CONDITIONS:
            cat_cond = [r for r in results if r.category == cat and r.label == cond]
            n = len(cat_cond)
            successes = sum(1 for r in cat_cond if r.success)
            by_category[cat][cond] = {
                "status": "present" if n else "not_run",
                "success_rate": round(successes / n, 3) if n else None,
                "successes": successes,
                "total": n,
            }

    return {"conditions_run": conditions_run, "by_condition": by_condition, "by_category": by_category}


def generate_markdown_report(
    results: list[bc.TaskResult],
    summary: dict,
    output_path: Path,
    model: str = "gpt-4o-mini",
    report_date: str | None = None,
):
    conditions = list(ABLATION_CONDITIONS)
    conditions_run = summary.get("conditions_run") or [c for c in conditions if summary["by_condition"][c]["total"]]
    tasks = list(dict.fromkeys(r.task_name for r in results))
    bcd = summary["by_condition"]

    def _fmt_rate(value):
        return "not run" if value is None else f"{value:.0%}"

    def _fmt_number(value, *, suffix: str = "", digits: int = 1):
        if value is None:
            return "not run"
        return f"{value:.{digits}f}{suffix}"

    lines = [
        "# Ablation Study Report",
        "",
        f"**Date**: {report_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"**Model**: {model} | **Tasks**: {len(tasks)} | **Conditions run**: {len(conditions_run)}",
        "**Success**: objective verification (DOM / URL / live API), not agent self-report",
        "**Rows**: benchmark attempts; infra failures are not counted as completed agent executions.",
        "",
        "## Overall Results",
        "",
        "| Condition | Status | Attempts | Success Rate | Completion Rate | Infra Failures | Zero-Step | Avg Steps | Avg Time | Vision Calls |",
        "|-----------|--------|---------:|-------------|-----------------|---------------:|----------:|-----------|----------|--------------|",
    ]
    for cond in conditions:
        s = bcd[cond]
        status = "run" if s["status"] == "present" else "not run"
        attempts = s["total"] if s["status"] == "present" else "not run"
        vision_calls = s["total_vision_calls"] if s["total_vision_calls"] is not None else "not run"
        lines.append(
            f"| {cond} | {status} | {attempts} | {_fmt_rate(s['success_rate'])} "
            f"| {_fmt_rate(s['completion_rate'])} | {s['infra_failure_count']} | {s['zero_step_count']} "
            f"| {_fmt_number(s['avg_steps'])} | {_fmt_number(s['avg_time'], suffix='s', digits=0)} "
            f"| {vision_calls} |"
        )

    lines += ["", "## Results by Category", ""]
    for cat in ["icon-heavy", "mixed", "dom-rich"]:
        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| Condition | Success Rate |")
        lines.append("|-----------|-------------|")
        for cond in conditions:
            s = summary["by_category"][cat][cond]
            if s["status"] == "not_run":
                lines.append(f"| {cond} | not run |")
            else:
                lines.append(f"| {cond} | {s['successes']}/{s['total']} ({s['success_rate']:.0%}) |")
        lines.append("")

    lines += ["## Per-Task Matrix", ""]
    header = "| Task | Category |" + "|".join(f" {c.split('_', 1)[0]} " for c in conditions) + "|"
    sep = "|------|----------|" + "|".join("----" for _ in conditions) + "|"
    lines.append(header)
    lines.append(sep)

    result_map = {(r.task_name, r.label): r for r in results}
    for task_name in tasks:
        cat = next(r.category for r in results if r.task_name == task_name)
        cells = []
        for cond in conditions:
            r = result_map.get((task_name, cond))
            if r:
                mark = "✅" if r.success else "❌"
                cells.append(f" {mark} {r.steps}st ")
            else:
                cells.append(" not run ")
        lines.append(f"| {task_name} | {cat} |" + "|".join(cells) + "|")

    lines += ["", "## Key Findings", ""]
    bcat = summary["by_category"]

    def _has(cond):
        return bcd.get(cond, {}).get("status") == "present"

    def _rate(cond):
        return bcd.get(cond, {}).get("success_rate")

    def _calls(cond):
        return bcd.get(cond, {}).get("total_vision_calls")

    def _icon(cond):
        c = bcat.get("icon-heavy", {}).get(cond, {})
        return c.get("successes", 0), c.get("total", 0)

    lines.append("> Success is objective verification (DOM / URL / live API), not agent self-report.")
    lines.append("")
    if _has("A_baseline") and _has("C_full_always"):
        a_rate, c_rate = _rate("A_baseline"), _rate("C_full_always")
        lines.append(
            f"- **Full vision (C) vs baseline (A)**: {c_rate:.0%} vs {a_rate:.0%} "
            f"({c_rate - a_rate:+.0%}) across the conditions that were actually run."
        )
    if _has("A_baseline") and _has("E_adaptive_full"):
        a_rate, e_rate = _rate("A_baseline"), _rate("E_adaptive_full")
        a_icon_s, a_icon_n = _icon("A_baseline")
        e_icon_s, e_icon_n = _icon("E_adaptive_full")
        lines.append(
            f"- **Adaptive full (E) vs baseline (A)**: {e_rate:.0%} vs {a_rate:.0%} "
            f"({e_rate - a_rate:+.0%}); icon-heavy outcomes were E {e_icon_s}/{e_icon_n} vs "
            f"A {a_icon_s}/{a_icon_n}."
        )
    if _has("C_full_always") and _has("E_adaptive_full"):
        c_calls, e_calls = _calls("C_full_always"), _calls("E_adaptive_full")
        budget = (e_calls / c_calls) if c_calls else None
        c_icon_s, c_icon_n = _icon("C_full_always")
        e_icon_s, e_icon_n = _icon("E_adaptive_full")
        budget_text = "not comparable" if budget is None else f"{budget:.0%} of C"
        lines.append(
            f"- **Vision budget**: E used {e_calls} vision calls vs C's {c_calls} ({budget_text}); "
            f"icon-heavy outcomes were E {e_icon_s}/{e_icon_n} vs C {c_icon_s}/{c_icon_n}."
        )
    missing = [cond for cond in conditions if not _has(cond)]
    if missing:
        lines.append(f"- **Not run**: {', '.join(missing)}. These conditions are excluded from comparisons.")
    lines.append(
        "- **Failure attribution**: this report records typed failures, but it does not claim that all "
        "remaining failures come from the vision model rather than the gate, browser, LLM, verifier, or service layer."
    )
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📝 Report: {output_path}")


# ────────────────────────────────────────────
# Main
# ────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="Ablation benchmark")
    parser.add_argument(
        "--conditions",
        type=str,
        default=None,
        help="Comma-separated condition prefixes to run, e.g. A,B,E (default: all)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model name (default: gpt-4o-mini). Non-default models write to a model-stamped output file.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Override per-task timeout in seconds (default: each task's own timeout). "
        "Raise it for full-vision conditions where Florence latency can exceed the default.",
    )
    args = parser.parse_args()

    model = args.model
    if args.timeout:
        for t in bc.TASKS:
            t.timeout = args.timeout

    if args.conditions:
        prefixes = [p.strip().upper() for p in args.conditions.split(",")]
        selected = {k: v for k, v in ABLATION_CONDITIONS.items() if k[0] in prefixes}
    else:
        selected = ABLATION_CONDITIONS

    print("=" * 64)
    print("🔬 Ablation Study: browser-use-vision")
    print("=" * 64)
    print(
        f"Model: {model} | Conditions: {len(selected)} | Tasks: {len(bc.TASKS)} | Total runs: {len(selected) * len(bc.TASKS)}"
    )
    for name, cond in selected.items():
        print(f"  {name}: {cond['description']}")
    print("=" * 64)

    all_results: list[bc.TaskResult] = []

    for ci, (cond_name, cond) in enumerate(selected.items()):
        print(f"\n{'═' * 64}")
        print(f"[{ci + 1}/{len(selected)}] Condition: {cond_name}")
        print(f"  {cond['description']}")
        print(f"{'─' * 64}")

        build = make_builder(cond, model=model)
        for task in bc.TASKS:
            result = await bc.run_task(task, build, label=cond_name)
            all_results.append(result)
            await asyncio.sleep(2)

        successes = sum(1 for r in all_results if r.label == cond_name and r.success)
        print(f"  → {cond_name}: {successes}/{len(bc.TASKS)} succeeded")

    # ────────────────────────────────────────
    # Output
    # ────────────────────────────────────────
    summary = build_summary(all_results)

    print(f"\n{'═' * 64}")
    print("📊 ABLATION RESULTS")
    print(f"{'═' * 64}\n")

    bcd = summary["by_condition"]
    print(f"{'Condition':<25} {'Success':<12} {'Avg Steps':<11} {'Avg Time':<10} {'Vision Calls'}")
    print("─" * 75)
    for cond in summary["conditions_run"]:
        s = bcd[cond]
        print(
            f"{cond:<25} {s['successes']}/{s['total']} ({s['success_rate']:.0%})"
            f"{'':>4} {s['avg_steps']:<11.1f} {s['avg_time']:<10.0f} {s['total_vision_calls']}"
        )

    output_dir = ROOT / "output" / "benchmark_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = make_run_id(model, list(selected))

    report_data = {
        "benchmark_name": "Ablation Study",
        "version": "0.4.0",
        "date": run_date,
        "run_id": run_id,
        "model": model,
        "vision_backend": "Florence-2 (localhost:8100)",
        "success_criterion": "objective verification (DOM / URL / live API)",
        "record_type": "benchmark attempts",
        "conditions": {k: {"description": v["description"]} for k, v in selected.items()},
        "results": [
            {
                "task": t,
                "category": next(r.category for r in all_results if r.task_name == t),
                "conditions": {
                    r.label: {
                        "success": r.success,
                        "steps": r.steps,
                        "time_seconds": r.time_seconds,
                        "vision_calls": r.vision_calls,
                        "verify_detail": r.verify_detail,
                        "is_done": r.is_done,
                        "error": r.error or None,
                        "failure_type": r.failure_type,
                    }
                    for r in all_results
                    if r.task_name == t
                },
            }
            for t in dict.fromkeys(r.task_name for r in all_results)
        ],
        "summary": summary,
    }

    # Non-default models write to model-stamped files so the canonical gpt-4o-mini
    # results (ablation_results.json) are never clobbered by a one-off model sweep.
    stamp = "" if model == "gpt-4o-mini" else f"_{model.replace('/', '-')}"
    json_path = output_dir / f"ablation_results{stamp}.json"
    with open(json_path, "w") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"\n💾 JSON: {json_path}")

    md_path = output_dir / f"ablation_report{stamp}.md"
    generate_markdown_report(all_results, summary, md_path, model=model, report_date=run_date)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("browser_use.telemetry").setLevel(logging.WARNING)

    asyncio.run(main())
