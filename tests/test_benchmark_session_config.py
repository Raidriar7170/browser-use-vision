import asyncio

from scripts import benchmark_common as bc


class _RecordingAgent:
    def __init__(self):
        self.max_steps = None

    async def run(self, max_steps=500):
        self.max_steps = max_steps


def test_run_agent_uses_task_max_steps():
    agent = _RecordingAgent()
    task = bc.BenchmarkTask(
        name="limited",
        url="http://example.test",
        task="do it",
        category="dom-rich",
        max_steps=7,
    )

    asyncio.run(bc._run_agent(agent, task))

    assert agent.max_steps == 7


def test_browser_session_kwargs_defaults_to_local_browser(monkeypatch):
    monkeypatch.delenv("BROWSER_USE_CDP_URL", raising=False)
    monkeypatch.delenv("BROWSER_USE_EXECUTABLE_PATH", raising=False)

    assert bc._browser_session_kwargs() == {"headless": True, "keep_alive": True}


def test_browser_session_kwargs_uses_cdp_url(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_CDP_URL", "http://127.0.0.1:49243")
    monkeypatch.setenv("BROWSER_USE_EXECUTABLE_PATH", "/should/not/be/used/with/cdp")

    assert bc._browser_session_kwargs() == {
        "headless": True,
        "keep_alive": True,
        "cdp_url": "http://127.0.0.1:49243",
    }


def test_browser_session_kwargs_uses_explicit_executable(monkeypatch):
    monkeypatch.delenv("BROWSER_USE_CDP_URL", raising=False)
    monkeypatch.setenv("BROWSER_USE_EXECUTABLE_PATH", "/path/to/chrome")

    assert bc._browser_session_kwargs() == {
        "headless": True,
        "keep_alive": True,
        "executable_path": "/path/to/chrome",
    }
