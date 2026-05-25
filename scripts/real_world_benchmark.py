"""
Browser-Use Vision Enhancement — Real-World Benchmark

在真实公开网站上对比 baseline (纯 DOM) vs vision-enhanced Agent。
每个任务跑两次: baseline + vision，记录步数、耗时、成功/失败。

任务设计原则:
1. 公开稳定的网站，不需要登录
2. 明确的成功判定条件
3. 覆盖不同视觉复杂度

用法:
  # 跑前先关 macOS SOCKS 代理:
  # networksetup -setsocksfirewallproxystate "Wi-Fi" off

  PYTHONUNBUFFERED=1 XDG_CONFIG_HOME=~/browser-use-config \
  PYTHONPATH=. python scripts/real_world_benchmark.py

  # 跑完恢复:
  # networksetup -setsocksfirewallproxystate "Wi-Fi" on
"""

import asyncio
import json
import os
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载 key
env_file = Path.home() / ".hermes" / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

# 代理策略: 保留 HTTP(S)_PROXY 给 LLM API 用，NO_PROXY 排除 CDP localhost
# 这样 LLM API 走代理（稳定），CDP 连接不走代理（不干扰）
for var in ["ALL_PROXY", "all_proxy", "SOCKS_PROXY", "socks_proxy"]:
    os.environ.pop(var, None)
os.environ["HTTP_PROXY"] = "http://127.0.0.1:1097"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1097"
os.environ["http_proxy"] = "http://127.0.0.1:1097"
os.environ["https_proxy"] = "http://127.0.0.1:1097"
os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"
os.environ["no_proxy"] = "localhost,127.0.0.1,0.0.0.0"
urllib.request.getproxies = lambda: {}


# ────────────────────────────────────────────
# 任务定义
# ────────────────────────────────────────────

@dataclass
class BenchmarkTask:
    name: str
    url: str
    task: str
    category: str  # icon-heavy / mixed / dom-rich
    success_keywords: list[str] = field(default_factory=list)
    max_steps: int = 8


TASKS = [
    # ── 视觉密集型 (icon-heavy): DOM 信息不足，需要视觉 ──
    BenchmarkTask(
        name="icon_music_player",
        url="http://localhost:8088/icon_only_player.html",
        task="Click the 'Next Track' button on this music player. The buttons are icon-only with no text labels. After clicking, call done.",
        category="icon-heavy",
        success_keywords=["next", "track", "click", "success"],
    ),
    BenchmarkTask(
        name="color_picker",
        url="http://localhost:8088/color_picker.html",
        task="Click the green color swatch to select it, then click the 'Apply Theme' button. After clicking, call done.",
        category="icon-heavy",
        success_keywords=["green", "apply", "click", "success"],
    ),
    BenchmarkTask(
        name="toolbar_eraser",
        url="http://localhost:8088/toolbar_app.html",
        task="Click the eraser tool in the drawing toolbar. The tools are icon-only SVG buttons with no text labels. After clicking, call done and report which tool you selected.",
        category="icon-heavy",
        success_keywords=["eraser", "selected", "success"],
    ),
    BenchmarkTask(
        name="social_feed_like",
        url="http://localhost:8088/social_feed.html",
        task="Click the heart/like button on the first post (by photographer_jane). The action buttons are icon-only. After clicking, call done.",
        category="icon-heavy",
        success_keywords=["like", "heart", "click", "success"],
    ),

    # ── 混合型 (mixed): 有文字也有图标 ──
    BenchmarkTask(
        name="dashboard_settings",
        url="http://localhost:8088/dashboard.html",
        task="Click the settings icon button in the top-right header area of the dashboard. After clicking, call done and report what happened.",
        category="mixed",
        success_keywords=["settings", "action", "click", "success"],
    ),
    BenchmarkTask(
        name="ecommerce_filter_color",
        url="http://localhost:8088/ecommerce.html",
        task="In the sneaker store, click the blue color swatch in the Color filter section on the left sidebar. After selecting, call done.",
        category="mixed",
        success_keywords=["blue", "color", "select", "success"],
    ),
    BenchmarkTask(
        name="wikipedia_toc_nav",
        url="https://en.wikipedia.org/wiki/Artificial_intelligence",
        task="Click on the 'Machine learning' link in the table of contents to navigate to that section. After clicking, call done.",
        category="mixed",
        success_keywords=["machine learning", "click", "section", "success"],
    ),
    BenchmarkTask(
        name="hackernews_top_story",
        url="https://news.ycombinator.com/",
        task="Find the top (first) story on Hacker News and report its title. Call done with the title.",
        category="mixed",
        success_keywords=["success"],
    ),

    # ── DOM 规范型 (dom-rich): DOM 信息充分 ──
    BenchmarkTask(
        name="github_trending",
        url="https://github.com/trending",
        task="Look at the GitHub Trending page and extract the names and descriptions of the top 3 trending repositories today. Call done with your findings.",
        category="dom-rich",
        success_keywords=["success"],
    ),
    BenchmarkTask(
        name="arxiv_search",
        url="https://arxiv.org/",
        task="Type 'vision language model' in the search box on arxiv.org and submit the search. After the search results appear, report the title of the first result. Call done with your findings.",
        category="dom-rich",
        success_keywords=["success"],
    ),
    BenchmarkTask(
        name="ecommerce_add_cart",
        url="http://localhost:8088/ecommerce.html",
        task="Add the 'Urban Glide X' sneaker to the cart by clicking its 'Add to Cart' button. After clicking, call done.",
        category="dom-rich",
        success_keywords=["cart", "urban", "glide", "success"],
    ),
    BenchmarkTask(
        name="dashboard_chart_tab",
        url="http://localhost:8088/dashboard.html",
        task="Switch the chart view to 'Monthly' by clicking the Monthly tab in the Revenue Overview section. After clicking, call done.",
        category="dom-rich",
        success_keywords=["monthly", "switch", "success"],
    ),
]


