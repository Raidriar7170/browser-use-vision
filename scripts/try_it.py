"""
一键体验脚本 — 有浏览器界面，可以看到 Agent 操作过程
"""

import asyncio
import os
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载 OpenAI key
env_file = Path.home() / ".hermes" / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

# 清除代理（防止干扰 CDP 连接）
# 必须同时清除环境变量 + 设置 NO_PROXY，因为 macOS 系统级 SOCKS 代理
# 会被 Python 的 urllib/aiohttp 自动读取
for var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "all_proxy",
            "SOCKS_PROXY", "socks_proxy"]:
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# 禁用 Python urllib 自动检测系统代理
import urllib.request
urllib.request.getproxies = lambda: {}

# 也 patch socket 级别，防止 python-socks 检测
os.environ["ALL_PROXY"] = ""


async def main():
    from browser_use.browser.session import BrowserSession
    from browser_use.llm.openai.chat import ChatOpenAI

    from browser_use_vision.enhanced_agent import VisionEnhancedAgent
    from browser_use_vision.grounding.florence import FlorenceBackend

    # ---------- 配置 ----------
    VISION_API = "http://localhost:8100"
    LLM_BASE   = os.environ.get("OPENAI_BASE_URL", "https://llm-gateway.mlamp.cn/v1")
    LLM_KEY    = os.environ.get("OPENAI_API_KEY", "")
    DEMO_URL   = "http://localhost:8088/icon_only_player.html"

    print("=" * 60)
    print("🔍 Browser-Use Vision Enhancement — 体验模式")
    print("=" * 60)
    print(f"  Vision API:  {VISION_API}")
    print(f"  LLM:         gpt-4o-mini via {LLM_BASE}")
    print(f"  Demo URL:    {DEMO_URL}")
    print(f"  Mode:        有界面 (headless=False)")
    print("=" * 60)
    print()

    # ---------- 初始化 ----------
    llm_kwargs = dict(model="gpt-4o-mini", api_key=LLM_KEY, temperature=0.0)
    if LLM_BASE:
        llm_kwargs["base_url"] = LLM_BASE
    llm = ChatOpenAI(**llm_kwargs)
    backend = FlorenceBackend(remote_url=VISION_API)

    # headless=False — 打开真实浏览器窗口
    session = BrowserSession(headless=False)

    agent = VisionEnhancedAgent(
        task="Click the 'Next Track' button on this music player to skip to the next song. "
             "The buttons are icon-only (no text labels). Once clicked, call done.",
        llm=llm,
        browser_session=session,
        vision_backend=backend,
        use_vision=True,
        enable_som=True,
        enable_adaptive=False,
        max_steps=6,
    )

    # ---------- 运行 ----------
    print("🚀 启动浏览器...")
    await session.start()

    page = await session.get_current_page()
    await page.goto(DEMO_URL)
    await asyncio.sleep(2)
    print("📄 页面已加载，Agent 开始操作...\n")

    history = await agent.run()

    # ---------- 结果 ----------
    n_steps = len(history.action_results()) if hasattr(history, "action_results") else "?"
    print()
    print("=" * 60)
    print(f"✅ Agent 完成! 共 {n_steps} 步")
    print(f"   最终结果: {history.final_result()}")
    print()

    # 显示视觉增强统计
    stats = agent.vision_stats
    print(f"📊 视觉增强统计:")
    print(f"   Vision 调用次数: {stats['total_vision_calls']}")
    if stats["enrichments"]:
        for e in stats["enrichments"]:
            print(f"   Step {e['step']}: {e['decision']} — 检测到 {e['items_detected']} 个元素")
    else:
        print("   自适应策略判断 DOM 已足够，未调用视觉模型 ✅")
    print("=" * 60)

    # 等几秒让用户看到结果
    print("\n⏳ 浏览器将在 10 秒后关闭...")
    await asyncio.sleep(10)
    await session.close()
    print("👋 Done!")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    # 减少 httpx 噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
