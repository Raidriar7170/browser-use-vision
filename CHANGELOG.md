# Changelog

## v0.4.0 (2026-05-31)

### 🔬 Objective verification + cross-model VLM-bound finding

This release replaces self-reported success with **objective verification** and
establishes the project's core finding: the icon-grounding bottleneck is
**VLM-bound, not pipeline-bound**.

**Benchmark & methodology**
- **Objective success verification** — every task is graded by a per-task
  `verify(page, result)` callable inspecting real post-run state (DOM JS / final
  URL / live ground-truth API), never the agent self-reporting `done()`.
- **16-task suite** — 6 local icon-only fixtures + 10 public sites (Wikipedia,
  Hacker News, arXiv, quotes/books.toscrape.com, the-internet.herokuapp.com).
- **Ablation study** — 6 conditions (baseline / SoM-only / full-always / OCR-only
  / adaptive-full / adaptive-no-SoM) × 16 tasks, single source of truth in
  `scripts/benchmark_common.py`.

**Core finding — vision's value scales with the VLM**
- Re-running the *identical* SoM + Florence + vision→DOM-bridge pipeline on
  **gpt-4o** (vs the gpt-4o-mini default): icon-heavy **0/4 → 3/4**, overall
  full-vision gain **+6% → +25%** (15/16 vs 11/16 baseline).
- Both models share an identical 69% DOM-only baseline — the gap is the strong VLM
  *using* grounded boxes the weak one ignores. Florence grounding was never the
  ceiling; the driver LLM's reasoning over boxes was.

**Grounding levers (implemented, objectively evaluated)**
- SoM bbox fix — prefer `bounds` over the always-zero `clientRects.x/y` in
  browser-use 0.12.x.
- Vision→DOM bridge — match vision detections back to clickable `[id]`s by
  IoU / center-containment.
- Florence-2 `<CAPTION_TO_PHRASE_GROUNDING>` — deployed and smoke-tested; grounds
  only to *region* granularity, so left unwired to the agent (documented NO-GO).

**Adaptive gate fix**
- Previously assessed a truncated object repr and fired vision on only 4/16 tasks
  (degenerated to baseline). Now reads the real serialized DOM and scores
  browser-use's indexed format — fires 15/35 vision calls, matching full vision on
  icon-heavy.

**Reporting correctness**
- Timeout runs now record real step counts (`agent.history.number_of_steps()`)
  instead of a misleading `steps=0`.
- Non-default models write to model-stamped output files
  (`ablation_results_gpt-4o.json`) so canonical mini data is never clobbered.

**Testing & docs**
- 119 unit tests + 3 E2E integration scenarios (all passing); CI green.
- README leads with the gpt-4o best result; GPU-free quickstart regenerates the
  hero image + results chart locally.

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

**Benchmark Results (superseded by v0.4.0)**
- Early demo benchmark: 6 tasks, self-reported success (agent `done()`), not
  objective verification. The "6/6 / 100%" numbers from this release were inflated
  by self-grading and are **superseded** by the 16-task objectively-verified suite
  in v0.4.0 — see the README for current results.

**Architecture**
- Zero upstream modification — pure inheritance from browser-use Agent
- Pluggable backend interface (`VisualGroundingBackend`)
- Graceful degradation when vision service unavailable
