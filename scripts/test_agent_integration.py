"""
Browser-Use Agent 集成对比测试

对比 baseline Agent（原版 browser-use）与 VisionEnhancedAgent 在多种网页场景下的表现。

前置条件:
  1. LLM API: http://localhost:8200/v1  (模型 "qwen")
  2. Vision API: http://localhost:8100
  3. Playwright chromium 已安装

运行:
    cd /tmp/browser-use-vision-code
    PYTHONPATH=. python3 scripts/test_agent_integration.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8200/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen")
LLM_API_KEY = os.getenv("LLM_API_KEY", "dummy")
VISION_API_URL = os.getenv("VISION_API_URL", "http://localhost:8100")
MAX_STEPS = int(os.getenv("MAX_STEPS", "10"))

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent_integration_test")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class ScenarioResult:
    """单次场景执行的结果"""

    scenario_name: str
    agent_type: str  # "baseline" | "vision_enhanced"
    success: bool
    error_message: str = ""
    elapsed_seconds: float = 0.0
    steps_taken: int = 0
    final_result: str = ""
    vision_stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TestScenario:
    """测试场景定义"""

    name: str
    url: str
    task: str
    description: str
    difficulty: str  # "easy" | "medium" | "hard"


# ---------------------------------------------------------------------------
# 测试场景
# ---------------------------------------------------------------------------
SCENARIOS: list[TestScenario] = [
    TestScenario(
        name="extract_page_title",
        url="https://example.com",
        task=(
            "Go to https://example.com and extract the main page title "
            "(the <h1> heading text). Return it as your final answer."
        ),
        description="打开 example.com，提取页面标题（简单 DOM 操作）",
        difficulty="easy",
    ),
    TestScenario(
        name="fill_form",
        url="https://httpbin.org/forms/post",
        task=(
            "Go to https://httpbin.org/forms/post and fill out the form: "
            "set Customer Name to 'Alice Test', Size to 'Large', "
            "check 'Cheese' topping, then submit the form. "
            "Report whether the submission was successful."
        ),
        description="打开 httpbin 表单页面，填写并提交表单（中等难度）",
        difficulty="medium",
    ),
    TestScenario(
        name="trending_info",
        url="https://github.com/trending",
        task=(
            "Go to https://github.com/trending and find the name and description "
            "of the top trending repository (the first one listed). "
            "Return the repository full name (owner/repo) and its description."
        ),
        description="打开 GitHub Trending，提取第一个仓库信息（复杂页面）",
        difficulty="hard",
    ),
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def create_llm():
    """创建 browser-use 自带的 ChatOpenAI 实例"""
    from browser_use.llm.openai.chat import ChatOpenAI

    return ChatOpenAI(
        base_url=LLM_BASE_URL,
        api_key="dummy",
        model=LLM_MODEL,
        temperature=0.0,
    )


def create_browser():
    """创建 browser-use BrowserSession 实例"""
    from browser_use.browser.session import BrowserSession

    return BrowserSession(headless=True, enable_default_extensions=False)


def create_vision_backend():
    """创建 Florence 远程视觉后端"""
    from browser_use_vision.grounding.florence import FlorenceBackend

    return FlorenceBackend(remote_url=VISION_API_URL)


def extract_final_result(history) -> str:
    """从 AgentHistoryList 中提取最终结果文本"""
    try:
        # AgentHistoryList 的最终结果
        if hasattr(history, "final_result"):
            result = history.final_result()
            if result:
                return str(result)[:500]
        # 回退：取最后一步的输出
        if hasattr(history, "history") and history.history:
            last = history.history[-1]
            if hasattr(last, "result") and last.result:
                return str(last.result)[:500]
        return str(history)[:500]
    except Exception:
        return "<unable to extract>"


def count_steps(history) -> int:
    """从 AgentHistoryList 中计算步骤数"""
    try:
        if hasattr(history, "history"):
            return len(history.history)
        if hasattr(history, "__len__"):
            return len(history)
        return 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 执行引擎
# ---------------------------------------------------------------------------
async def run_baseline(scenario: TestScenario, browser) -> ScenarioResult:
    """使用原版 browser-use Agent 执行场景"""
    from browser_use import Agent

    llm = create_llm()
    result = ScenarioResult(
        scenario_name=scenario.name,
        agent_type="baseline",
        success=False,
    )

    try:
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
        logger.error(f"Baseline failed on '{scenario.name}': {result.error_message}")
        logger.debug(traceback.format_exc())

    return result


async def run_vision_enhanced(scenario: TestScenario, browser) -> ScenarioResult:
    """使用 VisionEnhancedAgent 执行场景"""
    from browser_use_vision.enhanced_agent import VisionEnhancedAgent

    llm = create_llm()
    vision_backend = create_vision_backend()
    result = ScenarioResult(
        scenario_name=scenario.name,
        agent_type="vision_enhanced",
        success=False,
    )

    try:
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

        # 附加视觉增强统计
        if hasattr(agent, "vision_stats"):
            result.vision_stats = agent.vision_stats

    except Exception as e:
        result.error_message = f"{type(e).__name__}: {e}"
        logger.error(f"VisionEnhanced failed on '{scenario.name}': {result.error_message}")
        logger.debug(traceback.format_exc())

    return result


# ---------------------------------------------------------------------------
# 结果输出
# ---------------------------------------------------------------------------
def print_comparison_table(results: list[ScenarioResult]) -> None:
    """将结果以对比表格形式输出到终端"""
    # 按场景分组
    scenarios_seen: list[str] = []
    for r in results:
        if r.scenario_name not in scenarios_seen:
            scenarios_seen.append(r.scenario_name)

    sep = "+" + "-" * 22 + "+" + "-" * 18 + "+" + "-" * 10 + "+" + "-" * 14 + "+" + "-" * 8 + "+"
    header = f"|{'Scenario':^22}|{'Agent':^18}|{'Success':^10}|{'Time (s)':^14}|{'Steps':^8}|"

    print("\n")
    print("=" * 76)
    print("  Agent Integration Test — Comparison Results")
    print("=" * 76)
    print(sep)
    print(header)
    print(sep)

    for sname in scenarios_seen:
        group = [r for r in results if r.scenario_name == sname]
        for r in group:
            status = "OK" if r.success else "FAIL"
            time_str = f"{r.elapsed_seconds:.2f}" if r.success else "N/A"
            steps_str = str(r.steps_taken) if r.success else "N/A"
            print(f"|{sname:^22}|{r.agent_type:^18}|{status:^10}|{time_str:^14}|{steps_str:^8}|")
        print(sep)

    # 汇总
    baseline_results = [r for r in results if r.agent_type == "baseline"]
    vision_results = [r for r in results if r.agent_type == "vision_enhanced"]

    bl_success = sum(1 for r in baseline_results if r.success)
    ve_success = sum(1 for r in vision_results if r.success)
    bl_total = len(baseline_results)
    ve_total = len(vision_results)

    bl_avg_time = sum(r.elapsed_seconds for r in baseline_results if r.success) / max(bl_success, 1)
    ve_avg_time = sum(r.elapsed_seconds for r in vision_results if r.success) / max(ve_success, 1)

    bl_avg_steps = sum(r.steps_taken for r in baseline_results if r.success) / max(bl_success, 1)
    ve_avg_steps = sum(r.steps_taken for r in vision_results if r.success) / max(ve_success, 1)

    print("\n  Summary:")
    print(
        f"    Baseline          : {bl_success}/{bl_total} passed, "
        f"avg time {bl_avg_time:.2f}s, avg steps {bl_avg_steps:.1f}"
    )
    print(
        f"    VisionEnhanced    : {ve_success}/{ve_total} passed, "
        f"avg time {ve_avg_time:.2f}s, avg steps {ve_avg_steps:.1f}"
    )

    # 视觉增强统计汇总
    total_vision_calls = sum(r.vision_stats.get("total_vision_calls", 0) for r in vision_results if r.vision_stats)
    if total_vision_calls > 0:
        print(f"    Total vision API calls: {total_vision_calls}")

    print("=" * 76)
    print()


def save_results(results: list[ScenarioResult], output_dir: Path) -> Path:
    """保存结果到 JSON 文件"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"agent_integration_{timestamp}.json"

    payload = {
        "timestamp": timestamp,
        "config": {
            "llm_base_url": LLM_BASE_URL,
            "llm_model": LLM_MODEL,
            "vision_api_url": VISION_API_URL,
            "max_steps": MAX_STEPS,
        },
        "scenarios": [
            {
                "name": s.name,
                "url": s.url,
                "task": s.task,
                "description": s.description,
                "difficulty": s.difficulty,
            }
            for s in SCENARIOS
        ],
        "results": [r.to_dict() for r in results],
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return output_file


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def main() -> None:
    print("\n" + "=" * 76)
    print("  Browser-Use Agent Integration Test")
    print(f"  LLM : {LLM_BASE_URL}  model={LLM_MODEL}")
    print(f"  Vision API : {VISION_API_URL}")
    print(f"  Max steps  : {MAX_STEPS}")
    print(f"  Scenarios  : {len(SCENARIOS)}")
    print("=" * 76)

    all_results: list[ScenarioResult] = []

    for idx, scenario in enumerate(SCENARIOS, 1):
        print(f"\n{'─' * 76}")
        print(f"  [{idx}/{len(SCENARIOS)}] {scenario.name} ({scenario.difficulty})")
        print(f"  {scenario.description}")
        print(f"  URL : {scenario.url}")
        print(f"{'─' * 76}")

        # 每个场景用独立的 BrowserSession，避免 CDP 断连
        browser = create_browser()
        try:
            # --- Baseline ---
            print("\n  ▶ Running baseline Agent ...")
            bl_result = await run_baseline(scenario, browser)
            all_results.append(bl_result)
            if bl_result.success:
                print(f"    ✅ Done in {bl_result.elapsed_seconds:.2f}s, {bl_result.steps_taken} steps")
                print(f"    Result: {bl_result.final_result[:120]}")
            else:
                print(f"    ❌ Failed: {bl_result.error_message[:200]}")

        finally:
            try:
                await browser.close()
            except Exception:
                pass

        # --- VisionEnhanced --- (独立 session)
        browser2 = create_browser()
        try:
            print("\n  ▶ Running VisionEnhancedAgent ...")
            ve_result = await run_vision_enhanced(scenario, browser2)
            all_results.append(ve_result)
            if ve_result.success:
                print(f"    ✅ Done in {ve_result.elapsed_seconds:.2f}s, {ve_result.steps_taken} steps")
                print(f"    Result: {ve_result.final_result[:120]}")
                if ve_result.vision_stats:
                    vc = ve_result.vision_stats.get("total_vision_calls", 0)
                    print(f"    Vision calls: {vc}")
            else:
                print(f"    ❌ Failed: {ve_result.error_message[:200]}")
        finally:
            try:
                await browser2.close()
            except Exception:
                pass

    # 输出对比表格
    print_comparison_table(all_results)

    # 保存结果
    output_dir = PROJECT_ROOT / "benchmarks" / "results"
    output_file = save_results(all_results, output_dir)
    print(f"  Results saved to: {output_file}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
