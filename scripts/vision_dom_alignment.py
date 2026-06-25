"""Offline Vision-DOM alignment metrics for labeled fixtures."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _bbox_xyxy(value: Any) -> tuple[float, float, float, float]:
    if isinstance(value, dict):
        if {"x1", "y1", "x2", "y2"} <= set(value):
            return float(value["x1"]), float(value["y1"]), float(value["x2"]), float(value["y2"])
        if {"x", "y", "width", "height"} <= set(value):
            x = float(value["x"])
            y = float(value["y"])
            return x, y, x + float(value["width"]), y + float(value["height"])
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return float(value[0]), float(value[1]), float(value[2]), float(value[3])
    raise ValueError(f"Unsupported bbox format: {value!r}")


def _bbox_xyxy_or_none(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        return _bbox_xyxy(value)
    except (TypeError, ValueError):
        return None


def _area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def bbox_iou(a: Any, b: Any) -> float:
    box_a = _bbox_xyxy(a)
    box_b = _bbox_xyxy(b)
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = _area((x1, y1, x2, y2))
    union = _area(box_a) + _area(box_b) - inter
    return inter / union if union else 0.0


def center_distance(a: Any, b: Any) -> float:
    box_a = _bbox_xyxy(a)
    box_b = _bbox_xyxy(b)
    ax = (box_a[0] + box_a[2]) / 2
    ay = (box_a[1] + box_a[3]) / 2
    bx = (box_b[0] + box_b[2]) / 2
    by = (box_b[1] + box_b[3]) / 2
    return math.hypot(ax - bx, ay - by)


def _viewport_diagonal(page: dict[str, Any]) -> float | None:
    viewport = page.get("viewport") or {}
    width = viewport.get("width") or page.get("viewport_width")
    height = viewport.get("height") or page.get("viewport_height")
    if width is None or height is None:
        return None
    diag = math.hypot(float(width), float(height))
    return diag if diag > 0 else None


def _element_records(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for page in fixture.get("pages", []):
        page_id = str(page.get("page_id") or page.get("url") or "unknown")
        group = str(page.get("group") or page.get("element_group") or "unknown")
        page_diagonal = _viewport_diagonal(page)
        for element in page.get("elements", []):
            gold_id = str(element.get("element_id") or element.get("dom_id") or element.get("id"))
            gold_bbox = element.get("bbox")
            gold_box = _bbox_xyxy_or_none(gold_bbox)
            predictions = sorted(
                element.get("predictions", []),
                key=lambda pred: float(pred.get("score", 0.0)),
                reverse=True,
            )
            top = predictions[0] if predictions else None
            top3 = predictions[:3]
            top_id = str(top.get("element_id") or top.get("dom_id") or top.get("id")) if top else None
            top_bbox = top.get("bbox") if top else None
            top_box = _bbox_xyxy_or_none(top_bbox)
            top_center_distance = (
                center_distance(gold_box, top_box) if gold_box is not None and top_box is not None else None
            )
            records.append(
                {
                    "page_id": page_id,
                    "group": group,
                    "gold_id": gold_id,
                    "gold_bbox": gold_bbox,
                    "predictions": predictions,
                    "top1_match": bool(top_id == gold_id),
                    "top3_match": any(
                        str(pred.get("element_id") or pred.get("dom_id") or pred.get("id")) == gold_id for pred in top3
                    ),
                    "unmatched": not predictions,
                    "top_iou": bbox_iou(gold_box, top_box) if gold_box is not None and top_box is not None else None,
                    "top_center_distance": top_center_distance,
                    "top_normalized_center_distance": top_center_distance / page_diagonal
                    if top_center_distance is not None and page_diagonal
                    else None,
                }
            )
    return records


def _mean(values: list[float | None]) -> float:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else 0.0


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    matched_geometry = [record for record in records if not record["unmatched"]]
    ious = [record["top_iou"] for record in matched_geometry]
    top1_correct_ious = [record["top_iou"] for record in matched_geometry if record["top1_match"]]
    distances = [record["top_center_distance"] for record in matched_geometry]
    normalized_distances = [record["top_normalized_center_distance"] for record in matched_geometry]
    return {
        "total": total,
        "top1_dom_match_accuracy": sum(1 for row in records if row["top1_match"]) / total if total else 0.0,
        "top3_dom_match_recall": sum(1 for row in records if row["top3_match"]) / total if total else 0.0,
        "unmatched_rate": sum(1 for row in records if row["unmatched"]) / total if total else 0.0,
        "mean_iou": _mean(ious),
        "mean_iou_all_predictions": _mean(ious),
        "mean_iou_top1_correct": _mean(top1_correct_ious),
        "mean_center_distance": _mean(distances),
        "normalized_center_distance": _mean(normalized_distances),
    }


def _breakdown(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record[key])].append(record)
    return {name: _summarize(rows) for name, rows in sorted(grouped.items())}


def evaluate_alignment_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    records = _element_records(fixture)
    return {
        "overall": _summarize(records),
        "by_page": _breakdown(records, "page_id"),
        "by_group": _breakdown(records, "group"),
    }


def evaluate_alignment_file(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return evaluate_alignment_fixture(json.load(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate offline Vision-DOM alignment fixtures.")
    parser.add_argument("fixture", type=Path, help="Labeled fixture JSON")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    metrics = evaluate_alignment_file(args.fixture)
    rendered = json.dumps(metrics, indent=2, ensure_ascii=False) + "\n"
    if args.json_output:
        args.json_output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
