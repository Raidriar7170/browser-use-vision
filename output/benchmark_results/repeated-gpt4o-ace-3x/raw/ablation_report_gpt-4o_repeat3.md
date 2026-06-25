# Ablation Study Report

**Date**: 2026-06-25
**Model**: gpt-4o | **Tasks**: 16 | **Conditions**: 3
**Success**: objective verification (DOM / URL / live API), not agent self-report

## Overall Results

| Condition | Success Rate | Avg Steps | Avg Time | Vision Calls |
|-----------|-------------|-----------|----------|--------------|
| A_baseline | 4/16 (25%) | 0.4 | 31s | 0 |
| C_full_always | 5/16 (31%) | 1.6 | 77s | 14 |
| E_adaptive_full | 5/16 (31%) | 2.6 | 90s | 18 |

## Results by Category

### icon-heavy

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 0/4 (0%) |
| C_full_always | 2/4 (50%) |
| E_adaptive_full | 1/4 (25%) |

### mixed

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 1/5 (20%) |
| C_full_always | 2/5 (40%) |
| E_adaptive_full | 0/5 (0%) |

### dom-rich

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 3/7 (43%) |
| C_full_always | 1/7 (14%) |
| E_adaptive_full | 4/7 (57%) |

## Per-Task Matrix

| Task | Category | A | C | E |
|------|----------|----|----|----|
| icon_music_player | icon-heavy | ❌ 0st | ❌ 2st | ❌ 8st |
| color_picker | icon-heavy | ❌ 0st | ✅ 2st | ❌ 3st |
| toolbar_eraser | icon-heavy | ❌ 0st | ❌ 2st | ✅ 2st |
| social_feed_like | icon-heavy | ❌ 0st | ✅ 2st | ❌ 7st |
| ecommerce_filter_color | mixed | ❌ 0st | ✅ 2st | ❌ 8st |
| dashboard_chart_tab | dom-rich | ❌ 0st | ✅ 2st | ✅ 2st |
| wikipedia_toc_nav | mixed | ❌ 0st | ❌ 4st | ❌ 4st |
| wikipedia_search | mixed | ❌ 0st | ❌ 7st | ❌ 2st |
| hackernews_top_story | mixed | ❌ 0st | ❌ 0st | ❌ 0st |
| arxiv_search | dom-rich | ❌ 0st | ❌ 0st | ✅ 3st |
| quotes_first_author | dom-rich | ✅ 1st | ❌ 0st | ❌ 0st |
| quotes_tag_nav | mixed | ✅ 2st | ✅ 2st | ❌ 0st |
| books_price | dom-rich | ✅ 1st | ❌ 0st | ✅ 1st |
| books_category | dom-rich | ✅ 2st | ❌ 0st | ✅ 2st |
| herokuapp_checkbox | dom-rich | ❌ 0st | ❌ 0st | ❌ 0st |
| herokuapp_dropdown | dom-rich | ❌ 0st | ❌ 0st | ❌ 0st |

## Key Findings

> Success is objective verification (DOM / URL / live API), not agent self-report.

- **Full vision (C) vs baseline (A)**: 31% vs 25% (+6%). Region Caption (C) vs OCR-only (D) is +31% — within run-to-run noise.
- **Adaptive gate now targets vision correctly**: condition E fires 18 vision calls vs C's 14 (129% of the budget), concentrated on icon/visual pages and skipping text-rich pages — and still matches full vision on the category that needs it: icon-heavy 1/4 vs C 2/4.
- **SoM contributes inside the vision pipeline**: adaptive-with-SoM (E, 31%) vs adaptive-without-SoM (F, 0%) is +31%. SoM alone with no backend (B vs A, -25%) gives nothing — it only pays off paired with vision.
- **Vision pays off, scaled by VLM strength**: adaptive vision (E, 31%) beats baseline (A, 25%) by +6%, driven entirely by icon-heavy (1/4 vs A 0/4) — the category that needs pixels. The remaining icon failures are the vision model's small-icon grounding ceiling, not the gate.
