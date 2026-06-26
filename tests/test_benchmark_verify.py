"""
Unit tests for benchmark verifier helpers (scripts/benchmark_common.py).

Pure logic — no browser, no LLM, no network. The page object is faked.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark_common as bc  # noqa: E402


class FakePage:
    """Minimal stand-in for a Playwright page."""

    def __init__(self, url: str = "", eval_result=None, eval_error: Exception | None = None):
        self.url = url
        self._eval_result = eval_result
        self._eval_error = eval_error

    async def evaluate(self, expr: str):
        if self._eval_error:
            raise self._eval_error
        return self._eval_result


class FakeActorPage:
    """Stand-in for the browser-use actor Page: async get_url(), evaluate() -> str."""

    def __init__(self, url: str = "", eval_value: str = "False"):
        self._url = url
        self._eval_value = eval_value

    async def get_url(self) -> str:
        return self._url

    async def evaluate(self, expr: str) -> str:
        # Real actor returns the *string* representation of the JS result.
        return self._eval_value


def _run(coro):
    return asyncio.run(coro)


# ── text_has ──────────────────────────────────────────────────────────────


class TestTextHas:
    def test_single_substring_present(self):
        vf = bc.text_has("einstein")
        ok, _ = _run(vf(None, "The author is Albert Einstein"))
        assert ok is True

    def test_case_insensitive(self):
        vf = bc.text_has("ALBERT EINSTEIN")
        ok, _ = _run(vf(None, "albert einstein said"))
        assert ok is True

    def test_all_substrings_required(self):
        vf = bc.text_has("vision", "language")
        assert _run(vf(None, "vision language model"))[0] is True
        assert _run(vf(None, "vision only"))[0] is False

    def test_missing_substring(self):
        vf = bc.text_has("himalayas")
        ok, _ = _run(vf(None, "It's only the Andes"))
        assert ok is False

    def test_empty_result(self):
        vf = bc.text_has("anything")
        assert _run(vf(None, ""))[0] is False
        assert _run(vf(None, None))[0] is False


# ── url_has ───────────────────────────────────────────────────────────────


class TestUrlHas:
    def test_substring_present(self):
        vf = bc.url_has("Machine_learning")
        page = FakePage(url="https://en.wikipedia.org/wiki/Artificial_intelligence#Machine_learning")
        assert _run(vf(page, ""))[0] is True

    def test_case_insensitive(self):
        vf = bc.url_has("alan_turing")
        page = FakePage(url="https://en.wikipedia.org/wiki/Alan_Turing")
        assert _run(vf(page, ""))[0] is True

    def test_all_substrings_required(self):
        vf = bc.url_has("/search/", "query")
        page = FakePage(url="https://arxiv.org/search/?searchtype=all&query=vision")
        assert _run(vf(page, ""))[0] is True
        page2 = FakePage(url="https://arxiv.org/abs/1234")
        assert _run(vf(page2, ""))[0] is False

    def test_missing(self):
        vf = bc.url_has("Machine_learning")
        page = FakePage(url="https://en.wikipedia.org/wiki/Artificial_intelligence")
        assert _run(vf(page, ""))[0] is False

    def test_actor_page_async_get_url(self):
        # Real actor Page exposes async get_url(), not a .url attribute.
        vf = bc.url_has("Alan_Turing")
        page = FakeActorPage(url="https://en.wikipedia.org/wiki/Alan_Turing")
        assert _run(vf(page, ""))[0] is True
        page2 = FakeActorPage(url="https://en.wikipedia.org/wiki/Main_Page")
        assert _run(vf(page2, ""))[0] is False

    def test_none_page_fails(self):
        vf = bc.url_has("anything")
        assert _run(vf(None, ""))[0] is False


# ── dom_js ────────────────────────────────────────────────────────────────


class TestDomJs:
    def test_truthy_passes(self):
        vf = bc.dom_js("document.querySelector('.x')")
        page = FakePage(eval_result=True)
        assert _run(vf(page, ""))[0] is True

    def test_falsy_fails(self):
        vf = bc.dom_js("document.querySelector('.x')")
        page = FakePage(eval_result=False)
        assert _run(vf(page, ""))[0] is False

    def test_eval_error_fails_gracefully(self):
        vf = bc.dom_js("bad expr")
        page = FakePage(eval_error=RuntimeError("boom"))
        ok, detail = _run(vf(page, ""))
        assert ok is False
        assert "error" in detail.lower()

    def test_none_page_fails(self):
        vf = bc.dom_js("document.querySelector('.x')")
        ok, detail = _run(vf(None, ""))
        assert ok is False
        assert "no page" in detail.lower()

    def test_stringified_bool_from_actor_page(self):
        # Actor Page.evaluate returns "True"/"False" strings, not real bools.
        vf = bc.dom_js("document.querySelector('.x')")
        assert _run(vf(FakeActorPage(eval_value="True"), ""))[0] is True
        assert _run(vf(FakeActorPage(eval_value="False"), ""))[0] is False
        assert _run(vf(FakeActorPage(eval_value=""), ""))[0] is False


# ── all_of ────────────────────────────────────────────────────────────────


class TestAllOf:
    def test_all_pass(self):
        vf = bc.all_of(bc.url_has("/search/"), bc.text_has("vision"))
        page = FakePage(url="https://arxiv.org/search/?q=1")
        assert _run(vf(page, "vision language model"))[0] is True

    def test_one_fails(self):
        vf = bc.all_of(bc.url_has("/search/"), bc.text_has("missing"))
        page = FakePage(url="https://arxiv.org/search/?q=1")
        assert _run(vf(page, "vision language model"))[0] is False


# ── title_matches (HN fuzzy match) ─────────────────────────────────────────


class TestTitleMatches:
    def test_exact_substring(self):
        assert bc.title_matches("Show HN: My Cool Project", "The top story is Show HN: My Cool Project") is True

    def test_punctuation_and_case_insensitive(self):
        assert bc.title_matches("Rust 2.0 Released!", "rust 20 released") is True

    def test_token_overlap_threshold(self):
        title = "A New Approach to Distributed Consensus Algorithms"
        # result paraphrases but keeps most significant tokens
        result = "new approach distributed consensus algorithms in databases"
        assert bc.title_matches(title, result) is True

    def test_unrelated_fails(self):
        assert bc.title_matches("Quantum Computing Breakthrough", "I clicked the like button") is False

    def test_empty_title_fails(self):
        assert bc.title_matches("", "anything") is False


class TestFailureType:
    def test_distinguishes_outer_and_internal_timeout(self):
        assert bc.classify_failure_type(success=False, error="Outer deadline (240s)") == "outer_deadline"
        assert bc.classify_failure_type(success=False, error="Internal timeout before outer deadline") == (
            "internal_timeout"
        )

    def test_distinguishes_verifier_and_objective_failure(self):
        assert bc.classify_failure_type(success=False, verify_detail="verify error: page closed") == "verifier_error"
        assert bc.classify_failure_type(success=False, error="", verify_detail="url mismatch") == (
            "objective_verification_failed"
        )

    def test_wraps_agent_internal_asyncio_timeout_before_outer_deadline(self):
        class TimeoutAgent:
            async def run(self, max_steps: int):  # noqa: ARG002
                raise asyncio.TimeoutError("llm backend timeout")

        with pytest.raises(Exception) as exc_info:
            _run(bc._run_agent(TimeoutAgent(), bc.TASKS[0]))  # noqa: SLF001

        assert exc_info.value.__class__.__name__ == "_InternalAgentTimeoutError"
        assert str(exc_info.value) == "llm backend timeout"


# ── live_hn_top verifier (with monkeypatched fetch) ─────────────────────────


class TestLiveHnTop:
    def test_uses_fetched_title(self, monkeypatch):
        monkeypatch.setattr(bc, "fetch_hn_top_title", lambda: "Show HN: A Verifier Framework")
        vf = bc.live_hn_top()
        ok, detail = _run(vf(None, "The top story is Show HN: A Verifier Framework"))
        assert ok is True
        assert "Show HN" in detail

    def test_wrong_answer_fails(self, monkeypatch):
        monkeypatch.setattr(bc, "fetch_hn_top_title", lambda: "Show HN: A Verifier Framework")
        vf = bc.live_hn_top()
        ok, _ = _run(vf(None, "Some unrelated headline about cats"))
        assert ok is False

    def test_fetch_error_fails_gracefully(self, monkeypatch):
        def _boom():
            raise RuntimeError("network down")

        monkeypatch.setattr(bc, "fetch_hn_top_title", _boom)
        vf = bc.live_hn_top()
        ok, detail = _run(vf(None, "anything"))
        assert ok is False
        assert "error" in detail.lower()


# ── TASKS sanity ────────────────────────────────────────────────────────────


class TestTasksIntegrity:
    def test_sixteen_tasks(self):
        assert len(bc.TASKS) == 16

    def test_every_task_has_verifier(self):
        assert all(t.verify is not None for t in bc.TASKS)

    def test_unique_names(self):
        names = [t.name for t in bc.TASKS]
        assert len(names) == len(set(names))

    def test_categories_valid(self):
        valid = {"icon-heavy", "mixed", "dom-rich"}
        assert all(t.category in valid for t in bc.TASKS)

    def test_real_sites_majority(self):
        local = sum(1 for t in bc.TASKS if "localhost" in t.url)
        assert local == 6
        assert len(bc.TASKS) - local == 10
