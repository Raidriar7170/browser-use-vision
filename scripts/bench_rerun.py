"""补跑失败的 2 个任务：toolbar_eraser + dashboard_settings"""

import asyncio, os, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

env_file = Path.home() / ".hermes" / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

# 代理: HTTP_PROXY 给 LLM，NO_PROXY 排除 localhost (CDP)
for var in ["ALL_PROXY", "all_proxy", "SOCKS_PROXY", "socks_proxy"]:
    os.environ.pop(var, None)
os.environ["HTTP_PROXY"] = "http://127.0.0.1:1097"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1097"
os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"
os.environ["no_proxy"] = "localhost,127.0.0.1,0.0.0.0"
os.environ["XDG_CONFIG_HOME"] = str(Path.home() / "browser-use-config")
urllib.request.getproxies = lambda: {}

LLM_BASE = os.environ.get("OPENAI_BASE_URL", "https://llm-gateway.mlamp.cn/v1")
LLM_KEY = os.environ.get("OPENAI_API_KEY", "")

TASKS = [
    ("toolbar_eraser", "http://localhost:8088/toolbar_app.html",
     "Click the eraser tool in the drawing toolbar. The tools are icon-only SVG buttons with no text labels. After clicking, call done and report which tool you selected."),
    ("dashboard_settings", "http://localhost:8088/dashboard.html",
     "Click the settings icon button (gear icon) in the top-right header area of the dashboard. After clicking, call done and report what happened."),
]

async def run_one(name, url, task_desc, use_vision):
    from browser_use.browser.session import BrowserSession
    from browser_use.llm.openai.chat import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=LLM_KEY, base_url=LLM_BASE, temperature=0.0)
    session = BrowserSession(headless=True)

    try:
        if use_vision:
            from browser_use_vision.enhanced_agent import VisionEnhancedAgent
            from browser_use_vision.grounding.florence import FlorenceBackend
            backend = FlorenceBackend(remote_url="http://localhost:8100")
            agent = VisionEnhancedAgent(task=task_desc, llm=llm, browser_session=session,
                                        vision_backend=backend, max_steps=8)
        else:
            from browser_use.agent.service import Agent
            agent = Agent(task=task_desc, llm=llm, browser_session=session,
                         use_vision=False, max_steps=8)

        await session.start()
        page = await session.get_current_page()
        await page.goto(url)
        await asyncio.sleep(3)

        t0 = time.time()
        history = await asyncio.wait_for(agent.run(), timeout=90)
        elapsed = time.time() - t0
        steps = history.number_of_steps()
        done = history.is_done()
        result = history.final_result() or ""
        success = done and steps < 8
        print(f"  {'✅' if success else '❌'} {name} [{'vision' if use_vision else 'baseline'}]: {steps} steps, {elapsed:.1f}s, done={done}")
        if result:
            print(f"     Result: {result[:100]}")
    except asyncio.TimeoutError:
        print(f"  ❌ {name} [{'vision' if use_vision else 'baseline'}]: TIMEOUT (90s)")
    except Exception as e:
        print(f"  ❌ {name} [{'vision' if use_vision else 'baseline'}]: ERROR: {e}")
    finally:
        await session.close()

async def main():
    print("补跑 2 个任务 × 2 模式")
    for name, url, task_desc in TASKS:
        print(f"\n[{name}]")
        await run_one(name, url, task_desc, use_vision=False)
        await run_one(name, url, task_desc, use_vision=True)

import logging
logging.basicConfig(level=logging.WARNING)
asyncio.run(main())
