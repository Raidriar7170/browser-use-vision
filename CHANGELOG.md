# Changelog

## v0.1.0 (2026-05-21)

### 🎉 Initial Release

**Core Features**
- `VisionEnhancedAgent` — drop-in replacement for browser-use Agent with vision capabilities
- Florence-2 vision backend — OCR + Dense Region Caption via remote GPU API
- Set-of-Mark (SoM) screenshot annotation — numbered labels on interactive elements
- Adaptive vision strategy — DOM confidence scoring to skip unnecessary vision calls (~50% GPU savings)
- Vision API server (FastAPI) for GPU inference deployment

**Testing & Quality**
- 72 unit tests + 3 E2E integration tests
- GitHub Actions CI (test + lint), all green
- Core module coverage: 67-95%
- ruff linting, typed Python codebase

**Benchmark Results**
- Real-world benchmark: 6 tasks across icon-heavy / mixed / DOM-rich websites
- Vision-enhanced: **100% success rate (6/6)**
- Baseline (DOM-only): 67% success rate (4/6)
- Vision wins 4/6, baseline wins 1/6, ties 1/6

**Architecture**
- Zero upstream modification — pure inheritance from browser-use Agent
- Pluggable backend interface (`VisualGroundingBackend`)
- Graceful degradation when vision service unavailable
