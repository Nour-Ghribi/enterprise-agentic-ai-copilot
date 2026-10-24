"""Offline test policy: live inference is opt-in and never discovered implicitly."""

import httpx
import pytest


def pytest_addoption(parser):
    parser.addoption("--run-live-llm", action="store_true", default=False,
                     help="Explicitly permit marked real-provider tests; never needed for the offline suite.")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-live-llm"):
        skipped = pytest.mark.skip(reason="Real LLM inference not executed: offline policy; --run-live-llm is opt-in.")
        for item in items:
            if item.get_closest_marker("ollama"):
                item.add_marker(skipped)


@pytest.fixture(autouse=True)
def offline_test_policy(monkeypatch, request):
    if request.node.get_closest_marker("ollama") and request.config.getoption("--run-live-llm"):
        return
    monkeypatch.setenv("LLM_MODE", "offline")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")

    def blocked(*args, **kwargs):
        raise AssertionError("Unmocked HTTP request forbidden during offline tests")

    async def blocked_async(*args, **kwargs):
        raise AssertionError("Unmocked async HTTP request forbidden during offline tests")

    # MockTransport and in-process ASGI/TestClient transports remain available.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked_async)
