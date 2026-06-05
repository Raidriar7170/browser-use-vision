"""Tests for the VBR adapter entrypoint — all GPU-free."""

import re

import pytest

from browser_use_vision.adapter import BrowserUseVisionGrounder, ground


# ── VBR smoke context ───────────────────────────────────────────

SMOKE_CONTEXT = {"controlled_local_demo": "visual_fallback"}


class TestControlledLocalDemoSmoke:
    def test_returns_valid_schema(self):
        result = ground("icon-only confirmation button", context=SMOKE_CONTEXT)
        assert result["selected_target_ref"] == "element:0"
        assert result["confidence"] == pytest.approx(0.8)
        assert result["is_mock"] is False
        assert result["evidence"]["provider"] == "browser-use-vision"
        assert result["evidence"]["method"] == "local-contract-smoke"

    def test_reason_mentions_contract_smoke(self):
        result = ground("play", context=SMOKE_CONTEXT)
        reason = result["evidence"]["reason"]
        assert "contract smoke" in reason.lower()
        assert "no screenshot grounding claimed" in reason.lower()

    def test_includes_target_in_reason(self):
        result = ground("next track button", context=SMOKE_CONTEXT)
        assert "next track button" in result["evidence"]["reason"]


# ── element matching ────────────────────────────────────────────

SAMPLE_ELEMENTS = [
    {"label": "Play", "bbox": [0.1, 0.2, 0.15, 0.25]},
    {"label": "Next Track", "bbox": [0.3, 0.2, 0.35, 0.25]},
    {"label": "Volume Up", "bbox": [0.5, 0.2, 0.55, 0.25]},
]


class TestElementMatch:
    def test_exact_match(self):
        result = ground("Play", context={"elements": SAMPLE_ELEMENTS})
        assert result["selected_target_ref"] == "element:0"
        assert result["confidence"] == pytest.approx(1.0)
        assert result["is_mock"] is False
        assert result["evidence"]["method"] == "element-match"
        assert result["evidence"]["bbox"] == [0.1, 0.2, 0.15, 0.25]

    def test_case_insensitive(self):
        result = ground("play", context={"elements": SAMPLE_ELEMENTS})
        assert result["selected_target_ref"] == "element:0"

    def test_substring_match(self):
        result = ground("Track", context={"elements": SAMPLE_ELEMENTS})
        assert result["selected_target_ref"] == "element:1"
        assert result["confidence"] == pytest.approx(0.8)

    def test_best_match_ranking(self):
        elements = [
            {"label": "Submit Order", "bbox": [0.1, 0.1, 0.2, 0.2]},
            {"label": "Submit", "bbox": [0.3, 0.1, 0.4, 0.2]},
        ]
        result = ground("Submit", context={"elements": elements})
        assert result["selected_target_ref"] == "element:1"
        assert result["confidence"] == pytest.approx(1.0)

    def test_no_match_raises(self):
        with pytest.raises(RuntimeError, match="no element label matches"):
            ground("nonexistent widget", context={"elements": SAMPLE_ELEMENTS})

    def test_empty_elements_raises(self):
        with pytest.raises(RuntimeError, match="empty"):
            ground("Play", context={"elements": []})


# ── error cases ─────────────────────────────────────────────────

class TestErrors:
    def test_no_context_raises(self):
        with pytest.raises(RuntimeError, match="no actionable context"):
            ground("anything")

    def test_none_context_raises(self):
        with pytest.raises(RuntimeError, match="no actionable context"):
            ground("anything", context=None)

    def test_empty_context_raises(self):
        with pytest.raises(RuntimeError, match="no actionable context"):
            ground("anything", context={})

    def test_screenshot_without_backend_raises(self):
        with pytest.raises(RuntimeError, match="backend_url"):
            ground("button", context={"screenshot": b"\x89PNG..."})


# ── safety invariants ───────────────────────────────────────────

ALL_CONTEXTS = [
    SMOKE_CONTEXT,
    {"elements": SAMPLE_ELEMENTS},
]

SENSITIVE_PATTERNS = re.compile(
    r"/Users/|/home/|/tmp/|api_key|api.key|token=|secret|password",
    re.IGNORECASE,
)


class TestSafetyInvariants:
    @pytest.mark.parametrize("ctx", ALL_CONTEXTS)
    def test_never_mock(self, ctx):
        result = ground("Play", context=ctx)
        assert result["is_mock"] is False

    @pytest.mark.parametrize("ctx", ALL_CONTEXTS)
    def test_provider_tag(self, ctx):
        result = ground("Play", context=ctx)
        assert result["evidence"]["provider"] == "browser-use-vision"

    @pytest.mark.parametrize("ctx", ALL_CONTEXTS)
    def test_no_sensitive_data_in_evidence(self, ctx):
        result = ground("Play", context=ctx)
        evidence_str = str(result["evidence"])
        assert not SENSITIVE_PATTERNS.search(evidence_str), (
            f"Sensitive data found in evidence: {evidence_str}"
        )


# ── class vs function parity ────────────────────────────────────

class TestClassFunctionParity:
    def test_same_result(self):
        ctx = {"elements": SAMPLE_ELEMENTS}
        func_result = ground("Play", context=ctx)
        class_result = BrowserUseVisionGrounder().ground("Play", context=ctx)
        assert func_result == class_result

    def test_smoke_parity(self):
        func_result = ground("test", context=SMOKE_CONTEXT)
        class_result = BrowserUseVisionGrounder().ground("test", context=SMOKE_CONTEXT)
        assert func_result == class_result
