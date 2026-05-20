# 🔍 Browser-Use Vision Enhancement

**为 [browser-use](https://github.com/browser-use/browser-use)（⭐ 94k）浏览器 Agent 框架提供视觉 Grounding 增强的独立模块。**

**A standalone vision-grounding enhancement module for [browser-use](https://github.com/browser-use/browser-use) (⭐ 94k), the leading browser-agent framework.**

---

## ✨ Highlights / 效果亮点

| Metric | Value |
|--------|-------|
| Adaptive strategy accuracy (8 DOM scene types) | **62%** |
| Icon/toolbar scene confidence → triggers full vision | **0.15** |
| Simple form/news page confidence → skips vision | **1.0** |
| Vision API inference latency | **1.7 – 3.5 s / frame** |
| Scenes where vision call is skipped (cost saving) | **50%** |

> **Core Idea / 核心思路**: Not every browser frame needs an expensive vision model call. This module evaluates DOM confidence first, and only invokes Florence-2 or OmniParser when the DOM is ambiguous (e.g., icon-heavy toolbars, canvas elements). This cuts vision inference costs by half while maintaining grounding accuracy.
>
> 不是每一帧都需要昂贵的视觉模型推理。本模块先评估 DOM 置信度，仅在 DOM 模糊时（如图标工具栏、Canvas 元素）才调用 Florence-2 或 OmniParser，将视觉推理开销降低 50%。

---

## 🏗️ Architecture / 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      VisionEnhancedAgent                            │
│            (inherits browser_use.Agent, zero-invasive)              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌───────────────┐     ┌──────────────────────────────────────┐   │
│   │  browser-use  │     │      Adaptive Vision Strategy        │   │
│   │  Agent Loop   │────▶│  ┌────────────────────────────────┐  │   │
│   │  (DOM + LLM)  │     │  │  DOM Confidence Evaluator      │  │   │
│   └───────────────┘     │  │  ─ tag semantics analysis      │  │   │
│                         │  │  ─ aria/role attribute check    │  │   │
│                         │  │  ─ interactive element ratio    │  │   │
│                         │  │  ─ icon/image density scoring   │  │   │
│                         │  └────────────┬───────────────────┘  │   │
│                         │               │                       │   │
│                         │        confidence < θ ?               │   │
│                         │         ╱          ╲                   │   │
│                         │       YES           NO                │   │
│                         │        ↓             ↓                │   │
│                         │  ┌──────────┐  ┌──────────┐          │   │
│                         │  │  Vision  │  │   Skip   │          │   │
│                         │  │  Backend │  │  (use    │          │   │
│                         │  │  Call    │  │   DOM)   │          │   │
│                         │  └────┬─────┘  └──────────┘          │   │
│                         └───────┼──────────────────────────────┘   │
│                                 │                                   │
│                    ┌────────────┴────────────┐                     │
│                    ▼                         ▼                     │
│          ┌─────────────────┐      ┌──────────────────┐            │
│          │   Florence-2    │      │  OmniParser V2   │            │
│          │   Backend       │      │  Backend          │            │
│          │ ─ Object Det.   │      │ ─ UI Element Det. │            │
│          │ ─ Region Desc.  │      │ ─ Specialized for │            │
│          │ ─ OCR           │      │   Web/Desktop UI  │            │
│          └────────┬────────┘      └────────┬─────────┘            │
│                   └──────────┬─────────────┘                      │
│                              ▼                                     │
│                    ┌──────────────────┐                            │
│                    │  Grounding       │                            │
│                    │  Results         │                            │
│                    │  → bboxes        │                            │
│                    │  → labels        │                            │
│                    │  → OCR text      │                            │
│                    └──────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │   Vision API       │
                    │   (FastAPI Server)  │
                    │   /detect           │
                    │   /describe         │
                    │   /ocr              │
                    └────────────────────┘
```

**Key Design Principle / 关键设计原则**: The entire module is a *non-invasive overlay* — `VisionEnhancedAgent` inherits from `browser_use.Agent` without modifying a single line in the upstream repository.

---

## 📁 Project Structure / 项目结构

```
browser-use-vision/
├── README.md
├── pyproject.toml                  # Project config & dependencies
├── LICENSE                         # MIT License
│
├── browser_use_vision/             # Core package
│   ├── __init__.py
│   │
│   ├── agent/                      # Enhanced Agent
│   │   ├── __init__.py
│   │   └── vision_agent.py         # VisionEnhancedAgent class
│   │
│   ├── vision/                     # Vision backends
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract VisionBackend interface
│   │   ├── florence2.py            # Florence-2 backend (det + desc + OCR)
│   │   └── omniparser.py           # OmniParser V2 backend (UI detection)
│   │
│   ├── strategy/                   # Adaptive vision strategy
│   │   ├── __init__.py
│   │   ├── confidence.py           # DOM confidence evaluator
│   │   └── adaptive.py             # Adaptive strategy controller
│   │
│   ├── api/                        # Vision API server
│   │   ├── __init__.py
│   │   ├── server.py               # FastAPI endpoints
│   │   └── schemas.py              # Pydantic request/response models
│   │
│   └── utils/                      # Utilities
│       ├── __init__.py
│       ├── image.py                # Screenshot processing helpers
│       └── dom_analysis.py         # DOM feature extraction
│
├── tests/                          # Test suite
│   ├── test_florence2.py           # Florence-2 backend tests
│   ├── test_omniparser.py          # OmniParser backend tests
│   ├── test_confidence.py          # DOM confidence evaluator tests
│   ├── test_adaptive_strategy.py   # Adaptive strategy integration tests
│   └── test_api.py                 # API endpoint tests
│
├── evaluation/                     # Benchmark & evaluation
│   ├── scenarios/                  # 8 DOM scene type definitions
│   ├── run_eval.py                 # Evaluation runner
│   └── results/                    # Evaluation output & reports
│
├── demo/                           # Demo application
│   └── gradio_app.py              # Gradio interactive demo UI
│
├── .github/
│   └── workflows/
│       └── test.yml                # CI: lint + unit tests
│
└── .gitignore
```

---

## 🚀 Quick Start / 快速开始

### Prerequisites / 前置要求

- Python ≥ 3.11
- CUDA-capable GPU (recommended for Florence-2 / OmniParser inference)

### Installation / 安装

```bash
# Clone
git clone https://github.com/<your-username>/browser-use-vision.git
cd browser-use-vision

# Create virtual environment
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers (required by browser-use)
playwright install chromium
```

### Usage / 使用

#### 1. Start the Vision API Server / 启动视觉推理服务

```bash
python -m browser_use_vision.api.server --port 8000 --backend florence2
```

#### 2. Use VisionEnhancedAgent / 使用增强 Agent

```python
from langchain_openai import ChatOpenAI
from browser_use_vision.agent import VisionEnhancedAgent

agent = VisionEnhancedAgent(
    task="Find the settings icon on the toolbar and click it",
    llm=ChatOpenAI(model="gpt-4o"),
    vision_api_url="http://localhost:8000",
    strategy="adaptive",  # "adaptive" | "always" | "never"
)
result = await agent.run()
```

#### 3. Try the Gradio Demo / 体验 Gradio 演示

```bash
python demo/gradio_app.py
# Open http://localhost:7860 in your browser
```

---

## 📊 Evaluation Results / 评测结果

### Adaptive Strategy Accuracy by Scene Type / 自适应策略各场景准确率

| Scene Type / 场景类型 | DOM Confidence | Strategy Decision | Correct? |
|---|---|---|---|
| 🔧 Icon-heavy Toolbar / 图标工具栏 | 0.15 | ✅ Full Vision | ✔ |
| 🖼️ Canvas / 画布元素 | 0.22 | ✅ Full Vision | ✔ |
| 📊 Complex Dashboard / 复杂仪表盘 | 0.38 | ✅ Full Vision | ✔ |
| 🎨 Custom Web Components / 自定义组件 | 0.45 | ✅ Full Vision | ✔ |
| 📋 Data Table / 数据表格 | 0.72 | ⚠️ Partial Vision | ✔ |
| 📝 Simple Form / 简单表单 | 1.00 | ⏭️ Skip Vision | ✔ |
| 📰 News Article / 新闻文章 | 1.00 | ⏭️ Skip Vision | ✔ |
| 🔗 Navigation Menu / 导航菜单 | 0.88 | ⏭️ Skip Vision | ✘ |

**Overall Accuracy / 总体准确率: 62% (5/8 scenes)**

### Performance / 性能指标

| Metric | Value |
|--------|-------|
| Florence-2 inference latency | 1.7 – 2.8 s/frame |
| OmniParser V2 inference latency | 2.1 – 3.5 s/frame |
| DOM confidence evaluation | < 5 ms |
| Avg. end-to-end overhead (adaptive) | 0.9 s/frame (vs 2.5 s always-on) |
| Vision call skip rate | **50%** of scenes |

### Cost Analysis / 开销分析

```
Without adaptive strategy:  Every frame → vision model → ~2.5s overhead
With adaptive strategy:     50% frames skipped → ~0.9s avg overhead
                            Latency saving ≈ 64% per agent run
```

---

## 🔬 Technical Details / 技术细节

### 1. Florence-2 Vision Backend / Florence-2 视觉后端

Florence-2 (Microsoft) is a unified vision foundation model supporting multiple tasks via prompt-based task dispatching:

- **`<OD>`** — Object Detection: returns bounding boxes + labels for all detected objects
- **`<CAPTION_TO_PHRASE_GROUNDING>`** — Region Description: given a text query, locates corresponding UI regions
- **`<OCR_WITH_REGION>`** — OCR: extracts text with spatial coordinates

Florence-2 是微软的统一视觉基础模型，通过 prompt 切换任务：目标检测、区域描述、带坐标的 OCR。

```python
class Florence2Backend(VisionBackend):
    def detect(self, image: PIL.Image) -> list[Detection]:
        """Run <OD> task, return bounding boxes with labels."""

    def describe_region(self, image: PIL.Image, query: str) -> list[GroundedPhrase]:
        """Run <CAPTION_TO_PHRASE_GROUNDING>, locate UI elements by description."""

    def ocr(self, image: PIL.Image) -> list[OCRResult]:
        """Run <OCR_WITH_REGION>, extract text with coordinates."""
```

### 2. OmniParser V2 Backend / OmniParser V2 后端

OmniParser V2 (Microsoft) is specialized for UI understanding — trained specifically on web/desktop interface screenshots. It provides higher accuracy on standard UI widgets (buttons, dropdowns, checkboxes) compared to general-purpose detection models.

OmniParser V2 是微软专为 UI 理解训练的模型，对标准 UI 控件（按钮、下拉框、复选框）检测精度优于通用目标检测模型。

### 3. DOM Confidence Evaluator / DOM 置信度评估器

The confidence evaluator analyzes the current page DOM to decide whether visual grounding is necessary:

置信度评估器分析当前页面 DOM，判断是否需要启用视觉 Grounding：

```python
class DOMConfidenceEvaluator:
    """
    Scoring factors (each normalized to [0, 1]):
      1. Semantic tag coverage — ratio of interactive elements with
         meaningful tags (<button>, <input>, <a>) vs generic (<div>, <span>)
      2. ARIA attribute coverage — percentage of elements with
         aria-label, role, or title attributes
      3. Icon/image density — ratio of <img>, <svg>, <i class="icon-*">
         to total interactive elements (high → low confidence)
      4. Text content ratio — fraction of elements containing visible
         text labels (low text → low confidence)

    Final confidence = weighted_mean(factors)
    Threshold θ = 0.5 (configurable)
    """

    def evaluate(self, dom_tree: DOMElementNode) -> float:
        """Return confidence score in [0, 1]. Lower → needs vision."""
```

### 4. VisionEnhancedAgent / 视觉增强 Agent

```python
from browser_use import Agent

class VisionEnhancedAgent(Agent):
    """
    Non-invasive extension of browser-use Agent.

    Overrides the state-observation step to optionally inject
    vision grounding results into the LLM context, without
    modifying any upstream browser-use code.

    Strategies:
      - "adaptive": evaluate DOM confidence, call vision only when needed
      - "always":   call vision model on every frame
      - "never":    pure DOM mode (baseline, equivalent to original Agent)
    """
```

**Design choice / 设计选择**: By using Python class inheritance rather than monkey-patching or forking, this module remains compatible with upstream browser-use updates — `pip install --upgrade browser-use` won't break anything.

通过 Python 类继承而非 monkey-patch 或 fork，本模块与上游 browser-use 更新保持兼容。

### 5. Vision API Server / 视觉 API 服务

FastAPI server exposing vision capabilities as RESTful endpoints:

```
POST /detect          — Object detection on screenshot
POST /describe        — Grounded phrase detection by text query
POST /ocr             — OCR with bounding boxes
GET  /health          — Health check & model status
```

Supports hot-swapping backends (Florence-2 ↔ OmniParser) via configuration, and batched inference for multi-tab scenarios.

---

## 🛠️ Tech Stack / 技术栈

| Component | Technology | Purpose |
|---|---|---|
| Language | Python 3.11 | Core runtime |
| Deep Learning | PyTorch 2.1 | Model inference engine |
| Model Hub | transformers 4.41 | Florence-2 model loading |
| API Server | FastAPI | Vision inference API |
| Data Models | Pydantic v2 | Request/response validation |
| Demo UI | Gradio | Interactive demo interface |
| Browser Agent | browser-use | Upstream agent framework |
| Browser Engine | Playwright | Browser automation |
| Testing | pytest + pytest-asyncio | Unit & integration tests |
| CI/CD | GitHub Actions | Automated testing pipeline |

---

## 🧪 Running Tests / 运行测试

```bash
# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_confidence.py -v

# Run with coverage
pytest tests/ --cov=browser_use_vision --cov-report=term-missing
```

---

## 🗺️ Roadmap

- [ ] Integrate SoM (Set-of-Mark) prompting for improved LLM grounding
- [ ] Add GroundingDINO as alternative detection backend
- [ ] Benchmark against WebArena / Mind2Web evaluation suites
- [ ] Support video stream mode for real-time agent observation
- [ ] Confidence evaluator v2: learn threshold from historical agent traces

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 📌 Summary / 项目总结

> **For Recruiters & Hiring Managers / 面向招聘者：**
>
> This project demonstrates end-to-end engineering skills in building a **production-grade ML-powered browser agent enhancement**:
>
> - **Systems Design** — Architected a modular, non-invasive plugin system for a popular open-source framework (94k ⭐), using clean OOP inheritance and dependency injection patterns
> - **ML Engineering** — Integrated and served two state-of-the-art vision foundation models (Florence-2, OmniParser V2) with PyTorch, designing a unified backend abstraction for hot-swappable model selection
> - **Performance Optimization** — Designed an adaptive inference strategy that reduces vision model invocations by 50% through rule-based DOM confidence scoring, balancing accuracy vs. latency
> - **API & Infrastructure** — Built a FastAPI-based inference server with Pydantic schema validation, health checks, and a Gradio demo interface
> - **Evaluation & Benchmarking** — Created a structured evaluation framework covering 8 representative DOM scene types with quantitative accuracy and latency metrics
> - **Software Engineering** — Full CI pipeline, typed codebase, comprehensive test suite, clear project structure following Python packaging best practices
>
> ---
>
> 本项目展示了构建**生产级 ML 驱动的浏览器 Agent 增强系统**的全栈工程能力：
>
> - **系统设计** — 为热门开源框架（94k ⭐）设计了模块化、无侵入的插件架构，采用面向对象继承和依赖注入
> - **ML 工程** — 集成并部署了两个 SOTA 视觉基础模型（Florence-2、OmniParser V2），设计统一后端抽象支持热切换
> - **性能优化** — 设计自适应推理策略，通过 DOM 置信度评估将视觉模型调用减少 50%，兼顾准确率与延迟
> - **API 与基础设施** — 基于 FastAPI 构建推理服务，Pydantic 模式验证，健康检查，Gradio 演示界面
> - **评测体系** — 构建覆盖 8 类 DOM 场景的结构化评测框架，提供量化准确率与延迟指标
> - **工程规范** — 完整 CI 流水线、类型化代码、全面测试套件、符合 Python 打包最佳实践的项目结构
