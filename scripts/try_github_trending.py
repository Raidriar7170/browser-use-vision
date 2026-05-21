"""
真实场景体验: 去 GitHub Trending 搜索 Agent 项目
"""

import asyncio
import os
import sys
import urllib.request
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

# 清除代理
for var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "all_proxy",
            "SOCKS_PROXY", "socks_proxy"]:
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ["ALL_PROXY"] = ""
urllib.request.getproxies = lambda: {}


async def main():
    from browser_use.browser.session import BrowserSession
    from browser_use.llm.openai.chat import ChatOpenAI

    from browser_use_vision.enhanced_agent import VisionEnhancedAgent
    from browser_use_vision.grounding.florence import FlorenceBackend

    VISION_API = "http://localhost:8100"
    LLM_BASE = os.environ.get("OPENAI_BASE_URL", "https://llm-gateway.mlamp.cn/v1")
    LLM_KEY = os.environ.get("OPENAI_API_KEY", "")

    print("=" * 60)
    print("🔍 真实场景: GitHub Trending Agent 项目搜索")
    print("=" * 60)

    llm_kwargs = dict(model="gpt-4o-mini", api_key=LLM_KEY, temperature=0.0)
    if LLM_BASE:
        llm_kwargs["base_url"] = LLM_BASE
    llm = ChatOpenAI(**llm_kwargs)

    backend = FlorenceBackend(remote_url=VISION_API)
    session = BrowserSession(headless=False)

    agent = VisionEnhancedAgent(
        task=(
            "Go to https://github.com/trending and find trending repositories "
            "related to 'agent'. Steps: "
            "1. Navigate to https://github.com/trending "
            "2. Look at the trending list and identify any projects related to AI agents "
            "3. Report back the top 3-5 agent-related trending repos you can see, "
            "   including their name, stars, and description. "
            "Once you have gathered the info, call done with your findings."
        ),
        llm=llm,
        browser_session=session,
        vision_backend=backend,
        use_vision=True,
        enable_som=True,
        enable_adaptive=True,  # 自适应模式: 只在需要时用视觉
        max_steps=10,
    )

    print("🚀 启动浏览器...\n")
    history = await agent.run()

    print()
    print("=" * 60)
    print("📋 Agent 搜索结果:")
    print("=" * 60)
    print(history.final_result())
    print()

    stats = agent.vision_stats
    print(f"📊 视觉增强统计:")
    print(f"   Vision 调用次数: {stats['total_vision_calls']}")
    if stats["enrichments"]:
        for e in stats["enrichments"]:
            print(f"   Step {e['step']}: {e['decision']} — {e['items_detected']} 元素")
    else:
        print("   自适应策略判断 DOM 已足够，未调用视觉模型 ✅")
    print("=" * 60)

    print("\n⏳ 10 秒后关闭浏览器...")
    await asyncio.sleep(10)
    await session.close()
    print("👋 Done!")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