# ────────────────────────────────────────────
# 运行引擎
# ────────────────────────────────────────────

@dataclass
class TaskResult:
    task_name: str
    category: str
    mode: str  # "baseline" or "vision"
    success: bool
    steps: int
    time_seconds: float
    final_result: str
    vision_calls: int = 0
    error: str = ""


async def run_task(task: BenchmarkTask, use_vision: bool) -> TaskResult:
    """运行单个任务"""
    from browser_use.browser.session import BrowserSession
    from browser_use.llm.openai.chat import ChatOpenAI

    LLM_BASE = os.environ.get("OPENAI_BASE_URL", "https://llm-gateway.mlamp.cn/v1")
    LLM_KEY = os.environ.get("OPENAI_API_KEY", "")
    VISION_API = "http://localhost:8100"

    mode = "vision" if use_vision else "baseline"
    print(f"\n  {'🔍' if use_vision else '📄'} [{mode}] {task.name}...", end=" ", flush=True)

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=LLM_KEY, base_url=LLM_BASE, temperature=0.0)
    session = BrowserSession(headless=True)

    start_time = time.time()
    result_text = ""
    steps = 0
    vision_calls = 0
    error_msg = ""
    success = False

    try:
        if use_vision:
            from browser_use_vision.enhanced_agent import VisionEnhancedAgent
            from browser_use_vision.grounding.florence import FlorenceBackend

            backend = FlorenceBackend(remote_url=VISION_API)
            agent = VisionEnhancedAgent(
                task=task.task,
                llm=llm,
                browser_session=session,
                vision_backend=backend,
                use_vision=True,
                enable_som=True,
                enable_adaptive=True,
                max_steps=task.max_steps,
            )
        else:
            from browser_use.agent.service import Agent
            agent = Agent(
                task=task.task,
                llm=llm,
                browser_session=session,
                use_vision=False,
                max_steps=task.max_steps,
            )

        # 先启动浏览器并导航到目标页面
        await session.start()
        page = await session.get_current_page()
        await page.goto(task.url)
        await asyncio.sleep(3)  # 等页面加载稳定

        # 加硬超时保护（120秒），防止 Agent 无限循环
        history = await asyncio.wait_for(agent.run(), timeout=120)
        result_text = history.final_result() or ""
        steps = history.number_of_steps()

        # 获取 vision 统计
        if use_vision and hasattr(agent, "vision_stats"):
            vision_calls = agent.vision_stats.get("total_vision_calls", 0)

        # 判断成功: Agent 自己报告成功 + 没有超过 max_steps
        success = history.is_done() and steps < task.max_steps

    except asyncio.TimeoutError:
        error_msg = "Timeout (120s)"
    except Exception as e:
        error_msg = str(e)[:200]

    elapsed = time.time() - start_time

    try:
        await session.close()
    except Exception:
        pass

    status = "✅" if success else "❌"
    print(f"{status} {steps} steps, {elapsed:.1f}s", flush=True)

    return TaskResult(
        task_name=task.name,
        category=task.category,
        mode=mode,
        success=success,
        steps=steps,
        time_seconds=round(elapsed, 1),
        final_result=result_text[:500],
        vision_calls=vision_calls,
        error=error_msg,
    )


async def main():
    print("=" * 64)
    print("🔬 Real-World Benchmark: Baseline vs Vision-Enhanced")
    print("=" * 64)
    print(f"Tasks: {len(TASKS)} | Mode: baseline + vision per task")
    print(f"LLM: gpt-4o-mini | Vision: Florence-2 (localhost:8100)")
    print("=" * 64)

    all_results: list[TaskResult] = []

    for i, task in enumerate(TASKS):
        print(f"\n{'─' * 50}")
        print(f"[{i+1}/{len(TASKS)}] {task.name} ({task.category})")
        print(f"  URL: {task.url}")

        # 先跑 baseline
        baseline = await run_task(task, use_vision=False)
        all_results.append(baseline)

        await asyncio.sleep(2)  # 间隔避免 rate limit

        # 再跑 vision
        vision = await run_task(task, use_vision=True)
        all_results.append(vision)

        await asyncio.sleep(2)

    # ────────────────────────────────────────
    # 输出结果
    # ────────────────────────────────────────
    print("\n" + "=" * 64)
    print("📊 BENCHMARK RESULTS")
    print("=" * 64)

    print(f"\n{'Task':<25} {'Category':<12} {'Baseline':<15} {'Vision':<15} {'Δ Steps'}")
    print("─" * 80)

    baseline_wins = 0
    vision_wins = 0
    ties = 0

    for i in range(0, len(all_results), 2):
        b = all_results[i]      # baseline
        v = all_results[i + 1]  # vision

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

    # 汇总
    b_total = sum(1 for r in all_results if r.mode == "baseline" and r.success)
    v_total = sum(1 for r in all_results if r.mode == "vision" and r.success)
    v_calls = sum(r.vision_calls for r in all_results if r.mode == "vision")
    v_skips = sum(1 for r in all_results if r.mode == "vision" and r.vision_calls == 0 and r.success)

    print(f"\n{'─' * 80}")
    print(f"Success rate:  Baseline {b_total}/{len(TASKS)}  |  Vision {v_total}/{len(TASKS)}")
    print(f"Vision calls:  {v_calls} total  |  {v_skips} tasks with 0 calls (adaptive skip)")
    print(f"Advantage:     Vision wins {vision_wins} | Baseline wins {baseline_wins} | Ties {ties}")
    print("=" * 64)

    # 保存结果
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
