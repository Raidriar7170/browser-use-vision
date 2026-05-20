"""
Browser-Use Vision Enhancement — GPT-4o 集成测试 (本机运行)

运行:
    cd /Users/raidriar/browser-use-vision
    XDG_CONFIG_HOME=~/browser-use-config PYTHONPATH=. /opt/anaconda3/bin/python3 scripts/demo_gpt4o.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------- 配置 ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required. Set it before running.")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
VISION_API_URL = os.getenv("VISION_API_URL", "http://localhost:8100")
PROXY_URL = os.getenv("HTTPS_PROXY", "http://127.0.0.1:1097")
MAX_STEPS = 15

# 关键：排除本地连接走代理，否则 CDP websocket 会失败
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"
# 不设全局 HTTP(S)_PROXY，只在 OpenAI client 里用代理
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
            "ALL_PROXY", "all_proxy"]:
    os.environ.pop(var, None)

import httpx
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("demo_gpt4o")


@dataclass
class ScenarioResult:
    scenario_name: str
    agent_type: str
    success: bool
    error_message: str = ""
    elapsed_seconds: float = 0.0
    steps_taken: int = 0
    final_result: str = ""


@dataclass
class TestScenario:
    name: str
    task: str
    description: str


SCENARIOS = [
    TestScenario(
        name="extract_title",
        task=(
            "Go to https://example.com and extract the main heading text (the <h1>). "
            "Return ONLY the heading text as your final answer."
        ),
        description="提取 example.com 的标题（简单任务）",
    ),
    TestScenario(
        name="wikipedia_info",
        task=(
            "Go to https://en.wikipedia.org/wiki/Python_(programming_language) "
            "and find when Python was first released (the year). "
            "Return ONLY the year as your final answer."
        ),
        description="从 Wikipedia 提取 Python 首次发布年份（中等难度）",
    ),
]


def get_llm():
    """创建 browser-use 原生的 ChatOpenAI，带代理"""
    from browser_use.llm.openai.chat import ChatOpenAI

    # 创建带代理的 httpx client
    proxy_client = httpx.AsyncClient(
        proxy=PROXY_URL,
        timeout=httpx.Timeout(60.0),
    )

    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        temperature=0.0,
        http_client=proxy_client,
    )


def extract_final_result(history) -> str:
    try:
        if hasattr(history, "final_result"):
            result = history.final_result()
            if result:
                return str(result)[:500]
        if hasattr(history, "history") and history.history:
            last = history.history[-1]
            if hasattr(last, "result") and last.result:
                return str(last.result)[:500]
        return str(history)[:500]
    except Exception:
        return "<unable to extract>"


def count_steps(history) -> int:
    try:
        if hasattr(history, "history"):
            return len(history.history)
        return 0
    except Exception:
        return 0


async def run_baseline(scenario: TestScenario) -> ScenarioResult:
    """原版 browser-use Agent + GPT-4o-mini"""
    from browser_use import Agent
    from browser_use.browser.session import BrowserSession

    result = ScenarioResult(
        scenario_name=scenario.name, agent_type="baseline", success=False
    )

    browser = BrowserSession(headless=True)
    try:
        llm = get_llm()

        agent = Agent(
            task=scenario.task,
            llm=llm,
            browser_session=browser,
            use_vision=False,
        )

        t0 = time.perf_counter()
        history = await agent.run(max_steps=MAX_STEPS)
        result.elapsed_seconds = round(time.perf_counter() - t0, 3)
        result.steps_taken = count_steps(history)
        result.final_result = extract_final_result(history)
        result.success = True

    except Exception as e:
        result.error_message = f"{type(e).__name__}: {e}"
        logger.error(f"Baseline failed: {result.error_message}")
        logger.debug(traceback.format_exc())
    finally:
        try:
            await browser.close()
        except Exception:
            pass

    return result


async def run_vision_enhanced(scenario: TestScenario) -> ScenarioResult:
    """VisionEnhancedAgent + GPT-4o-mini + Florence-2"""
    from browser_use.browser.session import BrowserSession

    from browser_use_vision.enhanced_agent import VisionEnhancedAgent
    from browser_use_vision.grounding.florence import FlorenceBackend

    result = ScenarioResult(
        scenario_name=scenario.name, agent_type="vision_enhanced", success=False
    )

    browser = BrowserSession(headless=True)
    try:
        llm = get_llm()
        vision_backend = FlorenceBackend(remote_url=VISION_API_URL)

        agent = VisionEnhancedAgent(
            task=scenario.task,
            llm=llm,
            browser_session=browser,
            vision_backend=vision_backend,
            use_vision=False,
        )

        t0 = time.perf_counter()
        history = await agent.run(max_steps=MAX_STEPS)
        result.elapsed_seconds = round(time.perf_counter() - t0, 3)
        result.steps_taken = count_steps(history)
        result.final_result = extract_final_result(history)
        result.success = True

    except Exception as e:
        result.error_message = f"{type(e).__name__}: {e}"
        logger.error(f"VisionEnhanced failed: {result.error_message}")
        logger.debug(traceback.format_exc())
    finally:
        try:
            await browser.close()
        except Exception:
            pass

    return result


def print_results(results: list[ScenarioResult]):
    sep = "+" + "-" * 20 + "+" + "-" * 18 + "+" + "-" * 9 + "+" + "-" * 12 + "+" + "-" * 7 + "+"
    header = f"|{'Scenario':^20}|{'Agent':^18}|{'Success':^9}|{'Time (s)':^12}|{'Steps':^7}|"

    print(f"\n{'=' * 70}")
    print("  GPT-4o Integration Test — Results")
    print(f"{'=' * 70}")
    print(sep)
    print(header)
    print(sep)

    for r in results:
        status = "✅" if r.success else "❌"
        t = f"{r.elapsed_seconds:.1f}" if r.success else "N/A"
        s = str(r.steps_taken) if r.success else "N/A"
        print(f"|{r.scenario_name:^20}|{r.agent_type:^18}|{status:^9}|{t:^12}|{s:^7}|")
    print(sep)

    # 结果详情
    print("\n  📋 结果详情:")
    for r in results:
        icon = "✅" if r.success else "❌"
        print(f"\n    {icon} {r.scenario_name} ({r.agent_type})")
        if r.success:
            print(f"       结果: {r.final_result[:200]}")
        else:
            print(f"       错误: {r.error_message[:200]}")
    print()


async def main():
    print(f"\n{'═' * 70}")
    print("  Browser-Use Vision — GPT-4o Integration Test")
    print(f"  Model : {OPENAI_MODEL}")
    print(f"  Vision: {VISION_API_URL}")
    print(f"  Proxy : {PROXY_URL}")
    print(f"{'═' * 70}")

    all_results: list[ScenarioResult] = []

    for idx, scenario in enumerate(SCENARIOS, 1):
        print(f"\n{'─' * 70}")
        print(f"  [{idx}/{len(SCENARIOS)}] {scenario.name}")
        print(f"  {scenario.description}")
        print(f"{'─' * 70}")

        # Baseline
        print(f"\n  ▶ Running baseline Agent (GPT-4o-mini) ...")
        bl = await run_baseline(scenario)
        all_results.append(bl)
        if bl.success:
            print(f"    ✅ {bl.elapsed_seconds:.1f}s, {bl.steps_taken} steps")
            print(f"    Result: {bl.final_result[:120]}")
        else:
            print(f"    ❌ {bl.error_message[:200]}")

        # VisionEnhanced
        print(f"\n  ▶ Running VisionEnhancedAgent (GPT-4o-mini + Florence-2) ...")
        ve = await run_vision_enhanced(scenario)
        all_results.append(ve)
        if ve.success:
            print(f"    ✅ {ve.elapsed_seconds:.1f}s, {ve.steps_taken} steps")
            print(f"    Result: {ve.final_result[:120]}")
        else:
            print(f"    ❌ {ve.error_message[:200]}")

    print_results(all_results)

    # 总结
    passed = sum(1 for r in all_results if r.success)
    total = len(all_results)
    print(f"  {'🎉' if passed == total else '⚠️'}  总计: {passed}/{total} 通过")

    if passed == total:
        print("  ✅ Agent 集成测试全部通过！VisionEnhancedAgent + GPT-4o-mini 工作正常")
    print()


if __name__ == "__main__":
    asyncio.run(main())
