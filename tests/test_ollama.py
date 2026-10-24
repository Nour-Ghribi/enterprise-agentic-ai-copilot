import json

import httpx
import pytest

from copilot.models import Query
from copilot.provider import ChatProvider


def provider(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:1.7b")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    return ChatProvider()


def test_ollama_needs_no_key(monkeypatch):
    local = provider(monkeypatch)
    assert local.configured and not local.key and local.is_ollama


def test_native_tool_calls_and_replay(monkeypatch):
    local = provider(monkeypatch)
    bodies = []

    def handle(request):
        assert "authorization" not in request.headers
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3:1.7b",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "get_customer", "arguments": {"customer_id": "C003"}}}
                    ],
                },
                "prompt_eval_count": 40,
                "eval_count": 12,
                "done": True,
            },
        )

    local.transport = httpx.MockTransport(handle)
    result, meta = local.complete(
        [{"role": "user", "content": "contact C003"}],
        [{"type": "function", "function": {"name": "get_customer"}}],
    )
    call = result["tool_calls"][0]
    assert call["id"] and json.loads(call["function"]["arguments"]) == {"customer_id": "C003"}
    assert meta["usage"]["total_tokens"] == 52 and meta["execution"] == "simulated_provider"
    local.complete(
        [
            {"role": "user", "content": "contact C003"},
            result,
            {"role": "tool", "tool_call_id": call["id"], "content": '{"facts":[]}'},
        ]
    )
    assert bodies[1]["messages"][-1]["tool_name"] == "get_customer"
    assert isinstance(bodies[1]["messages"][1]["tool_calls"][0]["function"]["arguments"], dict)
    assert not bodies[0]["stream"] and bodies[0]["think"] is False


@pytest.mark.parametrize(
    "models,capabilities,expected",
    [
        ([], [], "model_missing"),
        (["qwen3:1.7b"], ["completion"], "tools_not_advertised"),
        (["qwen3:1.7b"], ["tools", "completion"], "ready"),
    ],
)
def test_discovery_distinguishes_missing_model_and_tools(monkeypatch, models, capabilities, expected):
    local = provider(monkeypatch)

    def handle(request):
        return httpx.Response(
            200,
            json={"models": [{"name": name} for name in models]}
            if request.url.path == "/api/tags"
            else {"capabilities": capabilities},
        )

    local.transport = httpx.MockTransport(handle)
    status = local.ollama_status(refresh=True)
    assert status["status"] == expected and not status["inference_verified"]


def test_absent_server_never_claims_inference(monkeypatch):
    local = provider(monkeypatch)

    def fail(request):
        raise httpx.ConnectError("Unavailable")

    local.transport = httpx.MockTransport(fail)
    assert local.ollama_status()["status"] == "server_unreachable"


def test_ollama_unavailable_returns_labeled_baseline(engine, monkeypatch):
    local = provider(monkeypatch)
    local.transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"models": []}))
    engine.provider = local
    result = engine.run(Query(message="Compare renewal risk C001 and C004 without creating tasks"))
    assert result["execution"]["mode"] == "offline" and not result.get("provider_calls")
    assert len(result["results"]) == 2
    assert any("model_missing" in w for w in result["warnings"])


def test_remote_ollama_endpoint_is_rejected(monkeypatch):
    local = provider(monkeypatch)
    local.ollama_base = "https://ollama.com"
    with pytest.raises(ValueError):
        local.complete([{"role": "user", "content": "test"}])


def test_cloud_backed_ollama_tag_is_rejected(monkeypatch):
    local = provider(monkeypatch)
    local.model = "qwen3:cloud"
    with pytest.raises(ValueError):
        local.complete([{"role": "user", "content": "test"}])


def test_native_ollama_langgraph_loop_uses_actual_protocol(engine, monkeypatch):
    local = provider(monkeypatch)
    rounds = []

    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:1.7b"}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["tools", "completion"]})
        body = json.loads(request.content)
        rounds.append(body)
        if len(rounds) == 1:
            message = {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "get_customer", "arguments": {"customer_id": "C003"}}}],
            }
        else:
            payload = json.loads(body["messages"][-1]["content"])
            source = next(f for f in payload["facts"] if f["fact_id"] == "CT-C003")
            message = {
                "role": "assistant",
                "content": json.dumps(
                    {"claims": [{k: source[k] for k in ("fact_id", "customer_id", "text")}]}
                ),
            }
        return httpx.Response(
            200, json={"model": "qwen3:1.7b", "message": message, "prompt_eval_count": 10, "eval_count": 5}
        )

    local.transport = httpx.MockTransport(handle)
    engine.provider = local
    result = engine.run(Query(message="Who is the contact for C003?", execution_mode="agent"))
    assert result["grounded_answer"]["verified_claims"][0]["fact_id"] == "CT-C003"
    assert len(rounds) == 2 and result["execution"]["mode"] == "simulated_provider"


@pytest.mark.ollama
@pytest.mark.parametrize(
    "name,question",
    [
        ("contact", "Who is the contact for C003?"),
        ("invoice", "Show overdue invoices for C001."),
        ("contract", "What is the non-renewal notice for C002? Give a PDF citation."),
        (
            "comparison",
            "Compare renewal risk C001 and C004 using accounts, invoices, tickets and contracts, recommend next actions without creating any CRM task.",
        ),
    ],
)
def test_real_local_ollama_e2e(tmp_path, monkeypatch, name, question):
    from copilot.local_check import local_case
    from copilot.workflow import Engine

    local = provider(monkeypatch)
    status = local.ollama_status(refresh=True)
    if status["status"] != "ready":
        pytest.skip("Real Ollama E2E not executed: " + status["status"])
    monkeypatch.setenv("CRM_MODE", "mock")
    monkeypatch.setenv("ERP_MODE", "mock")
    instance = Engine(tmp_path)
    try:
        assert local_case(instance, name, question)["status"] == "passed"
    finally:
        instance.close()


@pytest.mark.ollama
def test_real_local_ollama_durable_approval(tmp_path, monkeypatch):
    from copilot.local_check import approval_case
    from copilot.workflow import Engine

    local = provider(monkeypatch)
    status = local.ollama_status(refresh=True)
    if status["status"] != "ready":
        pytest.skip("Real Ollama approval E2E not executed: " + status["status"])
    monkeypatch.setenv("CRM_MODE", "mock")
    monkeypatch.setenv("ERP_MODE", "mock")
    instance = Engine(tmp_path)
    try:
        assert approval_case(instance)["status"] == "passed"
    finally:
        instance.close()
