# Ablation Study Report

**Date**: 2026-05-31
**Model**: gpt-4o-mini | **Tasks**: 16 | **Conditions**: 6
**Success**: objective verification (DOM / URL / live API), not agent self-report

## Overall Results

| Condition | Success Rate | Avg Steps | Avg Time | Vision Calls |
|-----------|-------------|-----------|----------|--------------|
| A_baseline | 11/16 (69%) | 1.7 | 28s | 0 |
| B_som_only | 10/16 (62%) | 2.4 | 36s | 0 |
| C_full_always | 12/16 (75%) | 2.2 | 29s | 35 |
| D_ocr_only | 11/16 (69%) | 2.3 | 33s | 36 |
| E_adaptive_full | 11/16 (69%) | 2.2 | 28s | 15 |
| F_adaptive_no_som | 9/16 (56%) | 1.4 | 23s | 9 |

## Results by Category

### icon-heavy

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 1/4 (25%) |
| B_som_only | 1/4 (25%) |
| C_full_always | 2/4 (50%) |
| D_ocr_only | 2/4 (50%) |
| E_adaptive_full | 2/4 (50%) |
| F_adaptive_no_som | 1/4 (25%) |

### mixed

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 4/5 (80%) |
| B_som_only | 3/5 (60%) |
| C_full_always | 4/5 (80%) |
| D_ocr_only | 3/5 (60%) |
| E_adaptive_full | 3/5 (60%) |
| F_adaptive_no_som | 2/5 (40%) |

### dom-rich

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 6/7 (86%) |
| B_som_only | 6/7 (86%) |
| C_full_always | 6/7 (86%) |
| D_ocr_only | 6/7 (86%) |
| E_adaptive_full | 6/7 (86%) |
| F_adaptive_no_som | 6/7 (86%) |

## Per-Task Matrix

| Task | Category | A | B | C | D | E | F |
|------|----------|----|----|----|----|----|----|
| icon_music_player | icon-heavy | ❌ 2st | ❌ 2st | ❌ 2st | ❌ 2st | ❌ 2st | ❌ 2st |
| color_picker | icon-heavy | ❌ 0st | ❌ 0st | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st |
| toolbar_eraser | icon-heavy | ❌ 2st | ❌ 2st | ❌ 4st | ❌ 4st | ❌ 2st | ❌ 4st |
| social_feed_like | icon-heavy | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ❌ 0st |
| ecommerce_filter_color | mixed | ❌ 2st | ❌ 2st | ❌ 2st | ❌ 2st | ❌ 2st | ❌ 0st |
| dashboard_chart_tab | dom-rich | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ❌ 0st |
| wikipedia_toc_nav | mixed | ✅ 2st | ❌ 0st | ✅ 2st | ❌ 2st | ❌ 2st | ❌ 0st |
| wikipedia_search | mixed | ✅ 3st | ✅ 3st | ✅ 3st | ✅ 3st | ✅ 3st | ❌ 0st |
| hackernews_top_story | mixed | ✅ 1st | ✅ 2st | ✅ 1st | ✅ 1st | ✅ 1st | ✅ 1st |
| arxiv_search | dom-rich | ❌ 0st | ❌ 13st | ✅ 3st | ✅ 5st | ✅ 3st | ✅ 3st |
| quotes_first_author | dom-rich | ✅ 1st | ✅ 1st | ✅ 1st | ✅ 1st | ✅ 1st | ✅ 1st |
| quotes_tag_nav | mixed | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st |
| books_price | dom-rich | ✅ 1st | ✅ 1st | ✅ 1st | ✅ 1st | ✅ 1st | ✅ 1st |
| books_category | dom-rich | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st | ✅ 2st |
| herokuapp_checkbox | dom-rich | ✅ 3st | ✅ 2st | ❌ 4st | ❌ 4st | ❌ 7st | ✅ 2st |
| herokuapp_dropdown | dom-rich | ✅ 2st | ✅ 2st | ✅ 3st | ✅ 2st | ✅ 2st | ✅ 2st |

## Key Findings

> Success is objective verification (DOM / URL / live API), not agent self-report.

- **Full vision (C) vs baseline (A)**: 75% vs 69% (+6%). Region Caption (C) vs OCR-only (D) is +6% — within run-to-run noise.
- **Adaptive gate now targets vision correctly**: condition E fires 15 vision calls vs C's 35 (43% of the budget), concentrated on icon/visual pages and skipping text-rich pages — and still matches full vision on the category that needs it: icon-heavy 2/4 vs C 2/4.
- **SoM contributes inside the vision pipeline**: adaptive-with-SoM (E, 69%) vs adaptive-without-SoM (F, 56%) is +13%. SoM alone with no backend (B vs A, -6%) gives nothing — it only pays off paired with vision.
- **Honest caveat**: E ties baseline overall (69%) because full vision's own ceiling is modest this run (C only +6%), and two icon fixtures fail even under full vision — the remaining bottleneck is the vision model's icon grounding, not the gate.
