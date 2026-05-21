"""
Browser-Use Vision Enhancement — 交互式 Demo

用法:
    cd /Users/raidriar/browser-use-vision
    export OPENAI_API_KEY="sk-..."
    XDG_CONFIG_HOME=~/browser-use-config PYTHONPATH=. /opt/anaconda3/bin/python3 scripts/interactive_demo.py

会弹出浏览器窗口，你可以实时看到 Agent 操作页面。
输入任务后 Agent 自动执行，完成后继续输入下一个任务。

选项:
    --baseline    使用原版 Agent (不带视觉增强)
    --vision      使用 VisionEnhancedAgent (带 Florence-2)
    --both        两种都跑，对比结果 (默认)
    --model MODEL 指定模型 (默认 gpt-4o-mini)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------- 代理配置 ----------
PROXY_URL = os.getenv("HTTPS_PROXY", "http://127.0.0.1:1097")
# 排除本地连接走代理
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(var, None)

import logging

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# 降低噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("browser_use").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)

logger = logging.getLogger("interactive_demo")


def get_llm(model: str):
    from browser_use.llm.openai.chat import ChatOpenAI

    proxy_client = httpx.AsyncClient(
        proxy=PROXY_URL,
        timeout=httpx.Timeout(60.0),
    )
    return ChatOpenAI(
        model=model,
        api_key=os.environ["OPENAI_API_KEY"],
        temperature=0.0,
        http_client=proxy_client,
    )


async def run_agent(task: str, mode: str, model: str, max_steps: int = 20):
    """运行 Agent 并返回结果"""
    from browser_use import Agent
    from browser_use.browser.session import BrowserSession

    # headless=False 让你看到浏览器窗口
    browser = BrowserSession(headless=False)
    llm = get_llm(model)

    try:
        if mode == "vision":
            from browser_use_vision.enhanced_agent import VisionEnhancedAgent
            from browser_use_vision.grounding.florence import FlorenceBackend

            vision_url = os.getenv("VISION_API_URL", "http://localhost:8100")
            backend = FlorenceBackend(remote_url=vision_url)

            agent = VisionEnhancedAgent(
                task=task,
                llm=llm,
                browser_session=browser,
                vision_backend=backend,
                use_vision=False,
            )
            agent_label = f"VisionEnhanced ({model} + Florence-2)"
        else:
            agent = Agent(
                task=task,
                llm=llm,
                browser_session=browser,
                use_vision=False,
            )
            agent_label = f"Baseline ({model})"

        print(f"\n  🚀 启动 {agent_label}")
        print(f"  📋 任务: {task}")
        print("  👀 浏览器窗口已打开，观察 Agent 操作...\n")

        t0 = time.perf_counter()
        history = await agent.run(max_steps=max_steps)
        elapsed = time.perf_counter() - t0

        # 提取结果
        steps = len(history.history) if hasattr(history, "history") else 0
        result = ""
        try:
            if hasattr(history, "final_result"):
                result = str(history.final_result())[:500]
            elif hasattr(history, "history") and history.history:
                last = history.history[-1]
                if hasattr(last, "result") and last.result:
                    result = str(last.result)[:500]
        except Exception:
            result = "<无法提取>"

        # Vision 统计
        vision_stats = None
        if mode == "vision" and hasattr(agent, "vision_stats"):
            vision_stats = agent.vision_stats

        print(f"\n  {'─' * 56}")
        print(f"  ✅ {agent_label} 完成!")
        print(f"  ⏱  耗时: {elapsed:.1f}s")
        print(f"  🦶 步数: {steps}")
        print(f"  📝 结果: {result[:200]}")
        if vision_stats:
            adaptive = vision_stats.get("adaptive_stats", {})
            print(f"  👁  视觉调用: {adaptive.get('vision_calls', 0)} 次")
            print(f"  ⏭  视觉跳过: {adaptive.get('skip_calls', 0)} 次")
            print(f"  💰 节省比例: {adaptive.get('savings_ratio', 0):.0%}")
        print(f"  {'─' * 56}")

        return {
            "mode": mode,
            "elapsed": elapsed,
            "steps": steps,
            "result": result,
            "vision_stats": vision_stats,
        }

    except Exception as e:
        print(f"\n  ❌ {mode} 失败: {e}")
        return {"mode": mode, "error": str(e)}
    finally:
        # 让用户看一下最终页面状态
        print("\n  ⏸  按 Enter 关闭浏览器...")
        try:
            await asyncio.get_event_loop().run_in_executor(None, input)
        except EOFError:
            pass
        try:
            await browser.close()
        except Exception:
            pass


def print_comparison(results: list[dict]):
    """打印对比结果"""
    if len(results) < 2:
        return

    bl = next((r for r in results if r["mode"] == "baseline"), None)
    ve = next((r for r in results if r["mode"] == "vision"), None)
    if not bl or not ve or "error" in bl or "error" in ve:
        return

    print(f"\n  {'═' * 56}")
    print("  📊 对比结果")
    print(f"  {'═' * 56}")
    print(f"  {'指标':<14} {'Baseline':<18} {'Vision Enhanced':<18}")
    print(f"  {'─' * 56}")
    print(f"  {'耗时':<14} {bl['elapsed']:.1f}s{'':<13} {ve['elapsed']:.1f}s")
    print(f"  {'步数':<14} {bl['steps']:<18} {ve['steps']:<18}")

    if ve["steps"] < bl["steps"]:
        pct = (bl["steps"] - ve["steps"]) / bl["steps"] * 100
        print(f"\n  ✅ Vision Enhanced 步数减少 {pct:.0f}%")
    elif ve["steps"] > bl["steps"]:
        print("\n  ⚠️  Vision Enhanced 步数更多")

    if ve.get("vision_stats"):
        adaptive = ve["vision_stats"].get("adaptive_stats", {})
        savings = adaptive.get("savings_ratio", 0)
        print(f"  💡 自适应策略跳过了 {savings:.0%} 的视觉调用")

    print(f"  {'═' * 56}")


EXAMPLE_TASKS = [
    "Go to https://example.com and extract the main heading",
    "Go to https://en.wikipedia.org/wiki/Python_(programming_language) and find the year Python was first released",
    "Go to https://news.ycombinator.com and find the title of the top post",
    "Go to https://github.com/browser-use/browser-use and find the number of stars",
]


async def main():
    parser = argparse.ArgumentParser(description="Browser-Use Vision 交互式 Demo")
    parser.add_argument("--baseline", action="store_true", help="仅运行 Baseline")
    parser.add_argument("--vision", action="store_true", help="仅运行 VisionEnhanced")
    parser.add_argument("--both", action="store_true", help="两种都跑（默认）")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI 模型")
    parser.add_argument("--max-steps", type=int, default=20, help="最大步数")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("\n  ❌ 请先设置 OPENAI_API_KEY:")
        print("     export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    # 默认 both
    if not args.baseline and not args.vision:
        args.both = True

    modes = []
    if args.both:
        modes = ["baseline", "vision"]
    elif args.baseline:
        modes = ["baseline"]
    elif args.vision:
        modes = ["vision"]

    print(f"""
