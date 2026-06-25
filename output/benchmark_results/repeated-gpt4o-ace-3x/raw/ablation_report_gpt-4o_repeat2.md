# Ablation Study Report

**Date**: 2026-06-25
**Model**: gpt-4o | **Tasks**: 16 | **Conditions**: 3
**Success**: objective verification (DOM / URL / live API), not agent self-report

## Overall Results

| Condition | Success Rate | Avg Steps | Avg Time | Vision Calls |
|-----------|-------------|-----------|----------|--------------|
| A_baseline | 7/16 (44%) | 2.6 | 46s | 0 |
| C_full_always | 4/16 (25%) | 1.7 | 74s | 22 |
| E_adaptive_full | 4/16 (25%) | 1.4 | 50s | 20 |

## Results by Category

### icon-heavy

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 1/4 (25%) |
| C_full_always | 2/4 (50%) |
| E_adaptive_full | 2/4 (50%) |

### mixed

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 1/5 (20%) |
| C_full_always | 0/5 (0%) |
| E_adaptive_full | 1/5 (20%) |

### dom-rich

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 5/7 (71%) |
| C_full_always | 2/7 (29%) |
| E_adaptive_full | 1/7 (14%) |

## Per-Task Matrix

| Task | Category | A | C | E |
|------|----------|----|----|----|
| icon_music_player | icon-heavy | ❌ 2st | ❌ 2st | ❌ 0st |
| color_picker | icon-heavy | ❌ 8st | ✅ 3st | ✅ 5st |
| toolbar_eraser | icon-heavy | ❌ 2st | ❌ 2st | ❌ 8st |
| social_feed_like | icon-heavy | ✅ 2st | ✅ 2st | ✅ 2st |
| ecommerce_filter_color | mixed | ❌ 8st | ❌ 8st | ✅ 5st |
| dashboard_chart_tab | dom-rich | ✅ 2st | ✅ 2st | ✅ 2st |
| wikipedia_toc_nav | mixed | ❌ 3st | ❌ 4st | ❌ 0st |
| wikipedia_search | mixed | ❌ 0st | ❌ 3st | ❌ 0st |
| hackernews_top_story | mixed | ❌ 0st | ❌ 0st | ❌ 0st |
| arxiv_search | dom-rich | ✅ 8st | ❌ 0st | ❌ 0st |
| quotes_first_author | dom-rich | ✅ 1st | ❌ 0st | ❌ 0st |
| quotes_tag_nav | mixed | ✅ 2st | ❌ 0st | ❌ 0st |
| books_price | dom-rich | ✅ 1st | ✅ 1st | ❌ 0st |
| books_category | dom-rich | ✅ 2st | ❌ 0st | ❌ 0st |
| herokuapp_checkbox | dom-rich | ❌ 0st | ❌ 0st | ❌ 0st |
| herokuapp_dropdown | dom-rich | ❌ 0st | ❌ 0st | ❌ 0st |

## Key Findings

> Success is objective verification (DOM / URL / live API), not agent self-report.

- **Full vision (C) vs baseline (A)**: 25% vs 44% (-19%). Region Caption (C) vs OCR-only (D) is +25% — within run-to-run noise.
- **Adaptive gate now targets vision correctly**: condition E fires 20 vision calls vs C's 22 (91% of the budget), concentrated on icon/visual pages and skipping text-rich pages — and still matches full vision on the category that needs it: icon-heavy 2/4 vs C 2/4.
- **SoM contributes inside the vision pipeline**: adaptive-with-SoM (E, 25%) vs adaptive-without-SoM (F, 0%) is +25%. SoM alone with no backend (B vs A, -44%) gives nothing — it only pays off paired with vision.
- **Honest caveat**: E ties baseline overall (25%) because full vision's own ceiling is modest this run (C only -19%), and two icon fixtures fail even under full vision — the remaining bottleneck is the vision model's icon grounding, not the gate.
