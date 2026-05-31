"""
Browser-Use Vision Enhancement — Real-World Benchmark

在真实公开网站 + 本地 fixture 上对比 baseline (纯 DOM) vs vision-enhanced Agent。
每个任务跑两次: baseline + vision，记录步数、耗时、成功/失败。

成功判定: 客观校验（DOM / URL / 实时 API），而非 Agent 自报 done()。
任务定义、校验器与运行引擎均来自 scripts/benchmark_common.py（单一真相来源）。

用法:
  # 先启动 demo server 和 vision server:
  #   python -m http.server 8088 --directory demo/
  #   python -m browser_use_vision.server --backend florence --port 8100
  # 跑前先关 macOS SOCKS 代理:
  #   networksetup -setsocksfirewallproxystate "Wi-Fi" off

  PYTHONUNBUFFERED=1 XDG_CONFIG_HOME=~/browser-use-config \
  PYTHONPATH=. python scripts/real_world_benchmark.py
"""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark_common as bc  # noqa: E402

bc.setup_env()


# ────────────────────────────────────────────
# Agent builders (baseline / vision)
# ────────────────────────────────────────────


def build_baseline(task, session):
    from browser_use.agent.service import Agent

    return Agent(
        task=task.task,
        llm=bc.make_llm(),
        browser_session=session,
        use_vision=False,
        max_steps=task.max_steps,
    )


def build_vision(task, session):
    from browser_use_vision.enhanced_agent import VisionEnhancedAgent
    from browser_use_vision.grounding.florence import FlorenceBackend

    return VisionEnhancedAgent(
        task=task.task,
        llm=bc.make_llm(),
        browser_session=session,
        vision_backend=FlorenceBackend(remote_url=bc.VISION_API),
        use_vision=True,
        enable_som=True,
        enable_adaptive=True,
        max_steps=task.max_steps,
    )


# ────────────────────────────────────────────
# Main
# ────────────────────────────────────────────


async def main():
    print("=" * 64)
    print("🔬 Real-World Benchmark: Baseline vs Vision-Enhanced")
    print("=" * 64)
    print(f"Tasks: {len(bc.TASKS)} | Mode: baseline + vision per task")
    print("LLM: gpt-4o-mini | Vision: Florence-2 (localhost:8100)")
    print("Success: objective verification (DOM / URL / live API)")
    print("=" * 64)

    all_results = []

    for i, task in enumerate(bc.TASKS):
        print(f"\n{'─' * 50}")
        print(f"[{i+1}/{len(bc.TASKS)}] {task.name} ({task.category})")
        print(f"  URL: {task.url}")

        baseline = await bc.run_task(task, build_baseline, label="baseline")
        all_results.append(baseline)
        await asyncio.sleep(2)

        vision = await bc.run_task(task, build_vision, label="vision")
        all_results.append(vision)
        await asyncio.sleep(2)

    # ────────────────────────────────────────
    # Output
    # ────────────────────────────────────────
    print("\n" + "=" * 64)
    print("📊 BENCHMARK RESULTS")
    print("=" * 64)

    print(f"\n{'Task':<25} {'Category':<12} {'Baseline':<15} {'Vision':<15} {'Δ Steps'}")
    print("─" * 80)

    baseline_wins = vision_wins = ties = 0

    for i in range(0, len(all_results), 2):
        b = all_results[i]
        v = all_results[i + 1]

        b_str = f"{'✅' if b.success else '❌'} {b.steps}st/{b.time_seconds}s"
        v_str = f"{'✅' if v.success else '❌'} {v.steps}st/{v.time_seconds}s"

        if v.success and not b.success:
            delta = "Vision ✨"
            vision_wins += 1
        elif b.success and not v.success:
            delta = "Baseline"
            baseline_wins += 1
        elif v.success and b.success:
            delta = f"{b.steps - v.steps:+d} steps"
            if v.steps < b.steps:
                vision_wins += 1
            elif b.steps < v.steps:
                baseline_wins += 1
            else:
                ties += 1
        else:
            delta = "Both fail"
            ties += 1

        print(f"{b.task_name:<25} {b.category:<12} {b_str:<15} {v_str:<15} {delta}")

    b_total = sum(1 for r in all_results if r.label == "baseline" and r.success)
    v_total = sum(1 for r in all_results if r.label == "vision" and r.success)
    v_calls = sum(r.vision_calls for r in all_results if r.label == "vision")
    v_skips = sum(1 for r in all_results if r.label == "vision" and r.vision_calls == 0 and r.success)

    print(f"\n{'─' * 80}")
    print(f"Success rate:  Baseline {b_total}/{len(bc.TASKS)}  |  Vision {v_total}/{len(bc.TASKS)}")
    print(f"Vision calls:  {v_calls} total  |  {v_skips} tasks with 0 calls (adaptive skip)")
    print(f"Advantage:     Vision wins {vision_wins} | Baseline wins {baseline_wins} | Ties {ties}")
    print("=" * 64)

    output_dir = ROOT / "output" / "benchmark_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    results_json = output_dir / "real_world_results.json"
    with open(results_json, "w") as f:
        json.dump([asdict(r) for r in all_results], f, indent=2, ensure_ascii=False)
    print(f"\n💾 Results saved: {results_json}")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("browser_use.telemetry").setLevel(logging.WARNING)

    asyncio.run(main())
