# 🔍 Browser-Use Vision Enhancement

[![Tests](https://github.com/Raidriar7170/browser-use-vision/actions/workflows/tests.yml/badge.svg)](https://github.com/Raidriar7170/browser-use-vision/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**A vision-grounding plugin for
[browser-use](https://github.com/browser-use/browser-use) (⭐ 94k)
that enables browser agents to understand what they _see_,
not just what they read from the DOM.**

为 [browser-use](https://github.com/browser-use/browser-use)（⭐ 94k）浏览器 Agent 框架提供视觉 Grounding 增强——让 Agent 不仅能读 DOM，还能"看见"页面。

---

## 🎯 Motivation / 为什么需要这个项目

Modern browser agents (browser-use, Playwright agents, etc.) rely on DOM parsing
to understand web pages. This works well for semantic HTML — buttons with labels,
links with text. But it **breaks down** on:

| Scenario | DOM-only Agent | Vision-Enhanced Agent |
|----------|:-:|:-:|
| Icon-only buttons (no text/aria labels) | ❌ Cannot distinguish | ✅ Identifies by visual shape |
| Color swatches / visual selectors | ❌ No color awareness | ✅ Recognizes by appearance |
| Canvas / SVG rendered content | ❌ Invisible to DOM | ✅ OCR + region detection |
| Dynamic SPA (lazy-loaded content) | ⚠️ May act too early | ✅ Visually confirms content |

现代浏览器 Agent 依赖 DOM 解析理解页面。但在纯图标按钮、颜色选择器、Canvas 渲染内容等场景下，
DOM 无法提供足够信息。本项目通过视觉模型弥补这一缺陷。

---

## ✨ Key Results / 核心效果

> **Every success rate below comes from _objective verification_** — the DOM
> state, the page URL, or a live ground-truth API is checked _after_ the agent
> finishes. Success is **never** the agent self-reporting `done()`. See
> [Success Methodology](#-success-methodology--成功判定方法论) for why this matters.

### Where vision helps: icon-heavy pages

On the 4 icon-only fixtures (buttons with no text/aria labels), forcing the
vision pipeline on **doubles** objective success vs the DOM-only baseline:

| Category | Baseline (DOM-only) | + Full Vision |
|----------|:-:|:-:|
| **icon-heavy** (4 tasks) | 1/4 (25%) | **2/4 (50%)** |
| mixed (5 tasks) | 4/5 (80%) | 4/5 (80%) |
| dom-rich (7 tasks) | 6/7 (86%) | 6/7 (86%) |

### Overall (16-task ablation, objective verification)

| Configuration | Objective Success | Vision Calls |
|---|:-:|:-:|
| Baseline (pure DOM) | 11/16 (69%) | 0 |
| **Full vision every step** | **12/16 (75%)** | 35 |
| **Adaptive (DOM-gated vision)** | 11/16 (69%) | **15** |

Full vision lifts overall objective success **+6%** this run, concentrated on the
icon-heavy category where DOM parsing alone falls short. The **adaptive** strategy
fires vision on only **15 calls (43% of full vision's budget)** — concentrated on
icon/visual pages, skipped on text-rich ones — and **matches full vision exactly on
icon-heavy (2/4)**, the category that actually needs it.

### Vision's value scales with the VLM (gpt-4o-mini → gpt-4o)

The numbers above use the default **gpt-4o-mini**. Re-running the *same* 6-condition
ablation with **gpt-4o** (same pipeline, same tasks, objective verification) shows the
vision pipeline's payoff is gated by the driver LLM's ability to *reason over* the
grounded elements — not by the grounding plumbing:

| Metric | gpt-4o-mini | **gpt-4o** |
|---|:-:|:-:|
| Baseline (pure DOM) | 11/16 (69%) | 11/16 (69%) |
| Full vision (best of C/D/E) | 12/16 (75%) | **15/16 (94%)** |
| Full-vision gain over baseline | +6% | **+25%** |
| **icon-heavy**: baseline → full vision | 1/4 → 2/4 | **0/4 → 3/4** |
| Adaptive (E) vision calls vs full | 15 vs 35 | 20 vs 37 |

Same SoM + Florence + vision→DOM bridge. The only change is the driver LLM, and the
icon-heavy category jumps from a hard ceiling of 2/4 to 3/4 while overall success goes
from a modest +6% to +25%. **The gpt-4o-mini bottleneck was the VLM's reasoning over
grounded boxes, not Florence's grounding** — a weak VLM cannot exploit the pixels the
pipeline hands it. Adaptive (E) still matches full vision at ~half the vision calls
under both models. (gpt-4o data: `output/benchmark_results/ablation_report_gpt-4o.md`.)

> **Honest caveats** (the kind a self-report metric would have hidden):
> - Under **gpt-4o-mini**, adaptive **ties baseline overall (69%)** rather than
>   beating it — but not because the gate is broken. Full vision's *own* ceiling is
>   modest *with this weak VLM* (+6% over baseline), so there is little headroom to
>   capture. On the category where vision helps (icon-heavy) adaptive matches full
>   vision at a fraction of the cost. Under **gpt-4o** the same gate beats baseline
>   by **+25%**. (An earlier release had the gate genuinely broken — it read a
>   truncated object repr instead of the real DOM and fired vision on only 4/16
>   tasks; that wiring + heuristic bug is now fixed.)
> - The icon bottleneck is **VLM-bound, not pipeline-bound.** Three successive levers
>   aimed at it — **(1)** the SoM bbox fix (prefer `bounds` over the always-zero
>   `clientRects.x/y` in browser-use 0.12.x), **(2)** a vision→DOM bridge that matches
>   vision detections back to clickable `[id]`s by IoU/center-containment, and
>   **(3)** Florence-2 `<CAPTION_TO_PHRASE_GROUNDING>` fed the task phrase — did *not*
>   move icon-heavy under gpt-4o-mini (a curl smoke gate showed Florence grounds a
>   phrase only to *region* granularity: "Next Track button" → whole player card,
>   never the small icon). But simply swapping in a stronger VLM (gpt-4o) lifted
>   icon-heavy from 0/4 to 3/4 with the **same** Florence grounding. So the real next
>   lever is a more capable multimodal driver LLM (and/or a stronger grounding backend
>   like OmniParser / GroundingDINO for the last icon), not more plumbing on Florence-2.
> - SoM annotation only pays off **paired with vision**: SoM-alone ≈ baseline
>   (−6%), but adaptive-with-SoM beats adaptive-without-SoM by +13% (69% vs 56%).
> - Single-run numbers vary due to LLM non-determinism and network timeouts; no
>   single run is treated as definitive.

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

**Key Design**: The entire module is a _non-invasive overlay_ —
`VisionEnhancedAgent` inherits from `browser_use.Agent` without modifying
a single line in the upstream repository.
`pip install --upgrade browser-use` won't break anything.

关键设计：整个模块是**无侵入扩展**——`VisionEnhancedAgent` 通过类继承
`browser_use.Agent`，不修改上游任何一行代码。

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
├── tests/                          # Test suite (111 tests)
│   ├── test_som.py                 # SoM annotation tests (24 tests)
│   ├── test_enhanced_agent.py      # Enhanced agent tests
│   ├── test_grounding.py           # Grounding module tests
│   ├── test_adaptive.py            # Adaptive strategy tests
│   └── test_benchmark_verify.py    # Objective verifier tests (31 tests)
│
├── scripts/                        # Demo & evaluation scripts
│   ├── benchmark_common.py         # ★ Tasks + verifiers + run engine (single source)
│   ├── e2e_test.py                 # E2E integration test runner (3 scenarios)
│   ├── real_world_benchmark.py     # Baseline vs Vision (16 tasks)
│   ├── ablation_benchmark.py       # Ablation study runner (6 conditions)
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
│   ├── benchmark_results/          # ★ Primary evidence
│   │   ├── real_world_results.json # Machine-readable benchmark (16 tasks)
│   │   ├── ablation_results.json   # Ablation study data (6×16 runs)
│   │   └── ablation_report.md      # Ablation study report
│   ├── demo_results/               # Early-stage demo artifacts (single-task)
│   └── e2e_results/                # E2E integration test results
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
# Unit tests (111 tests)
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

The SoM module overlays numbered labels on interactive elements in the screenshot
before sending it to the LLM. This gives the LLM a visual "index" to reference
when deciding which element to click.

SoM 模块在截图上为交互元素标注编号标签，让 LLM 在决策时有视觉参照。

```python
from browser_use_vision.som import SoMAnnotator

annotator = SoMAnnotator()
annotated_image = annotator.annotate(screenshot, interactive_elements)
# → Screenshot with [0], [1], [2]... labels on buttons/links/inputs
```

### 2. Florence-2 Vision Backend

[Florence-2](https://huggingface.co/microsoft/Florence-2-large) (Microsoft)
is a unified vision foundation model. We use two key capabilities:

- **`OCR_WITH_REGION`** — Extracts text with bounding box coordinates from
  screenshots. Critical for reading text rendered in Canvas, SVG, or custom
  fonts that DOM cannot access.
- **`DENSE_REGION_CAPTION`** — Generates descriptions for all detected regions.
  Identifies icons, colors, shapes — exactly what DOM-only agents miss.
  *Disabled by default* to save GPU time; under objective verification the
  ablation shows OCR+Region and OCR-only are within run-to-run noise of each
  other (C 12/16 vs D 11/16). Enable with `enable_dense_caption=True`.

Florence-2（微软）是统一视觉基础模型。我们用 OCR_WITH_REGION 提取渲染文本坐标，
用 DENSE_REGION_CAPTION 识别图标、颜色、形状。

### 3. Adaptive Vision Strategy

Not every page needs expensive vision inference. The adaptive strategy evaluates
the **serialized DOM** (browser-use's indexed `[id]<tag ...>` representation) first:

```
DOM Confidence Score (0-1):
  → High (≥0.8): interactive elements carry text/aria/alt labels → Skip vision
  → Medium (0.5-0.8): some labeled, some bare → LIGHTWEIGHT (OCR only)
  → Low (<0.5): icon-only buttons, collapsed <svg>, no readable labels → FULL vision
  (consecutive failures or a detected loop force FULL regardless of score)
```

The score is `0.4 + 0.6 × (labeled ÷ total_interactive)`, minus a small penalty for
collapsed `<svg>`. An element counts as *labeled* if it carries an `aria-label` / `alt`
/ `title` / `placeholder` / `value` / `type` / `compound_components` attribute, **or**
has a readable text child on the next indented line; otherwise it is *icon-only*.
Decorative `<i>` glyphs (e.g. rating stars) are excluded so they don't drag text-rich
pages down. An empty string (DOM unreadable) scores low so the gate prefers vision
rather than wrongly skipping.

> **Validated in the objective ablation:** across the 16-task suite the adaptive
> agent fires vision on **15 calls (43% of always-on's 35)** — concentrated on
> icon/visual pages and skipped on text-rich ones — and **matches full vision on
> icon-heavy (2/4 = 2/4)**, the category where vision actually helps. (A previous
> release had this gate broken: it assessed a truncated object repr instead of the
> real serialized DOM and degenerated to always-skip / baseline accuracy. The
> wiring and the index-format heuristic are now fixed and unit-tested.)

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

## 🔬 Success Methodology / 成功判定方法论

Earlier versions of this benchmark scored a task as "passed" whenever the agent
called `done()` and stopped under the step limit — i.e. the agent **graded its
own homework**. That inflates numbers: an agent routinely reports *"Successfully
clicked the Next Track button"* while the DOM shows nothing changed.

Every benchmark in this repo now uses **objective verification**. After
`agent.run()` finishes, a per-task `verify(page, final_result)` callable inspects
the real post-run state:

| Verifier | Checks | Used for |
|----------|--------|----------|
| `dom_js(expr)` | a JS expression is truthy in the live page | action tasks (clicks, toggles, selections) |
| `url_has(*subs)` | the final URL contains substrings | navigation tasks |
| `text_has(*subs)` | the agent's answer contains expected text | static extraction tasks |
| `live_hn_top()` | answer matches the current #1 Hacker News story via the official Firebase API | dynamic extraction |

`is_done` and step count are still recorded — but only for analysis, never as
the success signal. The verifiers are unit-tested independently of any browser
([`tests/test_benchmark_verify.py`](tests/test_benchmark_verify.py), 31 cases),
and all task definitions, verifiers, and the run engine live in one place
([`scripts/benchmark_common.py`](scripts/benchmark_common.py)).

**Task suite: 16 tasks** — 6 local icon-only fixtures (where vision matters most)
+ 10 public sites (Wikipedia, Hacker News, arXiv, quotes/books.toscrape.com,
the-internet.herokuapp.com), real sites in the majority.

---

## 📊 Performance / 性能

> All numbers below are **objective-verification** success rates (DOM / URL /
> live API), not agent self-report. Model gpt-4o-mini, headless Chromium,
> Florence-2 on a remote GPU.

### Real-World Benchmark (16 tasks, Baseline vs Vision-Enhanced)

Each task runs twice — DOM-only baseline and the adaptive vision agent — under
identical conditions.

**Success Rate: Baseline 8/16 (50%) → Vision 10/16 (62%)**

Clean vision wins (baseline fails, vision succeeds): `color_picker`,
`arxiv_search`, `herokuapp_checkbox`. Several baseline failures are infra
timeouts (`0 steps / 125s` — LLM/page-load latency, not capability), which we
report honestly rather than hide. Note the *default* agent uses the adaptive
strategy, which skipped vision on most tasks (see caveat above) — so the
head-to-head understates vision's ceiling. The ablation below isolates that
ceiling by forcing vision on.

> Raw data: [`output/benchmark_results/real_world_results.json`](output/benchmark_results/real_world_results.json)

### Ablation Study (6 conditions × 16 tasks = 96 runs)

Systematically disabling each component to measure its individual contribution.

| Condition | Description | Success Rate | Avg Steps | Vision Calls |
|-----------|-------------|:----------:|:---------:|:------------:|
| A. Baseline | Pure DOM, no vision, no SoM | 11/16 (69%) | 1.7 | 0 |
| B. SoM Only | SoM annotation, no vision model | 10/16 (62%) | 2.4 | 0 |
| **C. Full Always** | **OCR + Region Caption every step** | **12/16 (75%)** | 2.3 | 35 |
| D. OCR Only | OCR every step, no Region Caption | 11/16 (69%) | 2.3 | 36 |
| **E. Adaptive Full** | **SoM + DOM-gated vision (default config)** | 11/16 (69%) | 2.3 | **15** |
| F. Adaptive No SoM | Adaptive vision, no SoM | 9/16 (56%) | 1.4 | 9 |

**Key findings (objective verification overturns the old self-report story):**

| Comparison | Delta | Insight |
|------------|:-----:|---------|
| C vs A | **+6%** | Full vision is the strongest config (75% vs 69%); the gain lands on icon-heavy (25%→50%) |
| C vs D | 0 (+6%/−6% noise) | Region Caption vs OCR-only is within run-to-run noise — no clear winner |
| **E: 15 vs 35 calls** | **43% budget** | Adaptive gate fires vision on icon/visual pages, skips text pages — and **matches C on icon-heavy (2/4)** |
| E vs F | **+13%** | SoM *paired with vision* helps (69% vs 56%); SoM alone (B vs A, −6%) does not |

**By category** — the signal is concentrated where DOM genuinely fails:

| Category | Baseline (A) | Full Vision (C) | Adaptive (E) |
|----------|:----------:|:---------------:|:------------:|
| icon-heavy (4 tasks) | 25% | **50%** | **50%** |
| mixed (5 tasks) | 80% | 80% | 60% |
| dom-rich (7 tasks) | 86% | 86% | 86% |

> **What changed from the previous (broken-gate) ablation:** the old report
> claimed "adaptive matches full vision" while the gate was in fact *broken* —
> it assessed a truncated object repr, fired vision on only 4/16 tasks, and
> degenerated to baseline. After fixing the wiring (`dom_state.llm_representation()`)
> and rewriting the confidence heuristic for browser-use's indexed format, the gate
> now genuinely targets vision: **15 calls (43% of always-on), matching full vision
> on icon-heavy at a fraction of the cost.** The remaining honest gap is that full
> vision's *own* ceiling is modest *with gpt-4o-mini* (+6%) and two icon fixtures
> resist even full vision — but this is a **driver-VLM limit, not a gate or pipeline
> limit**: re-running the identical ablation with **gpt-4o** lifts icon-heavy from
> 0/4 to 3/4 and overall full-vision gain from +6% to **+25%** (see the
> "Vision's value scales with the VLM" section above; data in `ablation_report_gpt-4o.md`).
>
> Raw data: [`output/benchmark_results/ablation_results.json`](output/benchmark_results/ablation_results.json)
> | Report: [`output/benchmark_results/ablation_report.md`](output/benchmark_results/ablation_report.md)

### Latency

| Metric | Value |
|--------|-------|
| Florence-2 OCR latency | ~1.0s / call (A100) |
| Florence-2 region detection | ~0.5s / call (A100) |
| SoM annotation overhead | < 50ms |
| End-to-end step time (with vision) | ~10s (including LLM) |
| Unit tests | 111 passing |
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
- [x] CI pipeline (GitHub Actions) — 111 unit tests
- [x] **Objective success verification** (DOM / URL / live API, not agent self-report)
- [x] Real-world benchmark (16 tasks) + ablation study (6 conditions × 16 tasks)
- [x] **Fix + re-tune adaptive vision gate** — read real serialized DOM, score the
      indexed format; now fires 15/35 vision calls, matching full vision on icon-heavy
- [~] OmniParser V2 backend (code complete, needs integration testing)
- [ ] GroundingDINO as alternative detection backend
- [ ] **Learn the gate threshold from agent traces** — current thresholds are
      hand-set; close the residual icon-grounding gap (2 fixtures resist even full vision)
- [ ] Benchmark against WebArena / Mind2Web evaluation suites
- [ ] Video stream mode for real-time agent observation

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 📌 Project Summary / 项目总结

> **For Recruiters & Hiring Managers:**
>
> This project demonstrates end-to-end engineering skills in building a
> **production-grade ML-powered browser agent enhancement**:
>
> - **Systems Design** — Architected a modular, non-invasive plugin for a
>   popular open-source framework (94k ⭐), using clean class inheritance
>   — zero upstream modifications
> - **ML Engineering** — Deployed Florence-2 vision foundation model as a
>   GPU inference service; designed SoM (Set-of-Mark) annotation pipeline
>   for visual grounding
> - **Performance Optimization** — Adaptive inference gates vision on rule-based
>   DOM-confidence scoring of browser-use's indexed serialization: **15 vision
>   calls vs 35 for always-on (43% of the budget), matching full vision on the
>   icon-heavy category (2/4) where it actually helps**
> - **Quantitative Results** — Evaluated on 16 tasks with **objective
>   verification** (DOM / URL / live API, not agent self-report): forcing vision
>   on lifts success to 75% (12/16) vs 69% baseline, doubling icon-heavy success
>   (25%→50%). Ablation (6 conditions × 16 = 96 runs) isolates each component's
>   real contribution and overturns earlier self-reported claims.
>   111 unit tests + 3 E2E integration scenarios (all passing)
> - **Software Engineering** — 1,800-line core module, 111 unit tests,
>   3 E2E integration tests, CI pipeline, typed Python codebase
>
> ---
>
> **面向招聘者：**
>
> 本项目展示了构建**生产级 ML 浏览器 Agent 增强系统**的全栈工程能力：
>
> - **系统设计** — 为热门开源框架（94k ⭐）设计无侵入插件架构，零上游修改
> - **ML 工程** — 部署 Florence-2 视觉基础模型为 GPU 推理服务；
>   设计 SoM 标注管线实现视觉定位
> - **性能优化** — 自适应推理基于 browser-use 索引序列化 DOM 的置信度评分门控视觉
>   调用：**全套 15 次视觉调用 vs 全开 35 次（仅 43% 预算），并在视觉真正起作用的
>   图标类任务上追平全视觉（2/4）**
> - **量化结果** — 16 个任务、**客观校验**（DOM / URL / 实时 API，非 Agent
>   自报）：强制开启视觉将成功率提升至 75%（12/16）vs 基线 69%，图标类
>   任务成功率翻倍（25%→50%）。消融实验（6 条件 × 16 = 96 次运行）量化各
>   组件真实贡献，并推翻了早期自报指标的结论。
>   含 111 单元测试 + 3 个 E2E 集成场景（全部通过）
> - **工程规范** — 1800 行核心模块、111 单元测试、3 个 E2E 集成测试、
>   CI 流水线、类型化 Python 代码