╔══════════════════════════════════════════════════════════╗
║   Browser-Use Vision Enhancement — 交互式 Demo          ║
╠══════════════════════════════════════════════════════════╣
║  模型: {args.model:<50}║
║  模式: {", ".join(modes):<50}║
║  最大步数: {args.max_steps:<47}║
║                                                          ║
║  浏览器窗口会弹出，你可以实时观看 Agent 操作！           ║
╚══════════════════════════════════════════════════════════╝
""")

    print("  示例任务:")
    for i, t in enumerate(EXAMPLE_TASKS, 1):
        print(f"    {i}. {t}")
    print("    输入 q 退出\n")

    while True:
        try:
            user_input = input("  📝 输入任务 (或编号 1-4): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  👋 再见!")
            break

        if not user_input or user_input.lower() == "q":
            print("  👋 再见!")
            break

        # 支持输入编号
        if user_input.isdigit():
            idx = int(user_input)
            if 1 <= idx <= len(EXAMPLE_TASKS):
                task = EXAMPLE_TASKS[idx - 1]
            else:
                print(f"  ❌ 请输入 1-{len(EXAMPLE_TASKS)}")
                continue
        else:
            task = user_input

        results = []
        for mode in modes:
            r = await run_agent(task, mode, args.model, args.max_steps)
            results.append(r)

        if len(modes) > 1:
            print_comparison(results)

        print()


if __name__ == "__main__":
    asyncio.run(main())
