from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import vision_dom_alignment as align  # noqa: E402


def test_alignment_metrics_include_topk_unmatched_geometry_and_group_breakdowns():
    fixture = {
        "pages": [
            {
                "page_id": "toolbar",
                "group": "icon-heavy",
                "viewport": {"width": 200, "height": 100},
                "elements": [
                    {
                        "element_id": "next_button",
                        "bbox": [10, 10, 30, 30],
                        "predictions": [
                            {"element_id": "previous_button", "bbox": [50, 10, 70, 30], "score": 0.9},
                            {"element_id": "next_button", "bbox": [12, 12, 32, 32], "score": 0.8},
                        ],
                    },
                    {
                        "element_id": "settings_button",
                        "bbox": [100, 10, 120, 30],
                        "predictions": [],
                    },
                ],
            },
            {
                "page_id": "article",
                "group": "text-rich",
                "viewport": {"width": 200, "height": 100},
                "elements": [
                    {
                        "element_id": "search_input",
                        "bbox": [0, 0, 100, 20],
                        "predictions": [
                            {"element_id": "search_input", "bbox": [0, 0, 100, 20], "score": 0.99},
                            {"element_id": "newsletter_input", "bbox": [0, 30, 100, 50], "score": 0.2},
                        ],
                    }
                ],
            },
        ]
    }

    metrics = align.evaluate_alignment_fixture(fixture)

    assert metrics["overall"]["total"] == 3
    assert metrics["overall"]["top1_dom_match_accuracy"] == 1 / 3
    assert metrics["overall"]["top3_dom_match_recall"] == 2 / 3
    assert metrics["overall"]["unmatched_rate"] == 1 / 3
    assert metrics["overall"]["mean_iou"] == 0.5
    assert metrics["overall"]["mean_iou_all_predictions"] == 0.5
    assert metrics["overall"]["mean_iou_top1_correct"] == 1.0
    assert metrics["overall"]["mean_center_distance"] == 20.0
    assert metrics["overall"]["normalized_center_distance"] == 20.0 / (200**2 + 100**2) ** 0.5

    icon = metrics["by_group"]["icon-heavy"]
    assert icon["total"] == 2
    assert icon["top1_dom_match_accuracy"] == 0.0
    assert icon["top3_dom_match_recall"] == 0.5
    assert icon["unmatched_rate"] == 0.5

    assert metrics["by_page"]["article"]["top1_dom_match_accuracy"] == 1.0


def test_sample_alignment_fixture_runs_deterministically():
    sample_path = ROOT / "tests" / "fixtures" / "vision_dom_alignment_sample.json"

    metrics = align.evaluate_alignment_file(sample_path)

    assert metrics["overall"]["total"] == 4
    assert metrics["overall"]["top1_dom_match_accuracy"] == 0.5
    assert metrics["overall"]["top3_dom_match_recall"] == 0.75
    assert "mean_iou_all_predictions" in metrics["overall"]
    assert "mean_iou_top1_correct" in metrics["overall"]
    assert "normalized_center_distance" in metrics["overall"]
    assert metrics["by_group"]["icon-heavy"]["total"] == 2
    assert metrics["by_group"]["text-rich"]["total"] == 2
