"""Verify recovered native correction, approval boundaries and offline defaults without a live provider."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from copilot.api import create_app
from copilot.config import OFFLINE_LABEL
from copilot.models import Decision, Query
from copilot.provider import ChatProvider
from copilot.workflow import Engine


def native_fixture(engine, monkeypatch, respond):
    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    provider = ChatProvider()
    seen = []

    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": provider.model}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion", "tools"]})
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"model": "explicit-native-fixture", "message": respond(body, len(seen)),
                                         "done": True, "prompt_eval_count": 10, "eval_count": 5})

    provider.transport = httpx.MockTransport(handle)
    engine.provider = provider
    return seen


@pytest.mark.parametrize("denied", [False, True])
def test_native_schema_repair_preserves_negation_and_durable_approval(engine, monkeypatch, denied):
    def respond(body, turn):
        if turn == 1:
            return {"role": "assistant", "tool_calls": [
                {"function": {"name": name, "arguments": {"customer_id": "C001", **args}}}
                for name, args in [("get_customer", {}), ("get_invoices", {}), ("get_tickets", {}),
                                   ("search_contracts", {"query": "renewal notice"})]
            ]}
        if turn == 2:
            return {"role": "assistant", "content": '{"facts":[]}' }
        assert "tools" not in body
        assert set(body["format"]["required"]) == {"analysis", "claims", "recommendations", "abstain"}
        assert body["format"]["properties"]["claims"]["minItems"] == 1
        facts = {f["fact_id"]: f for f in json.loads(body["messages"][-1]["content"])["facts"]}
        claim = {k: facts["C001:score"][k] for k in ("fact_id", "customer_id", "text")}
        return {"role": "assistant", "content": json.dumps({
            "analysis": "risk", "claims": [claim], "abstain": False,
            "recommendations": [{"customer_id": "C001", "action": "payment_plan",
                                 "based_on": ["C001:overdue"], "priority": "urgent"}],
        })}

    seen = native_fixture(engine, monkeypatch, respond)
    suffix = " without creating any CRM task" if denied else " and prepare follow-up actions"
    result = engine.run(Query(message="Analyze renewal risk C001" + suffix, prepare_actions=True,
                              execution_mode="agent"))
    assert len(seen) == 3 and result["draft_repairs"] == 1
    assert result["execution"]["mode"] == "simulated_provider"
    assert result["provider_calls"][-1]["structured_output"]
    assert not result["grounded_answer"]["rejected"] and not result["grounded_answer"]["abstained"]
    assert not engine.store.list_table("tasks")
    if denied:
        assert result["status"] == "completed" and result["proposals"] == []
    else:
        assert result["status"] == "awaiting_approval" and len(result["proposals"]) == 1
        fresh = Engine(engine.store.directory)
        try:
            approved = fresh.decide(result["run_id"], Decision(approved=True, actor="Explicit fixture reviewer"))
            assert approved["status"] == "completed" and len(fresh.store.list_table("tasks")) == 1
        finally:
            fresh.close()


def test_repeated_malformed_native_outputs_exhaust_repairs_without_writes(engine, monkeypatch):
    def respond(body, turn):
        if turn == 1:
            return {"role": "assistant", "tool_calls": [{"function": {
                "name": "get_invoices", "arguments": {"customer_id": "C001"},
            }}]}
        return {"role": "assistant", "content": '{"facts":[]}' }

    seen = native_fixture(engine, monkeypatch, respond)
    result = engine.run(Query(message="Show invoices C001 and prepare actions", prepare_actions=True,
                              execution_mode="agent"))
    assert result["draft_repairs"] == 3 and len(seen) == 5
    assert result["grounded_answer"]["abstained"]
    assert result["proposals"] == [] and engine.store.list_table("tasks") == []


def test_offline_api_and_hybrid_comparison_never_call_a_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "offline")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline mode attempted generative inference")

    monkeypatch.setattr(ChatProvider, "complete", forbidden)
    with TestClient(create_app(tmp_path)) as client:
        health = client.get("/health").json()
        assert health["llm"] == OFFLINE_LABEL and health["ollama"]["status"] == "not_selected"
        result = client.post("/runs", json={"message": "Compare renewal risk C001 and C004 without creating tasks",
                                            "execution_mode": "hybrid"}).json()
        assert result["execution"]["mode"] == "offline" and not result.get("provider_calls")
        assert {r["customer_id"]: r["score"] for r in result["results"]} == {"C001": 85, "C004": 40}
        assert result["proposals"] == [] and client.get("/tasks").json() == []


def test_offline_evaluation_does_not_probe_an_optional_ollama_provider(tmp_path, monkeypatch):
    from copilot import evaluate_phase2

    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(evaluate_phase2, "ROOT", tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Non-live evaluation attempted provider discovery/inference")

    monkeypatch.setattr(ChatProvider, "ollama_status", forbidden)
    monkeypatch.setattr(ChatProvider, "complete", forbidden)
    report = evaluate_phase2.evaluate(live=False)
    assert report["comparison"]["A_deterministic"]["n"] == 4
    assert report["comparison"]["B_LLM_lexical"]["n"] == 0
    assert report["comparison"]["C_LLM_hybrid"]["n"] == 0
