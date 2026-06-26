"""
Shared benchmark infrastructure for browser-use-vision.

Provides:
- BenchmarkTask / TaskResult dataclasses (with objective `verify`)
- TASKS: 16 tasks (6 local fixtures + 10 real sites), each with an objective verifier
- Verifier factories: dom_js / url_has / text_has / all_of / live_hn_top
- make_llm(): shared LLM factory
- run_task(): shared execution engine that runs the agent then verifies page state

Success is determined by objective verification (DOM / URL / live API), NOT by the
agent self-reporting `done()`. `is_done` and `steps` are still recorded for analysis.

Both real_world_benchmark.py and ablation_benchmark.py import from this module so the
task definitions, verifiers and run engine live in exactly one place.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ────────────────────────────────────────────
# Environment / proxy setup
# ────────────────────────────────────────────


def setup_env() -> None:
    """Load API keys from ~/.hermes/.env and configure proxy for LLM + browser.

    Keeps HTTP(S)_PROXY for the LLM gateway, excludes localhost (CDP + demo server),
    and neutralizes urllib.getproxies so browser-use internals don't double-proxy.
    Ground-truth fetchers (HN API) build their own proxied opener explicitly.
    """
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

    for var in ["ALL_PROXY", "all_proxy", "SOCKS_PROXY", "socks_proxy"]:
        os.environ.pop(var, None)
    proxy = os.environ.get("HTTP_PROXY", "http://127.0.0.1:1097")
    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    os.environ["http_proxy"] = proxy
    os.environ["https_proxy"] = proxy
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"
    os.environ["no_proxy"] = "localhost,127.0.0.1,0.0.0.0"
    urllib.request.getproxies = lambda: {}


VISION_API = "http://localhost:8100"


def make_llm(model: str = "gpt-4o-mini"):
    """Shared LLM factory reading OPENAI_BASE_URL / OPENAI_API_KEY from env."""
    from browser_use.llm.openai.chat import ChatOpenAI

    base = os.environ.get("OPENAI_BASE_URL", "https://llm-gateway.mlamp.cn/v1")
    key = os.environ.get("OPENAI_API_KEY", "")
    return ChatOpenAI(model=model, api_key=key, base_url=base, temperature=0.0)


# ────────────────────────────────────────────
# Verifier framework
# ────────────────────────────────────────────

# A verifier: async (page, final_result) -> (passed, detail)
Verifier = Callable[[object, str], Awaitable[Tuple[bool, str]]]


def _truthy(val) -> bool:
    """Coerce a verifier return value to bool.

    The browser-use actor Page.evaluate returns a *string* representation of the
    JS result (a JS boolean comes back as Python ``str(True)`` -> ``"True"``), so a
    naive ``bool(val)`` would treat the string ``"False"`` as truthy. Handle both
    real bools (unit-test FakePage) and stringified bools (live page).
    """
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


async def _page_url(page) -> str:
    """Read the current URL from either an actor Page (async ``get_url()``) or a
    Playwright-style page / FakePage (``.url`` attribute)."""
    if page is None:
        return ""
    getter = getattr(page, "get_url", None)
    if callable(getter):
        try:
            res = getter()
            if asyncio.iscoroutine(res):
                res = await res
            return res or ""
        except Exception:  # noqa: BLE001
            return ""
    return getattr(page, "url", "") or ""


def dom_js(expr: str, label: str = "") -> Verifier:
    """Verify by evaluating a JS expression in the page; truthy = pass.

    ``expr`` is any JS expression returning a truthy/falsy value. It is wrapped in
    an arrow function because the actor Page.evaluate enforces ``(...args) =>`` form.
    """

    async def _v(page, final_result):  # noqa: ANN001
        if page is None:
            return False, f"dom_js: no page available ({expr})"
        try:
            val = await page.evaluate(f"(() => Boolean({expr}))")
            passed = _truthy(val)
            return passed, label or f"dom_js({expr}) -> {val!r}"
        except Exception as e:  # noqa: BLE001
            return False, f"dom_js error: {e}"

    return _v


def url_has(*subs: str) -> Verifier:
    """Verify the final page URL contains all given substrings (case-insensitive)."""

    async def _v(page, final_result):  # noqa: ANN001
        url = await _page_url(page)
        low = url.lower()
        ok = all(s.lower() in low for s in subs)
        return ok, f"url={url!r} expected~{list(subs)}"

    return _v


def text_has(*subs: str) -> Verifier:
    """Verify the agent's reported result contains all given substrings (case-insensitive)."""

    async def _v(page, final_result):  # noqa: ANN001
        text = (final_result or "").lower()
        ok = all(s.lower() in text for s in subs)
        return ok, f"result expected~{list(subs)} (got {len(text)} chars)"

    return _v


