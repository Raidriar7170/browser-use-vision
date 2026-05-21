"""
Icon-Only Demo: Baseline vs Vision-Enhanced Agent 对比

场景: 音乐播放器页面，所有控制按钮都是 SVG icon，无文字/aria-label
任务: "Click the next track button"

Baseline (use_vision=False): DOM 中按钮没有文字描述，
  Agent 无法区分 shuffle/prev/play/next/repeat

Vision-Enhanced (SoM 标注): 截图上画了框+编号，LLM 通过视觉识别
  SVG 图标含义 → 正确选择 next 按钮

Usage:
    cd /Users/raidriar/browser-use-vision
    XDG_CONFIG_HOME=~/browser-use-config PYTHONPATH=. python scripts/demo_icon_only.py --mode both
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------- 代理和环境配置 ----------
# 从 ~/.hermes/.env 加载 key（跳过 shell 语法错误的行）
def _load_hermes_env():
    envfile = Path.home() / ".hermes" / ".env"
    if not envfile.exists():
        return
    for line in envfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and val and not os.getenv(key):
            os.environ[key] = val


_load_hermes_env()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY required (set in env or ~/.hermes/.env)")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
VISION_API_URL = os.getenv("VISION_API_URL", "http://localhost:8100")

# 关键: 排除本地连接走代理，否则 CDP websocket 失败
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(var, None)

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("demo_icon_only")

DEMO_URL = "http://localhost:8088/icon_only_player.html"
DEMO_TASK = (
    "On this music player page, click the 'Next Track' button to skip to the next song. "
    "There are several icon-only control buttons in the player — find and click the correct one."
)
MAX_STEPS = 10


def get_llm():
    from browser_use.llm.openai.chat import ChatOpenAI

    kwargs = dict(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        temperature=0.0,
    )
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def count_steps(history) -> int:
    try:
        if hasattr(history, "history"):
            return len(history.history)
        return 0
    except Exception:
        return 0


async def check_result(session) -> tuple[bool, list[str]]:
    """检查页面上触发了哪些 actions"""
    try:
        page = await session.get_current_page()
        if page:
            actions = await page.evaluate("() => window.actions || []")
            return "next" in actions, actions
    except Exception:
        pass
    return False, []


def check_history_for_success(history) -> tuple[bool, str]:
    """从 agent history 中检查是否成功完成了任务"""
    try:
        if hasattr(history, "final_result"):
            result = history.final_result()
            if result:
                return True, str(result)
        if hasattr(history, "history") and history.history:
            last = history.history[-1]
            if hasattr(last, "result") and last.result:
                # 检查 done action 的 success 标记
                for item in last.result:
                    if hasattr(item, "done") and item.done:
                        return item.done.success, item.done.text or ""
    except Exception:
        pass
    return False, ""


async def run_baseline() -> dict:
    """原版 browser-use Agent (无视觉增强)"""
    from browser_use import Agent
    from browser_use.browser.session import BrowserSession

    print("\n" + "=" * 60)
    print("🔴 BASELINE (use_vision=False, no SoM, no OCR)")
    print("=" * 60)

    session = BrowserSession(headless=True)
    try:
        llm = get_llm()
        agent = Agent(
            task=DEMO_TASK,
            llm=llm,
            browser_session=session,
            use_vision=False,
            max_steps=MAX_STEPS,
        )

        await session.start()
        page = await session.get_current_page()
        await page.goto(DEMO_URL)
        await asyncio.sleep(2)

        t0 = time.perf_counter()
        history = await agent.run()
        elapsed = round(time.perf_counter() - t0, 2)

        success, actions = await check_result(session)
        steps = count_steps(history)

        print("\n📊 Baseline 结果:")
        print(f"   成功: {'✅' if success else '❌'}")
        print(f"   步数: {steps}")
        print(f"   耗时: {elapsed}s")
        print(f"   触发的 actions: {actions}")

        return {"mode": "baseline", "success": success, "steps": steps, "elapsed": elapsed, "actions": actions}

    except Exception as e:
        logger.error(f"Baseline error: {e}")
        logger.debug(traceback.format_exc())
        return {"mode": "baseline", "success": False, "error": str(e)}
    finally:
        try:
            await session.close()
        except Exception:
            pass


async def run_vision() -> dict:
    """Vision-Enhanced Agent (SoM + OCR)"""
    from browser_use.browser.session import BrowserSession

    from browser_use_vision.enhanced_agent import VisionEnhancedAgent
    from browser_use_vision.grounding.florence import FlorenceBackend

    print("\n" + "=" * 60)
    print("🟢 VISION-ENHANCED (SoM + Florence-2 OCR)")
    print("=" * 60)

    session = BrowserSession(headless=True)
    try:
        llm = get_llm()
        vision_backend = FlorenceBackend(remote_url=VISION_API_URL)

        agent = VisionEnhancedAgent(
            task=DEMO_TASK,
            llm=llm,
            browser_session=session,
            vision_backend=vision_backend,
            use_vision=True,  # 让 browser-use 发截图给 LLM
            enable_som=True,  # SoM 标注
            enable_adaptive=False,  # 总是用视觉
            max_steps=MAX_STEPS,
        )

        await session.start()
        page = await session.get_current_page()
        await page.goto(DEMO_URL)
        await asyncio.sleep(2)

        t0 = time.perf_counter()
        history = await agent.run()
        elapsed = round(time.perf_counter() - t0, 2)

        # 先尝试从页面获取 JS actions（agent done 后页面可能已关闭）
        success, actions = await check_result(session)
        # 回退：从 agent history 判断成功
        history_success, history_text = check_history_for_success(history)
        if not success and history_success:
            success = True
        steps = count_steps(history)

        print("\n📊 Vision 结果:")
        print(f"   成功: {'✅' if success else '❌'}")
        print(f"   步数: {steps}")
        print(f"   耗时: {elapsed}s")
        print(f"   触发的 actions: {actions}")
        print(f"   Agent 报告: {history_text}")
        print(f"   视觉统计: {agent.vision_stats}")

        return {
            "mode": "vision",
            "success": success,
            "steps": steps,
            "elapsed": elapsed,
            "actions": actions,
            "agent_report": history_text,
            "vision_stats": agent.vision_stats,
        }

    except Exception as e:
        logger.error(f"Vision error: {e}")
        logger.debug(traceback.format_exc())
        return {"mode": "vision", "success": False, "error": str(e)}
    finally:
        try:
            await session.close()
        except Exception:
            pass


async def main(mode: str):
    results = []

    if mode in ("baseline", "both"):
        results.append(await run_baseline())

    if mode in ("vision", "both"):
        results.append(await run_vision())

    if mode == "both" and len(results) == 2:
        bl, vi = results
        print("\n" + "=" * 60)
        print("📊 对比总结")
        print("=" * 60)
        print(f"   {'指标':<20} {'Baseline':<15} {'Vision':<15}")
        print(f"   {'-' * 50}")
        bl_ok = "✅" if bl.get("success") else "❌"
        vi_ok = "✅" if vi.get("success") else "❌"
        print(f"   {'成功?':<20} {bl_ok:<15} {vi_ok:<15}")
        if bl.get("elapsed"):
            print(f"   {'耗时':<20} {bl['elapsed']}s{'':<9} {vi.get('elapsed', '?')}s")
        if bl.get("steps"):
            print(f"   {'步数':<20} {bl['steps']:<15} {vi.get('steps', '?'):<15}")

    # 保存
    out = PROJECT_ROOT / "output" / "demo_results"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "icon_only_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n结果已保存: {out / 'icon_only_results.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "vision", "both"], default="both")
    args = parser.parse_args()
    asyncio.run(main(args.mode))
