"""
端到端集成测试: VisionEnhancedAgent + Florence-2 + 真实浏览器

场景:
  1. icon-only: 纯图标按钮页面，需要视觉才能区分
  2. dynamic-spa: 动态内容加载，DOM 初始不完整
  3. canvas-chart: Canvas 图表中的数据，DOM 无法读取
  4. tooltip-hidden: hover 才显示的信息
  5. visual-form: 图片验证码风格的表单

每个场景都有独立的 HTML fixture 和验证逻辑。
跑之前需要:
  1. Florence-2 服务: http://localhost:8100/health
  2. HTTP 服务: python -m http.server 8088 (在 demo/ 目录)
"""

import asyncio
import json
import os
import sys
import time
import logging
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------- 环境配置 ----------
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
        val = val.strip().strip('"').strip("'")
        if key and val:
            os.environ.setdefault(key, val)

_load_hermes_env()

# 清除代理设置，避免干扰 browser-use CDP 连接
for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                  "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_var, None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
VISION_API_URL = "http://localhost:8100"
DEMO_BASE = "http://localhost:8088"
MAX_STEPS = 15

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_test")


def get_llm():
    from browser_use.llm.openai.chat import ChatOpenAI
    kwargs = dict(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, temperature=0.0)
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


# ============================================================
# HTML Fixture 生成
# ============================================================

FIXTURES = {}

# 1) Icon-only — 已有
FIXTURES["icon_only"] = None  # 使用已有的 icon_only_player.html

