# Ablation Study Report

**Date**: 2026-06-25
**Model**: gpt-4o | **Tasks**: 16 | **Conditions run**: 3
**Success**: objective verification (DOM / URL / live API), not agent self-report
**Rows**: benchmark attempts; infra failures are not counted as completed agent executions.

## Overall Results

| Condition | Status | Attempts | Success Rate | Completion Rate | Infra Failures | Zero-Step | Avg Steps | Avg Time | Vision Calls |
|-----------|--------|---------:|-------------|-----------------|---------------:|----------:|-----------|----------|--------------|
| A_baseline | run | 16 | 25% | 25% | 12 | 12 | 0.4 | 31s | 0 |
| B_som_only | not run | not run | not run | not run | 0 | 0 | not run | not run | not run |
| C_full_always | run | 16 | 31% | 44% | 9 | 7 | 1.6 | 77s | 14 |
| D_ocr_only | not run | not run | not run | not run | 0 | 0 | not run | not run | not run |
| E_adaptive_full | run | 16 | 31% | 62% | 6 | 5 | 2.6 | 90s | 18 |
| F_adaptive_no_som | not run | not run | not run | not run | 0 | 0 | not run | not run | not run |

## Results by Category

### icon-heavy

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 0/4 (0%) |
| B_som_only | not run |
| C_full_always | 2/4 (50%) |
| D_ocr_only | not run |
| E_adaptive_full | 1/4 (25%) |
| F_adaptive_no_som | not run |

### mixed

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 1/5 (20%) |
| B_som_only | not run |
| C_full_always | 2/5 (40%) |
| D_ocr_only | not run |
| E_adaptive_full | 0/5 (0%) |
| F_adaptive_no_som | not run |

### dom-rich

| Condition | Success Rate |
|-----------|-------------|
| A_baseline | 3/7 (43%) |
| B_som_only | not run |
| C_full_always | 1/7 (14%) |
| D_ocr_only | not run |
| E_adaptive_full | 4/7 (57%) |
| F_adaptive_no_som | not run |

## Per-Task Matrix

| Task | Category | A | B | C | D | E | F |
|------|----------|----|----|----|----|----|----|
| icon_music_player | icon-heavy | ❌ 0st | not run | ❌ 2st | not run | ❌ 8st | not run |
| color_picker | icon-heavy | ❌ 0st | not run | ✅ 2st | not run | ❌ 3st | not run |
| toolbar_eraser | icon-heavy | ❌ 0st | not run | ❌ 2st | not run | ✅ 2st | not run |
| social_feed_like | icon-heavy | ❌ 0st | not run | ✅ 2st | not run | ❌ 7st | not run |
| ecommerce_filter_color | mixed | ❌ 0st | not run | ✅ 2st | not run | ❌ 8st | not run |
| dashboard_chart_tab | dom-rich | ❌ 0st | not run | ✅ 2st | not run | ✅ 2st | not run |
| wikipedia_toc_nav | mixed | ❌ 0st | not run | ❌ 4st | not run | ❌ 4st | not run |
| wikipedia_search | mixed | ❌ 0st | not run | ❌ 7st | not run | ❌ 2st | not run |
| hackernews_top_story | mixed | ❌ 0st | not run | ❌ 0st | not run | ❌ 0st | not run |
| arxiv_search | dom-rich | ❌ 0st | not run | ❌ 0st | not run | ✅ 3st | not run |
| quotes_first_author | dom-rich | ✅ 1st | not run | ❌ 0st | not run | ❌ 0st | not run |
| quotes_tag_nav | mixed | ✅ 2st | not run | ✅ 2st | not run | ❌ 0st | not run |
| books_price | dom-rich | ✅ 1st | not run | ❌ 0st | not run | ✅ 1st | not run |
| books_category | dom-rich | ✅ 2st | not run | ❌ 0st | not run | ✅ 2st | not run |
| herokuapp_checkbox | dom-rich | ❌ 0st | not run | ❌ 0st | not run | ❌ 0st | not run |
| herokuapp_dropdown | dom-rich | ❌ 0st | not run | ❌ 0st | not run | ❌ 0st | not run |

## Key Findings

> Success is objective verification (DOM / URL / live API), not agent self-report.

- **Full vision (C) vs baseline (A)**: 31% vs 25% (+6%) across the conditions that were actually run.
- **Adaptive full (E) vs baseline (A)**: 31% vs 25% (+6%); icon-heavy outcomes were E 1/4 vs A 0/4.
- **Vision budget**: E used 18 vision calls vs C's 14 (129% of C); icon-heavy outcomes were E 1/4 vs C 2/4.
- **Not run**: B_som_only, D_ocr_only, F_adaptive_no_som. These conditions are excluded from comparisons.
- **Failure attribution**: this report records typed failures, but it does not claim that all remaining failures come from the vision model rather than the gate, browser, LLM, verifier, or service layer.
