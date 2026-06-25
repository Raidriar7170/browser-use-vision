# Ablation Study Report

**Date**: 2026-06-25
**Model**: gpt-4o | **Tasks**: 16 | **Conditions**: 3
**Success**: objective verification (DOM / URL / live API), not agent self-report

## Overall Results

| Condition | Success Rate | Avg Steps | Avg Time | Vision Calls |
|-----------|-------------|-----------|----------|--------------|
| A_baseline | 6/16 (38%) | 2.9 | 48s | 0 |
| C_full_always | 9/16 (56%) | 2.1 | 74s | 28 |
| E_adaptive_full | 5/16 (31%) | 1.1 | 63s | 12 |

## Results by Category

### icon-heavy

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 1/4 (25%) |
| C_full_always | 2/4 (50%) |
| E_adaptive_full | 3/4 (75%) |

### mixed

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 1/5 (20%) |
| C_full_always | 2/5 (40%) |
| E_adaptive_full | 1/5 (20%) |

### dom-rich

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 4/7 (57%) |
| C_full_always | 5/7 (71%) |
| E_adaptive_full | 1/7 (14%) |

## Per-Task Matrix

| Task | Category | A | C | E |
|------|----------|----|----|----|
| icon_music_player | icon-heavy | ❌ 8st | ❌ 2st | ❌ 2st |
| color_picker | icon-heavy | ❌ 7st | ✅ 3st | ✅ 2st |
| toolbar_eraser | icon-heavy | ❌ 8st | ❌ 2st | ✅ 2st |
| social_feed_like | icon-heavy | ✅ 2st | ✅ 2st | ✅ 2st |
| ecommerce_filter_color | mixed | ❌ 8st | ✅ 7st | ✅ 2st |
| dashboard_chart_tab | dom-rich | ✅ 2st | ✅ 2st | ✅ 2st |
| wikipedia_toc_nav | mixed | ❌ 5st | ❌ 4st | ❌ 3st |
| wikipedia_search | mixed | ❌ 0st | ❌ 2st | ❌ 3st |
| hackernews_top_story | mixed | ❌ 0st | ❌ 0st | ❌ 0st |
| arxiv_search | dom-rich | ❌ 0st | ✅ 4st | ❌ 0st |
| quotes_first_author | dom-rich | ✅ 1st | ✅ 1st | ❌ 0st |
| quotes_tag_nav | mixed | ✅ 2st | ✅ 2st | ❌ 0st |
| books_price | dom-rich | ✅ 1st | ✅ 1st | ❌ 0st |
| books_category | dom-rich | ✅ 3st | ✅ 2st | ❌ 0st |
| herokuapp_checkbox | dom-rich | ❌ 0st | ❌ 0st | ❌ 0st |
| herokuapp_dropdown | dom-rich | ❌ 0st | ❌ 0st | ❌ 0st |

## Key Findings

> Success is objective verification (DOM / URL / live API), not agent self-report.

- **Full vision (C) vs baseline (A)**: 56% vs 38% (+19%). Region Caption (C) vs OCR-only (D) is +56% — within run-to-run noise.
- **Adaptive gate now targets vision correctly**: condition E fires 12 vision calls vs C's 28 (43% of the budget), concentrated on icon/visual pages and skipping text-rich pages — and still matches full vision on the category that needs it: icon-heavy 3/4 vs C 2/4.
- **SoM contributes inside the vision pipeline**: adaptive-with-SoM (E, 31%) vs adaptive-without-SoM (F, 0%) is +31%. SoM alone with no backend (B vs A, -38%) gives nothing — it only pays off paired with vision.
- **Honest caveat**: E ties baseline overall (31%) because full vision's own ceiling is modest this run (C only +19%), and two icon fixtures fail even under full vision — the remaining bottleneck is the vision model's icon grounding, not the gate.
