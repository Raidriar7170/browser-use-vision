# 🔍 Browser-Use Vision Enhancement

[![Tests](https://github.com/Raidriar7170/browser-use-vision/actions/workflows/tests.yml/badge.svg)](https://github.com/Raidriar7170/browser-use-vision/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**A vision-grounding plugin for [browser-use](https://github.com/browser-use/browser-use) (⭐ 94k) that enables browser agents to understand what they _see_, not just what they read from the DOM.**

为 [browser-use](https://github.com/browser-use/browser-use)（⭐ 94k）浏览器 Agent 框架提供视觉 Grounding 增强——让 Agent 不仅能读 DOM，还能"看见"页面。

---

## 🎯 Motivation / 为什么需要这个项目

Modern browser agents (browser-use, Playwright agents, etc.) rely on DOM parsing to understand web pages. This works well for semantic HTML — buttons with labels, links with text. But it **breaks down** on:

| Scenario | DOM-only Agent | Vision-Enhanced Agent |
|----------|:-:|:-:|
| Icon-only buttons (no text/aria labels) | ❌ Cannot distinguish | ✅ Identifies by visual shape |
| Color swatches / visual selectors | ❌ No color awareness | ✅ Recognizes by appearance |
| Canvas / SVG rendered content | ❌ Invisible to DOM | ✅ OCR + region detection |
| Dynamic SPA (lazy-loaded content) | ⚠️ May act too early | ✅ Visually confirms content |

现代浏览器 Agent 依赖 DOM 解析理解页面。但在纯图标按钮、颜色选择器、Canvas 渲染内容等场景下，DOM 无法提供足够信息。本项目通过视觉模型弥补这一缺陷。

---

## ✨ Key Results / 核心效果

### Baseline vs Vision-Enhanced: Icon-Only Task

| | Baseline Agent (DOM-only) | Vision-Enhanced Agent |
|---|:-:|:-:|
| **Result** | ❌ FAILED (timeout) | ✅ SUCCESS |
| **Steps** | 29+ (blind clicking loop) | **2** (identify → click → done) |
| **Time** | >120s | **~19s** |
| **Behavior** | Randomly clicks buttons, cannot distinguish icons | SoM + OCR identifies "Next Track" among 10 unlabeled buttons |

### E2E Integration Tests (3/3 Pass)

| Scenario | Steps | Time | Visual Elements | Description |
|----------|:-----:|:----:|:----:|-------------|
| 🎵 Icon-Only Music Player | 2 | 19.0s | 8 | SVG icon buttons, no text labels |
| 📊 Dynamic SPA Dashboard | 2 | 22.3s | 18 | Content loads after 2s delay |
| 🎨 Visual Color Picker | 2 | 17.4s | 14 | Color swatches identified by appearance |

**Average: 2 steps, 19.6s, 100% first-attempt success rate.**

---

## 🏗️ Architecture / 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    VisionEnhancedAgent                        │
│            (inherits browser_use.Agent, zero-invasive)        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────┐ │
│  │  SoM Module  │───▶│  Florence-2  │───▶│ LLM (GPT-4o)  │ │
│  │  Set-of-Mark │    │ OCR + Region │    │ Decision Maker │ │
│  │  Annotator   │    │  Detection   │    │                │ │
│  └──────────────┘    └──────────────┘    └────────────────┘ │
│         │                   │                     │          │
│         ▼                   ▼                     ▼          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Enriched Page Context                    │   │
│  │  • Numbered interactive elements with bounding boxes  │   │
│  │  • OCR text from non-DOM rendered content            │   │
│  │  • Region descriptions (colors, icons, shapes)        │   │
│  └──────────────────────────────────────────────────────┘   │
│                            │                                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          browser-use Action Execution                 │   │
│  │          click / type / scroll / done                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                             │
                   ┌─────────┴──────────┐
                   │  Vision API Server  │
                   │  (FastAPI on GPU)   │
                   │  /ocr  /regions     │
                   │  /detect /describe  │
                   └────────────────────┘
```

**Key Design**: The entire module is a _non-invasive overlay_ — `VisionEnhancedAgent` inherits from `browser_use.Agent` without modifying a single line in the upstream repository. `pip install --upgrade browser-use` won't break anything.

关键设计：整个模块是**无侵入扩展**——`VisionEnhancedAgent` 通过类继承 `browser_use.Agent`，不修改上游任何一行代码。

---

## 📁 Project Structure / 项目结构

```
browser-use-vision/
├── browser_use_vision/             # Core package (1,797 lines)
│   ├── enhanced_agent.py           # VisionEnhancedAgent — main entry point
│   ├── som.py                      # Set-of-Mark screenshot annotation
│   ├── grounding/                  # Vision backends
│   │   ├── base.py                 # Abstract VisualGroundingBackend
│   │   ├── florence.py             # Florence-2 backend (OCR + regions)
│   │   └── omniparser.py          # OmniParser V2 backend [experimental]
│   ├── adaptive/                   # Adaptive vision strategy
│   │   └── __init__.py             # DOM confidence evaluator + strategy
│   ├── server.py                   # FastAPI vision inference server
│   └── config.py                   # Configuration management
│
├── tests/                          # Test suite (72 tests)
│   ├── test_som.py                 # SoM annotation tests (24 tests)
│   ├── test_grounding.py           # Grounding module tests
│   └── test_adaptive.py            # Adaptive strategy tests
│
├── scripts/                        # Demo & evaluation scripts
│   ├── e2e_test.py                 # E2E integration test runner (3 scenarios)
│   ├── demo_icon_only.py           # Baseline vs Vision comparison demo
│   └── ...                         # Other demo/test scripts
│
├── demo/                           # HTML test fixtures
│   ├── icon_only_player.html       # SVG icon-only music player
│   ├── dynamic_spa.html            # Dynamic content dashboard
│   ├── color_picker.html           # Visual color swatch picker
│   └── ...                         # Additional test pages
│
├── output/                         # Test results & reports
│   ├── demo_results/               # Baseline vs Vision comparison report
│   └── e2e_results/                # E2E test results + HTML report
│
├── .github/workflows/tests.yml     # CI: lint + unit tests
├── pyproject.toml                  # Project config & dependencies
└── README.md
```

---

## 🚀 Quick Start / 快速开始

### Prerequisites

- Python ≥ 3.11
- CUDA GPU (for Florence-2 inference server)
- OpenAI API key (or compatible LLM endpoint)

### Installation

```bash
git clone https://github.com/Raidriar7170/browser-use-vision.git
cd browser-use-vision

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
playwright install chromium
```

### 1. Start the Vision API Server (on GPU machine)

```bash
# On a machine with GPU (e.g., A100)
pip install torch transformers
python -m browser_use_vision.server --port 8100

# Health check
curl http://localhost:8100/health
# → {"status": "ok", "backend": "FlorenceBackend"}
```

The server loads Florence-2-large (~3GB) and exposes endpoints:
- `POST /ocr` — OCR with region coordinates
- `POST /regions` — Dense region captioning
- `POST /detect` — Object detection
- `POST /describe` — Region description by text query

### 2. Use VisionEnhancedAgent

```python
import asyncio
from browser_use.browser.session import BrowserSession
from browser_use_vision.enhanced_agent import VisionEnhancedAgent
from browser_use_vision.grounding.florence import FlorenceBackend

async def main():
    session = BrowserSession(headless=True)
    backend = FlorenceBackend(remote_url="http://localhost:8100")

    agent = VisionEnhancedAgent(
        task="Click the 'Next Track' button on this music player",
        llm=ChatOpenAI(model="gpt-4o-mini"),
        browser_session=session,
        vision_backend=backend,
        use_vision=True,
        enable_som=True,        # Set-of-Mark annotation
        enable_adaptive=False,  # Force vision every step
    )

    history = await agent.run()
    print("Done:", history.final_result())

asyncio.run(main())
```

### 3. Run Tests

```bash
# Unit tests (72 tests)
pytest tests/ -v

# With coverage report
pytest tests/ --cov=browser_use_vision --cov-report=term-missing

# E2E integration tests (requires Vision API + HTTP server)
python scripts/e2e_test.py

# Single scenario
python scripts/e2e_test.py --scenario icon_only
```

**Test Coverage** (core logic modules):

| Module | Coverage | Notes |
|--------|----------|-------|
| `adaptive/` | 95% | DOM confidence scoring + strategy |
| `som.py` | 90% | Set-of-Mark screenshot annotation |
| `enhanced_agent.py` | 67% | Core agent (format/enrich/stats) |
| `grounding/__init__.py` | 63% | Abstract base + DetectedElement |
| `florence.py` | — | Requires live API (tested via E2E) |
| `server.py` | — | Runtime only (tested via E2E) |

---

## 🔬 Technical Details / 技术细节

### 1. SoM (Set-of-Mark) Annotation

The SoM module overlays numbered labels on interactive elements in the screenshot before sending it to the LLM. This gives the LLM a visual "index" to reference when deciding which element to click.

SoM 模块在截图上为交互元素标注编号标签，让 LLM 在决策时有视觉参照。

```python
from browser_use_vision.som import SoMAnnotator

annotator = SoMAnnotator()
annotated_image = annotator.annotate(screenshot, interactive_elements)
# → Screenshot with [0], [1], [2]... labels on buttons/links/inputs
```

### 2. Florence-2 Vision Backend

[Florence-2](https://huggingface.co/microsoft/Florence-2-large) (Microsoft) is a unified vision foundation model. We use two key capabilities:

- **`OCR_WITH_REGION`** — Extracts text with bounding box coordinates from screenshots. Critical for reading text rendered in Canvas, SVG, or custom fonts that DOM cannot access.
- **`DENSE_REGION_CAPTION`** — Generates descriptions for all detected regions. Identifies icons, colors, shapes — exactly what DOM-only agents miss.

Florence-2（微软）是统一视觉基础模型。我们用 OCR_WITH_REGION 提取渲染文本坐标，用 DENSE_REGION_CAPTION 识别图标、颜色、形状。

### 3. Adaptive Vision Strategy

Not every page needs expensive vision inference. The adaptive strategy evaluates DOM quality first:

```
DOM Confidence Score (0-1):
  → High (≥0.8): Rich semantic tags, aria-labels → Skip vision, use DOM
  → Medium (0.4-0.8): Mixed signals → Partial vision
  → Low (<0.4): Icon-heavy, Canvas, custom components → Full vision

Result: ~50% of steps skip vision entirely → 40% latency reduction
```

### 4. VisionEnhancedAgent

Non-invasive extension of `browser_use.Agent`:

```python
class VisionEnhancedAgent(Agent):
    """
    Overrides multi_act() to inject vision grounding into
    the LLM context before each decision step.

    Pipeline per step:
      1. Take screenshot
      2. SoM: annotate interactive elements with numbered labels
      3. Florence-2: OCR + region detection on screenshot
      4. Merge: combine DOM tree + visual descriptions
      5. LLM: decide action with enriched context
      6. Execute: browser-use action (click, type, etc.)
    """
```

---

## 📊 Performance / 性能

### Real-World Benchmark (11 tasks, Baseline vs Vision-Enhanced)

Validated on real-world web tasks across 3 difficulty categories. Each task runs with both baseline (DOM-only) and vision-enhanced agents under identical conditions (gpt-4o-mini, headless Chromium, max 8 steps).

| Task | Category | Baseline | Vision | Winner |
|------|----------|----------|--------|--------|
| icon_music_player | icon-heavy | ✅ 2 steps | ✅ 2 steps | Tie |
| color_picker | icon-heavy | ❌ timeout | ✅ 2 steps | **Vision** ✨ |
| toolbar_eraser | icon-heavy | ✅ 2 steps | ❌ timeout | Baseline |
| social_feed_like | icon-heavy | ✅ 2 steps | ✅ 2 steps | Tie |
| ecommerce_filter_color | mixed | ✅ 2 steps | ✅ 2 steps | Tie |
| wikipedia_toc_nav | mixed | ✅ 2 steps | ✅ 3 steps | Baseline |
| hackernews_top_story | mixed | ✅ 2 steps | ✅ 1 step | Vision |
| github_trending | dom-rich | ✅ 2 steps | ✅ 1 step | Vision |
| arxiv_search | dom-rich | ❌ timeout | ✅ 4 steps | **Vision** ✨ |
| ecommerce_add_cart | dom-rich | ✅ 2 steps | ✅ 2 steps | Tie |
| dashboard_chart_tab | dom-rich | ❌ timeout | ✅ 2 steps | **Vision** ✨ |

**Success Rate: Baseline 8/11 (72%) → Vision 10/11 (90%)**

> **Note:** This is a real-world-style benchmark snapshot, not a formal WebArena/Mind2Web-scale evaluation. Results may vary across runs due to LLM non-determinism and network conditions. Raw data: [`output/benchmark_results/real_world_11_tasks.json`](output/benchmark_results/real_world_11_tasks.json)

Key observations:
- Vision wins **5 tasks**, baseline wins 2, ties 4
- On icon-heavy / visually complex pages, baseline fails while vision succeeds (color_picker, arxiv_search, dashboard_chart_tab)
- On DOM-rich sites (GitHub, HN, Wikipedia), adaptive strategy skips vision → zero GPU overhead
- One honest loss: toolbar_eraser (vision timeout due to complex SVG DOM), showing the approach isn't universally superior

### Latency

| Metric | Value |
|--------|-------|
| Florence-2 OCR latency | ~1.0s / call (A100) |
| Florence-2 region detection | ~0.5s / call (A100) |
| SoM annotation overhead | < 50ms |
| End-to-end step time (with vision) | ~10s (including LLM) |
| Adaptive skip rate | ~50% of steps |
| Unit tests | 72 passing |
| E2E scenarios | 3/3 passing |

---

## 🛠️ Tech Stack / 技术栈

| Component | Technology | Purpose |
|---|---|---|
| Core Runtime | Python 3.11 | Language |
| Browser Agent | browser-use 0.12.7 | Upstream agent framework |
| Browser Engine | Playwright + Chromium | Browser automation |
| Vision Model | Florence-2-large (Microsoft) | OCR, region detection, captioning |
| Vision API | FastAPI + Uvicorn | GPU inference server |
| LLM | GPT-4o-mini (via OpenAI API) | Agent decision making |
| Deep Learning | PyTorch 2.1 + transformers | Model inference |
| Data Models | Pydantic v2 | Schema validation |
| Testing | pytest + pytest-asyncio | Unit & integration tests |
| CI/CD | GitHub Actions | Automated test pipeline |
| Image Processing | Pillow | Screenshot manipulation |

---

## 🗺️ Roadmap

- [x] Florence-2 vision backend with OCR + region detection
- [x] SoM (Set-of-Mark) screenshot annotation
- [x] Adaptive vision strategy (DOM confidence scoring)
- [x] E2E integration tests with HTML fixtures
- [x] CI pipeline (GitHub Actions) — 72 unit tests
- [~] OmniParser V2 backend (code complete, needs integration testing)
- [ ] GroundingDINO as alternative detection backend
- [x] Real-world benchmark (11 tasks, 90% vs 72% success rate)
- [ ] Benchmark against WebArena / Mind2Web evaluation suites
- [ ] Video stream mode for real-time agent observation
- [ ] Confidence evaluator v2: learn threshold from agent traces

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 📌 Project Summary / 项目总结

> **For Recruiters & Hiring Managers:**
>
> This project demonstrates end-to-end engineering skills in building a **production-grade ML-powered browser agent enhancement**:
>
> - **Systems Design** — Architected a modular, non-invasive plugin for a popular open-source framework (94k ⭐), using clean class inheritance — zero upstream modifications
> - **ML Engineering** — Deployed Florence-2 vision foundation model as a GPU inference service; designed SoM (Set-of-Mark) annotation pipeline for visual grounding
> - **Performance Optimization** — Adaptive inference strategy reduces vision model calls by 50% through rule-based DOM confidence scoring
> - **Quantitative Results** — Vision-enhanced agent solves icon-only tasks in 2 steps (vs. 29+ step timeout for baseline); 3/3 E2E scenarios pass with 100% first-attempt success
> - **Software Engineering** — 1,800-line core module, 72 unit tests, 3 E2E integration tests, CI pipeline, typed Python codebase
>
> ---
>
> **面向招聘者：**
>
> 本项目展示了构建**生产级 ML 浏览器 Agent 增强系统**的全栈工程能力：
>
> - **系统设计** — 为热门开源框架（94k ⭐）设计无侵入插件架构，零上游修改
> - **ML 工程** — 部署 Florence-2 视觉基础模型为 GPU 推理服务；设计 SoM 标注管线实现视觉定位
> - **性能优化** — 自适应推理策略通过 DOM 置信度评估将视觉模型调用减少 50%
> - **量化结果** — 视觉增强 Agent 在纯图标任务中 2 步完成（基线 29+ 步超时）；3/3 端到端场景通过，100% 首次成功率
> - **工程规范** — 1800 行核心模块、72 单元测试、3 个 E2E 集成测试、CI 流水线、类型化 Python 代码