# 2) Dynamic SPA — 延迟加载内容
FIXTURES["dynamic_spa"] = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Dynamic Dashboard</title>
<style>
  body { font-family: sans-serif; background: #1a1a2e; color: #eee; padding: 40px; }
  .loading { color: #888; font-size: 1.2em; }
  .card { background: #16213e; border-radius: 12px; padding: 20px; margin: 16px 0; display: none; }
  .card.visible { display: block; }
  .metric { font-size: 2em; font-weight: bold; color: #e94560; }
  button { background: #0f3460; color: white; border: none; padding: 10px 20px;
           border-radius: 8px; cursor: pointer; margin: 8px; font-size: 1em; }
  button:hover { background: #e94560; }
  #status { margin-top: 20px; padding: 12px; background: #0a3d62; border-radius: 8px; }
</style></head>
<body>
<h1>📊 Sales Dashboard</h1>
<div id="loading" class="loading">Loading data...</div>
<div id="cards"></div>
<div>
  <button onclick="doAction('refresh')">🔄 Refresh</button>
  <button onclick="doAction('export')">📥 Export CSV</button>
  <button onclick="doAction('filter_q1')">Q1</button>
  <button onclick="doAction('filter_q2')">Q2</button>
</div>
<div id="status"></div>

<script>
window.actions = [];
function doAction(name) {
    window.actions.push(name);
    document.getElementById('status').textContent = 'Action: ' + name;
}

// 延迟 2 秒加载数据
setTimeout(() => {
    document.getElementById('loading').style.display = 'none';
    const data = [
        { title: 'Total Revenue', value: '$1,234,567', change: '+12.3%' },
        { title: 'Active Users', value: '89,432', change: '+5.7%' },
        { title: 'Conversion Rate', value: '3.42%', change: '-0.8%' },
    ];
    const container = document.getElementById('cards');
    data.forEach(d => {
        const card = document.createElement('div');
        card.className = 'card visible';
        card.innerHTML = '<h3>' + d.title + '</h3><div class="metric">' + d.value + '</div><div>' + d.change + '</div>';
        container.appendChild(card);
    });
}, 2000);
</script>
</body></html>"""

# 3) Canvas chart — 数据只在 Canvas 里渲染
FIXTURES["canvas_chart"] = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Sales Chart</title>
<style>
  body { font-family: sans-serif; background: #0d1117; color: #c9d1d9; padding: 40px; }
  canvas { background: #161b22; border-radius: 12px; border: 1px solid #30363d; }
  .controls { margin-top: 20px; }
  button { background: #238636; color: white; border: none; padding: 8px 16px;
           border-radius: 6px; cursor: pointer; margin: 4px; }
  button.active { background: #1f6feb; }
  #info { margin-top: 12px; padding: 10px; background: #161b22; border-radius: 8px; min-height: 40px; }
</style></head>
<body>
<h1>📈 Quarterly Revenue Chart</h1>
<canvas id="chart" width="800" height="400"></canvas>
<div class="controls">
  <button onclick="showQuarter('Q1')" class="active">Q1</button>
  <button onclick="showQuarter('Q2')">Q2</button>
  <button onclick="showQuarter('Q3')">Q3</button>
  <button onclick="showQuarter('Q4')">Q4</button>
  <button onclick="doAction('download_report')">Download Report</button>
</div>
<div id="info">Showing Q1 2024 data</div>

<script>
window.actions = [];
const quarters = {
    Q1: [120, 145, 132, 168],
    Q2: [155, 178, 162, 190],
    Q3: [180, 195, 210, 225],
    Q4: [200, 215, 230, 260],
};

function drawChart(q) {
    const canvas = document.getElementById('chart');
    const ctx = canvas.getContext('2d');
    const data = quarters[q];
    ctx.clearRect(0, 0, 800, 400);

    // Grid
    ctx.strokeStyle = '#30363d';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
        const y = 50 + i * 70;
        ctx.beginPath(); ctx.moveTo(80, y); ctx.lineTo(750, y); ctx.stroke();
        ctx.fillStyle = '#8b949e';
        ctx.font = '12px sans-serif';
        ctx.fillText('$' + (300 - i * 60) + 'K', 20, y + 4);
    }

    // Bars
    const months = ['Jan', 'Feb', 'Mar', 'Apr'];
    const colors = ['#58a6ff', '#3fb950', '#d29922', '#f85149'];
    data.forEach((val, i) => {
        const x = 120 + i * 160;
        const h = val * 1.2;
        const y = 380 - h;
        ctx.fillStyle = colors[i];
        ctx.fillRect(x, y, 80, h);
        ctx.fillStyle = '#c9d1d9';
        ctx.font = 'bold 14px sans-serif';
        ctx.fillText('$' + val + 'K', x + 15, y - 10);
        ctx.fillText(months[i], x + 25, 395);
    });

    // Title
    ctx.fillStyle = '#c9d1d9';
    ctx.font = 'bold 16px sans-serif';
    ctx.fillText(q + ' 2024 Revenue', 320, 30);
}

function showQuarter(q) {
    window.actions.push('show_' + q);
    drawChart(q);
    document.getElementById('info').textContent = 'Showing ' + q + ' 2024 data';
    document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
}

function doAction(name) {
    window.actions.push(name);
    document.getElementById('info').textContent = 'Action: ' + name;
}

drawChart('Q1');
</script>
</body></html>"""

# 4) Tooltip / hover 信息
FIXTURES["tooltip_info"] = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Team Directory</title>
<style>
  body { font-family: sans-serif; background: #1e1e2e; color: #cdd6f4; padding: 40px; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  .person {
    background: #313244; border-radius: 12px; padding: 20px; text-align: center;
    cursor: pointer; position: relative; transition: transform 0.2s;
  }
  .person:hover { transform: translateY(-4px); }
  .avatar {
    width: 64px; height: 64px; border-radius: 50%; margin: 0 auto 12px;
    display: flex; align-items: center; justify-content: center; font-size: 2em;
  }
  .name { font-weight: bold; font-size: 1.1em; }
  .role { color: #a6adc8; font-size: 0.9em; }
  .tooltip {
    display: none; position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
    background: #11111b; color: #cdd6f4; padding: 12px; border-radius: 8px;
    width: 220px; text-align: left; font-size: 0.85em; z-index: 10;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  }
  .person:hover .tooltip { display: block; }
  button { background: #89b4fa; color: #1e1e2e; border: none; padding: 10px 20px;
           border-radius: 8px; cursor: pointer; margin: 8px; font-weight: bold; }
  #result { margin-top: 20px; padding: 12px; background: #313244; border-radius: 8px; min-height: 40px; }
</style></head>
<body>
<h1>👥 Team Directory</h1>
<div class="grid">
  <div class="person" onclick="selectPerson('alice')">
    <div class="avatar" style="background:#f38ba8;">👩‍💻</div>
    <div class="name">Alice Chen</div>
    <div class="role">Lead Engineer</div>
    <div class="tooltip">📧 alice@company.com<br>📱 +1-555-0101<br>🏢 Building A, Floor 3<br>⭐ 5 years</div>
  </div>
  <div class="person" onclick="selectPerson('bob')">
    <div class="avatar" style="background:#a6e3a1;">👨‍🔬</div>
    <div class="name">Bob Martinez</div>
    <div class="role">Data Scientist</div>
    <div class="tooltip">📧 bob@company.com<br>📱 +1-555-0102<br>🏢 Building B, Floor 1<br>⭐ 3 years</div>
  </div>
  <div class="person" onclick="selectPerson('carol')">
    <div class="avatar" style="background:#89b4fa;">👩‍🎨</div>
    <div class="name">Carol Wu</div>
    <div class="role">UX Designer</div>
    <div class="tooltip">📧 carol@company.com<br>📱 +1-555-0103<br>🏢 Building A, Floor 2<br>⭐ 2 years</div>
  </div>
</div>
<div style="margin-top: 24px;">
  <button onclick="doAction('send_message')">💬 Send Message</button>
  <button onclick="doAction('schedule_meeting')">📅 Schedule Meeting</button>
  <button onclick="doAction('view_profile')">👤 View Full Profile</button>
</div>
<div id="result"></div>

<script>
window.actions = [];
function selectPerson(name) {
    window.actions.push('select_' + name);
    document.getElementById('result').textContent = 'Selected: ' + name;
}
function doAction(name) {
    window.actions.push(name);
    document.getElementById('result').textContent = 'Action: ' + name;
}
</script>
</body></html>"""

# 5) Visual form — 颜色选择
FIXTURES["color_picker"] = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Theme Configurator</title>
<style>
  body { font-family: sans-serif; background: #0f172a; color: #e2e8f0; padding: 40px; }
  .section { background: #1e293b; border-radius: 12px; padding: 24px; margin: 16px 0; }
  h2 { margin-bottom: 16px; }
  .color-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
  .color-swatch {
    width: 60px; height: 60px; border-radius: 10px; cursor: pointer; border: 3px solid transparent;
    transition: all 0.2s; position: relative;
  }
  .color-swatch:hover { transform: scale(1.1); }
  .color-swatch.selected { border-color: white; box-shadow: 0 0 12px rgba(255,255,255,0.3); }
  .color-swatch::after {
    content: attr(data-name); position: absolute; bottom: -20px; left: 50%;
    transform: translateX(-50%); font-size: 0.7em; color: #94a3b8; white-space: nowrap;
  }
  .preview { margin-top: 24px; padding: 20px; border-radius: 12px; text-align: center; min-height: 80px; }
  button { padding: 10px 24px; border: none; border-radius: 8px; cursor: pointer;
           font-size: 1em; margin: 8px; }
  .btn-apply { background: #22c55e; color: white; }
  .btn-reset { background: #64748b; color: white; }
  #status { margin-top: 16px; padding: 10px; background: #1e293b; border-radius: 8px; }
</style></head>
<body>
<h1>🎨 Theme Configurator</h1>
<div class="section">
  <h2>Primary Color</h2>
  <div class="color-grid" id="colors">
    <div class="color-swatch" style="background:#ef4444;" data-color="red" data-name="Red" onclick="pickColor(this,'red')"></div>
    <div class="color-swatch" style="background:#f97316;" data-color="orange" data-name="Orange" onclick="pickColor(this,'orange')"></div>
    <div class="color-swatch" style="background:#eab308;" data-color="yellow" data-name="Yellow" onclick="pickColor(this,'yellow')"></div>
    <div class="color-swatch" style="background:#22c55e;" data-color="green" data-name="Green" onclick="pickColor(this,'green')"></div>
    <div class="color-swatch selected" style="background:#3b82f6;" data-color="blue" data-name="Blue" onclick="pickColor(this,'blue')"></div>
    <div class="color-swatch" style="background:#8b5cf6;" data-color="purple" data-name="Purple" onclick="pickColor(this,'purple')"></div>
  </div>
</div>
<div class="section">
  <h2>Preview</h2>
  <div class="preview" id="preview" style="background: #3b82f6;">
    <h3>Your Selected Theme</h3>
    <p>This is how your primary color looks</p>
  </div>
</div>
<div>
  <button class="btn-apply" onclick="doAction('apply')">✅ Apply Theme</button>
  <button class="btn-reset" onclick="doAction('reset')">🔄 Reset</button>
</div>
<div id="status"></div>

<script>
window.actions = [];
function pickColor(el, color) {
    window.actions.push('pick_' + color);
    document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('selected'));
    el.classList.add('selected');
    document.getElementById('preview').style.background = el.style.background;
    document.getElementById('status').textContent = 'Selected: ' + color;
}
function doAction(name) {
    window.actions.push(name);
    document.getElementById('status').textContent = 'Action: ' + name;
}
</script>
</body></html>"""


def write_fixtures():
    """将 fixture HTML 写入 demo/ 目录"""
    demo_dir = PROJECT_ROOT / "demo"
    demo_dir.mkdir(exist_ok=True)
    for name, html in FIXTURES.items():
        if html is None:
            continue
        path = demo_dir / f"{name}.html"
        path.write_text(html)
        logger.info(f"Wrote fixture: {path.name}")


# ============================================================
# 测试场景定义
# ============================================================

SCENARIOS = [
    {
        "name": "icon_only",
        "title": "🎵 Icon-Only Music Player",
        "url": f"{DEMO_BASE}/icon_only_player.html",
        "task": "Click the 'Next Track' button on this music player. The buttons have NO text labels — they are icon-only SVG buttons. Once you click it, you are done.",
        "validate_actions": ["next"],
        "description": "SVG icon buttons without text labels — requires vision to identify",
    },
    {
        "name": "dynamic_spa",
        "title": "📊 Dynamic SPA Dashboard",
        "url": f"{DEMO_BASE}/dynamic_spa.html",
        "task": "Wait for the dashboard data to finish loading, then click the 'Export CSV' button (it has a 📥 icon). Once clicked, you are done.",
        "validate_actions": ["export"],
        "description": "Content loads dynamically after 2s delay",
    },
    {
        "name": "color_picker",
        "title": "🎨 Visual Color Picker",
        "url": f"{DEMO_BASE}/color_picker.html",
        "task": "Select the GREEN color swatch (it's a solid green square in the color grid), then click the 'Apply Theme' button. The swatches have no text on them — identify by color. Once both actions are done, you are finished.",
        "validate_actions": ["pick_green", "apply"],
        "description": "Color swatches identified only by visual color — requires vision",
    },
]


# ============================================================
# Agent 运行器
# ============================================================

async def run_scenario(scenario: dict) -> dict:
    """在真实浏览器中运行一个场景"""
    from browser_use.browser.session import BrowserSession
    from browser_use_vision.enhanced_agent import VisionEnhancedAgent
    from browser_use_vision.grounding.florence import FlorenceBackend

    name = scenario["name"]
    logger.info(f"\n{'='*60}")
    logger.info(f"Running: {scenario['title']}")
    logger.info(f"Task: {scenario['task']}")
    logger.info(f"{'='*60}")

    session = BrowserSession(headless=True)
    result = {"name": name, "title": scenario["title"], "description": scenario["description"]}

    try:
        llm = get_llm()
        vision_backend = FlorenceBackend(remote_url=VISION_API_URL)

        agent = VisionEnhancedAgent(
            task=scenario["task"],
            llm=llm,
            browser_session=session,
            vision_backend=vision_backend,
            use_vision=True,
            enable_som=True,
            enable_adaptive=False,
            max_steps=MAX_STEPS,
        )

        await session.start()
        page = await session.get_current_page()
        await page.goto(scenario["url"])
        await asyncio.sleep(3)  # 等待动态内容加载

        t0 = time.perf_counter()
        history = await agent.run()
        elapsed = round(time.perf_counter() - t0, 2)

        # 从页面读取 actions — 必须在 session close 之前
        actions = []
        try:
            page = await session.get_current_page()
            if page:
                actions = await page.evaluate("() => window.actions || []")
                logger.info(f"Page actions recorded: {actions}")
        except Exception as e:
            logger.warning(f"Could not read page actions: {e}")

        # 验证
        expected = scenario["validate_actions"]
        all_found = all(a in actions for a in expected)

        # 从 history 获取 agent 的自我报告
        agent_success = False
        agent_text = ""
        try:
            if hasattr(history, "final_result"):
                fr = history.final_result()
                if fr:
                    agent_text = str(fr)
                    agent_success = True
        except Exception:
            pass

        steps = 0
        try:
            if hasattr(history, "history"):
                steps = len(history.history)
        except Exception:
            pass

        success = all_found or agent_success
        result.update({
            "success": success,
            "actions_validated": all_found,
            "agent_reported_success": agent_success,
            "agent_text": agent_text,
            "expected_actions": expected,
            "actual_actions": actions,
            "steps": steps,
            "elapsed": elapsed,
            "vision_stats": agent.vision_stats,
        })

        status = "✅" if success else "❌"
        logger.info(f"\n{status} {name}: success={success}, steps={steps}, elapsed={elapsed}s")
        logger.info(f"   Expected: {expected}")
        logger.info(f"   Got:      {actions}")
        logger.info(f"   Agent:    {agent_text[:100]}")

    except Exception as e:
        logger.error(f"❌ {name} ERROR: {e}")
        logger.debug(traceback.format_exc())
        result.update({"success": False, "error": str(e)})

    finally:
        try:
            await session.close()
        except Exception:
            pass

    return result


async def run_all():
    """运行所有场景"""
    write_fixtures()

    results = []
    for scenario in SCENARIOS:
        r = await run_scenario(scenario)
        results.append(r)
        # 短暂等待，让浏览器资源释放
        await asyncio.sleep(2)

    # 汇总
    passed = sum(1 for r in results if r.get("success"))
    total = len(results)
    print(f"\n{'='*60}")
    print(f"📊 端到端测试结果: {passed}/{total} 通过")
    print(f"{'='*60}")
    for r in results:
        s = "✅" if r.get("success") else "❌"
        steps = r.get("steps", "?")
        elapsed = r.get("elapsed", "?")
        print(f"  {s} {r['title']}: {steps} steps, {elapsed}s")
        if r.get("error"):
            print(f"     ERROR: {r['error']}")

    # 保存
    out_dir = PROJECT_ROOT / "output" / "e2e_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "e2e_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n结果已保存: {out_path}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", help="只运行指定场景", default=None)
    args = parser.parse_args()

    if args.scenario:
        matched = [s for s in SCENARIOS if s["name"] == args.scenario]
        if not matched:
            print(f"未知场景: {args.scenario}")
            print(f"可选: {[s['name'] for s in SCENARIOS]}")
            sys.exit(1)
        asyncio.run(run_scenario(matched[0]))
    else:
        asyncio.run(run_all())
