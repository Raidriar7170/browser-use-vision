from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ablation_benchmark as ab  # noqa: E402
import benchmark_common as bc  # noqa: E402


def _result(
    label: str,
    *,
    success: bool,
    steps: int = 1,
    vision_calls: int = 0,
    failure_type: str = "none",
    error: str = "",
) -> bc.TaskResult:
    return bc.TaskResult(
        task_name="icon_music_player",
        category="icon-heavy",
        label=label,
        success=success,
        steps=steps,
        time_seconds=10.0,
        final_result="",
        verify_detail="ok" if success else "objective failed",
        vision_calls=vision_calls,
        error=error,
        failure_type=failure_type,
    )


def test_ablation_report_marks_unrun_conditions_and_avoids_unsupported_claims(tmp_path):
    results = [
        _result("A_baseline", success=False, failure_type="objective_verification_failed"),
        _result(
            "C_full_always",
            success=False,
            steps=0,
            vision_calls=2,
            failure_type="outer_deadline",
            error="Outer deadline (240s)",
        ),
        _result("E_adaptive_full", success=True, vision_calls=1),
    ]

    summary = ab.build_summary(results)

    assert summary["conditions_run"] == ["A_baseline", "C_full_always", "E_adaptive_full"]
    assert summary["by_condition"]["B_som_only"]["status"] == "not_run"
    assert summary["by_condition"]["D_ocr_only"]["success_rate"] is None
    assert summary["by_condition"]["F_adaptive_no_som"]["total_vision_calls"] is None
    assert summary["by_condition"]["C_full_always"]["zero_step_count"] == 1
    assert summary["by_condition"]["C_full_always"]["infra_failure_count"] == 1
    assert summary["by_condition"]["C_full_always"]["eligible_attempt_count"] == 0
    assert summary["by_condition"]["C_full_always"]["completion_rate"] == 0.0

    report_path = tmp_path / "ablation_report.md"
    ab.generate_markdown_report(results, summary, report_path, model="gpt-4o", report_date="2026-06-25")
    report = report_path.read_text(encoding="utf-8")

    assert "| B_som_only | not run |" in report
    assert "| D_ocr_only | not run |" in report
    assert "| F_adaptive_no_som | not run |" in report
    assert "**Rows**: benchmark attempts" in report
    assert "These conditions are excluded from comparisons" in report
    assert "vision model's small-icon grounding ceiling" not in report
    assert "remaining bottleneck is the vision model" not in report