def all_of(*verifiers: Verifier) -> Verifier:
    """AND-combine multiple verifiers; passes only if all pass."""

    async def _v(page, final_result):  # noqa: ANN001
        details = []
        ok = True
        for vf in verifiers:
            p, d = await vf(page, final_result)
            ok = ok and p
            details.append(d)
        return ok, " AND ".join(details)

    return _v


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def _proxied_get_json(url: str, timeout: int = 20):
    proxy = os.environ.get("HTTP_PROXY", "http://127.0.0.1:1097")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    with opener.open(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_hn_top_title() -> str:
    """Fetch the canonical #1 Hacker News story title via the official Firebase API."""
    top = _proxied_get_json("https://hacker-news.firebaseio.com/v0/topstories.json")
    item = _proxied_get_json(f"https://hacker-news.firebaseio.com/v0/item/{top[0]}.json")
    return item.get("title", "")


def title_matches(title: str, result: str) -> bool:
    """Fuzzy match: normalized title is a substring, or >=70% of title tokens present."""
    nt = _normalize(title).strip()
    nr = _normalize(result)
    if not nt:
        return False
    if nt in nr:
        return True
    toks = [t for t in nt.split() if len(t) > 2]
    if not toks:
        return False
    hits = sum(1 for t in toks if t in nr)
    return hits / len(toks) >= 0.7


def live_hn_top() -> Verifier:
    """Verify the agent reported the current real HN top story (live ground truth)."""

    async def _v(page, final_result):  # noqa: ANN001
        loop = asyncio.get_event_loop()
        try:
            title = await loop.run_in_executor(None, fetch_hn_top_title)
        except Exception as e:  # noqa: BLE001
            return False, f"HN fetch error: {e}"
        ok = title_matches(title, final_result or "")
        return ok, f"HN top={title!r} match={ok}"

    return _v


# ────────────────────────────────────────────
# Task definitions
# ────────────────────────────────────────────


@dataclass
class BenchmarkTask:
    name: str
    url: str
    task: str
    category: str  # icon-heavy / mixed / dom-rich
    verify: Optional[Verifier] = None
    max_steps: int = 8
    timeout: int = 120


TASKS = [
    # ── Local fixtures (6) — icon-only visual core, DOM-verified ──
    BenchmarkTask(
        name="icon_music_player",
        url="http://localhost:8088/icon_only_player.html",
        task="Click the 'Next Track' button on this music player. The buttons are icon-only with no text labels. After clicking, call done.",
        category="icon-heavy",
        verify=dom_js(
            "document.getElementById('result') && "
            "document.getElementById('result').textContent.toLowerCase().includes('next')"
        ),
    ),
    BenchmarkTask(
        name="color_picker",
        url="http://localhost:8088/color_picker.html",
        task="Click the green color swatch to select it, then click the 'Apply Theme' button. After clicking, call done.",
        category="icon-heavy",
        verify=dom_js(
            "document.querySelector('.color-swatch.selected') && "
            "document.querySelector('.color-swatch.selected').dataset.color==='green' && "
            "Array.isArray(window.actions) && window.actions.includes('apply')"
        ),
    ),
    BenchmarkTask(
        name="toolbar_eraser",
        url="http://localhost:8088/toolbar_app.html",
        task="Click the eraser tool in the drawing toolbar. The tools are icon-only SVG buttons with no text labels. After clicking, call done and report which tool you selected.",
        category="icon-heavy",
        verify=dom_js(
            "document.querySelector('.tool-btn.active') && "
            "document.querySelector('.tool-btn.active').dataset.tool==='eraser'"
        ),
    ),
    BenchmarkTask(
        name="social_feed_like",
        url="http://localhost:8088/social_feed.html",
        task="Click the heart/like button on the first post (by photographer_jane). The action buttons are icon-only. After clicking, call done.",
        category="icon-heavy",
        verify=dom_js(
            "document.querySelectorAll('.post')[0] && "
            "document.querySelectorAll('.post')[0].querySelector('.action-btn.liked')!==null"
        ),
    ),
    BenchmarkTask(
        name="ecommerce_filter_color",
        url="http://localhost:8088/ecommerce.html",
        task="In the sneaker store, click the blue color swatch in the Color filter section on the left sidebar. After selecting, call done.",
        category="mixed",
        verify=dom_js(
            "document.querySelector('.color-swatch.selected') && "
            "document.querySelector('.color-swatch.selected').dataset.color==='blue'"
        ),
    ),
    BenchmarkTask(
        name="dashboard_chart_tab",
        url="http://localhost:8088/dashboard.html",
        task="Switch the chart view to 'Monthly' by clicking the Monthly tab in the Revenue Overview section. After clicking, call done.",
        category="dom-rich",
        verify=dom_js(
            "document.querySelector('.chart-tab.active') && "
            "document.querySelector('.chart-tab.active').textContent.trim()==='Monthly'"
        ),
    ),
    # ── Real sites (10) — action + extraction ──
    BenchmarkTask(
        name="wikipedia_toc_nav",
        url="https://en.wikipedia.org/wiki/Artificial_intelligence",
        task="Click on the 'Machine learning' link in the table of contents to navigate to that section. After clicking, call done.",
        category="mixed",
        verify=url_has("Machine_learning"),
    ),
    BenchmarkTask(
        name="wikipedia_search",
        url="https://en.wikipedia.org/wiki/Main_Page",
        task="Use the search box to search for 'Alan Turing' and open his article. After the article loads, call done.",
        category="mixed",
        verify=url_has("Alan_Turing"),
    ),
    BenchmarkTask(
        name="hackernews_top_story",
        url="https://news.ycombinator.com/",
        task="Find the top (first) story on Hacker News and report its exact title. Call done with the title.",
        category="mixed",
        verify=live_hn_top(),
    ),
    BenchmarkTask(
        name="arxiv_search",
        url="https://arxiv.org/",
        task="Type 'vision language model' in the search box on arxiv.org and submit the search. After the search results appear, report the title of the first result. Call done with your findings.",
        category="dom-rich",
        verify=url_has("/search/"),
    ),
    BenchmarkTask(
        name="quotes_first_author",
        url="https://quotes.toscrape.com/",
        task="Report the author of the very first quote shown on this page. Call done with the author's name.",
        category="dom-rich",
        verify=text_has("albert einstein"),
    ),
    BenchmarkTask(
        name="quotes_tag_nav",
        url="https://quotes.toscrape.com/",
        task="Click the 'love' tag in the Top Tags sidebar, then report the author of the first quote shown on the resulting page. Call done with the author's name.",
        category="mixed",
        verify=text_has("gide"),
    ),
    BenchmarkTask(
        name="books_price",
        url="https://books.toscrape.com/",
        task="Find the book titled 'A Light in the Attic' and report its price. Call done with the price.",
        category="dom-rich",
        verify=text_has("51.77"),
    ),
    BenchmarkTask(
        name="books_category",
        url="https://books.toscrape.com/",
        task="Open the 'Travel' category from the left sidebar and report the title of the first book listed. Call done with the title.",
        category="dom-rich",
        verify=text_has("himalayas"),
    ),
    BenchmarkTask(
        name="herokuapp_checkbox",
        url="https://the-internet.herokuapp.com/checkboxes",
        task="On this page there are two checkboxes; the first one starts unchecked. Check the first checkbox so it becomes checked. After checking, call done.",
        category="dom-rich",
        verify=dom_js(
            "document.querySelectorAll('#checkboxes input[type=checkbox]')[0] && "
            "document.querySelectorAll('#checkboxes input[type=checkbox]')[0].checked===true"
        ),
    ),
    BenchmarkTask(
        name="herokuapp_dropdown",
        url="https://the-internet.herokuapp.com/dropdown",
        task="Select 'Option 2' from the dropdown menu on this page. After selecting, call done.",
        category="dom-rich",
        verify=dom_js("document.getElementById('dropdown') && document.getElementById('dropdown').value==='2'"),
    ),
]


# ────────────────────────────────────────────
# Result + execution engine
# ────────────────────────────────────────────


@dataclass
class TaskResult:
    task_name: str
    category: str
    label: str  # mode or condition name
    success: bool
    steps: int
    time_seconds: float
    final_result: str
    verify_detail: str = ""
    is_done: bool = False
    vision_calls: int = 0
    adaptive_stats: dict = field(default_factory=dict)
    error: str = ""
    failure_type: str = "none"


# build_agent: (task, session) -> agent  (the agent must accept browser_session=session)
AgentBuilder = Callable[[BenchmarkTask, object], object]


class _InternalAgentTimeoutError(Exception):
    """Raised when the agent stack raises TimeoutError before the outer deadline."""


def classify_failure_type(*, success: bool, error: str = "", verify_detail: str = "") -> str:
    if success:
        return "none"

    error_low = (error or "").lower()
    detail_low = (verify_detail or "").lower()
    if error.startswith("Outer deadline") or error.startswith("Timeout ("):
        return "outer_deadline"
    if "timeout" in error_low or "timeouterror" in error_low:
        return "internal_timeout"
    if any(token in error_low for token in ("browser", "cdp", "playwright", "chrome")):
        return "browser_error"
    if any(token in error_low for token in ("openai", "llm", "rate limit", "api")):
        return "llm_error"
    if any(token in error_low for token in ("florence", "vision", "ocr", "caption")):
        return "vision_error"
    if error:
        return "runtime_error"
    if detail_low.startswith("verify error"):
        return "verifier_error"
    return "objective_verification_failed"


def _browser_session_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {"headless": True, "keep_alive": True}
    cdp_url = os.environ.get("BROWSER_USE_CDP_URL")
    if cdp_url:
        kwargs["cdp_url"] = cdp_url
        return kwargs

    executable_path = os.environ.get("BROWSER_USE_EXECUTABLE_PATH")
    if executable_path:
        kwargs["executable_path"] = executable_path
    return kwargs


async def _run_agent(agent, task: BenchmarkTask):  # noqa: ANN001
    try:
        return await agent.run(max_steps=task.max_steps)
    except asyncio.TimeoutError as exc:
        raise _InternalAgentTimeoutError(str(exc)) from exc


async def _resolve_verify_page(session):
    """Get a live page for post-run verification.

    After ``agent.run()`` finishes, ``agent_focus_target_id`` is cleared, so
    ``get_current_page()`` returns None. ``get_pages()`` reads from the session
    manager independently, so fall back to it and pick the last tab with a real URL.
    """
    page = await session.get_current_page()
    if page is not None:
        return page

    try:
        pages = await session.get_pages()
    except Exception:  # noqa: BLE001
        pages = []

    chosen = None
    for pg in pages:
        try:
            u = await pg.get_url()
        except Exception:  # noqa: BLE001
            u = ""
        if u and not u.startswith("chrome://") and "about:blank" not in u:
            chosen = pg
    return chosen or (pages[-1] if pages else None)


async def run_task(task: BenchmarkTask, build_agent: AgentBuilder, label: str = "") -> TaskResult:
    """Run one task with the agent produced by build_agent, then objectively verify.

    Success = objective verification (task.verify) of the post-run page/result.
    Falls back to is_done() only when a task has no verifier (should not happen).
    """
    from browser_use.browser.session import BrowserSession

    print(f"  [{label}] {task.name}...", end=" ", flush=True)

    # keep_alive so the browser survives agent.run() for post-run verification;
    # we close it ourselves in the finally block below.
    session = BrowserSession(**_browser_session_kwargs())
    start_time = time.time()
    result_text = ""
    steps = 0
    is_done = False
    vision_calls = 0
    adaptive_stats: dict = {}
    error_msg = ""
    failure_type = ""
    success = False
    verify_detail = ""
    agent = None

    try:
        agent = build_agent(task, session)

        await session.start()
        page = await session.get_current_page()
        await page.goto(task.url)
        await asyncio.sleep(3)

        history = await asyncio.wait_for(_run_agent(agent, task), timeout=task.timeout)
        result_text = history.final_result() or ""
        steps = history.number_of_steps()
        is_done = history.is_done()

        if hasattr(agent, "vision_stats"):
            vs = agent.vision_stats
            vision_calls = vs.get("total_vision_calls", 0)
            adaptive_stats = vs.get("adaptive_stats", {})

        # Objective verification — the single source of truth for success.
        if task.verify is not None:
            try:
                page = await _resolve_verify_page(session)
                passed, verify_detail = await task.verify(page, result_text)
                success = bool(passed)
            except Exception as e:  # noqa: BLE001
                verify_detail = f"verify error: {e}"
                failure_type = "verifier_error"
                success = False
        else:
            success = is_done and steps < task.max_steps
            verify_detail = "no verifier (fallback to is_done)"

        if not success and not failure_type:
            failure_type = "objective_verification_failed"

    except _InternalAgentTimeoutError as e:
        detail = str(e).strip()
        error_msg = f"Internal timeout: {detail}" if detail else "Internal timeout inside agent stack"
        failure_type = "internal_timeout"
    except asyncio.TimeoutError:
        error_msg = f"Outer deadline ({task.timeout}s)"
        failure_type = "outer_deadline"
        # On timeout the agent kept looping; record the real step count so the
        # report doesn't show a misleading "0 steps" for a task that ran for minutes.
        if agent is not None:
            try:
                steps = agent.history.number_of_steps()
            except Exception:  # noqa: BLE001
                try:
                    steps = int(getattr(agent.state, "n_steps", 0))
                except Exception:  # noqa: BLE001
                    steps = 0
    except Exception as e:  # noqa: BLE001
        error_msg = str(e)[:200]
        failure_type = classify_failure_type(success=False, error=error_msg)

    elapsed = time.time() - start_time
    failure_type = failure_type or classify_failure_type(success=success, error=error_msg, verify_detail=verify_detail)

    try:
        await session.close()
    except Exception:  # noqa: BLE001
        pass

    status = "✅" if success else "❌"
    extra = f" vis={vision_calls}" if vision_calls else ""
    print(f"{status} {steps}st/{elapsed:.0f}s{extra}", flush=True)

    return TaskResult(
        task_name=task.name,
        category=task.category,
        label=label,
        success=success,
        steps=steps,
        time_seconds=round(elapsed, 1),
        final_result=result_text[:500],
        verify_detail=verify_detail,
        is_done=is_done,
        vision_calls=vision_calls,
        adaptive_stats=adaptive_stats,
        error=error_msg,
        failure_type=failure_type,
    )
