"""Regressions observed with real Qwen inference: duplicated evidence and optional contract scope."""

import json

import httpx
import pytest
from pydantic import ValidationError

from copilot.agent import generation_messages
from copilot.models import ContractSearch, Query, Search
from copilot.provider import ChatProvider


def test_generation_deduplicates_facts_without_changing_persisted_evidence():
    fact = {
        "fact_id": "C001:overdue", "customer_id": "C001", "text": "C001 has an overdue balance.",
        "kind": "calculated", "predicate": "overdue_cents", "value": 1020000,
        "source_ids": ["INV-C001-1"], "citation": None,
    }
    passage = {"text": "60 days notice is required.", "page": 1, "source_sha256": "a" * 64}
    observation = {"untrusted_evidence": True, "facts": [fact], "passages": [passage]}
    messages = [
        {"role": "system", "content": "Keep the approval policy."},
        {"role": "tool", "tool_call_id": "first", "content": json.dumps(observation)},
        {"role": "tool", "tool_call_id": "second", "content": json.dumps(observation)},
    ]
    original = json.dumps(messages)
    rendered = generation_messages(messages)
    facts = [f for m in rendered if m["role"] == "tool" for f in json.loads(m["content"]).get("facts", [])]
    assert len(facts) == 1 and facts[0]["text"] == fact["text"]
    assert json.loads(rendered[-1]["content"])["passages"] == [passage]
    assert rendered[0] == messages[0] and json.dumps(messages) == original
    assert len(json.dumps(rendered)) < len(original)


def test_earlier_tool_errors_remain_visible_after_compaction():
    messages = [
        {"role": "tool", "content": '{"error":"ValidationError","message":"customer_id required"}'},
        {"role": "tool", "content": '{"facts":[]}'},
    ]
    assert json.loads(generation_messages(messages)[0]["content"])["message"] == "customer_id required"


def test_latest_tool_error_does_not_erase_previously_observed_evidence():
    fact = {"fact_id": "C001:overdue", "customer_id": "C001", "text": "Observed overdue balance.",
            "kind": "calculated", "predicate": "overdue_cents", "value": 1020000}
    messages = [
        {"role": "tool", "content": json.dumps({"facts": [fact]})},
        {"role": "tool", "content": '{"error":"RuntimeError","message":"Temporary tool failure"}'},
    ]
    compacted = [json.loads(m["content"]) for m in generation_messages(messages)]
    assert compacted[0]["facts"][0]["fact_id"] == "C001:overdue"
    assert compacted[1]["message"] == "Temporary tool failure"


def test_agent_contract_search_requires_customer_without_changing_general_search():
    assert Search(query="renewal").customer_id is None
    with pytest.raises(ValidationError):
        ContractSearch(query="renewal")
    assert ContractSearch(query="renewal", customer_id="C002").customer_id == "C002"


@pytest.mark.parametrize("malformed", [False, True])
def test_rejected_model_draft_can_be_corrected_without_accepting_bad_claims(engine, malformed):
    engine.provider.mode = "openai"
    engine.provider.key = "explicit-http-fixture"
    responses = []

    def respond(request):
        body = json.loads(request.content)
        responses.append(body)
        if len(responses) == 1:
            message = {"role": "assistant", "tool_calls": [{
                "id": "read-1", "type": "function", "function": {
                    "name": "get_invoices", "arguments": '{"customer_id":"C001"}',
                },
            }]}
        else:
            payload = next(json.loads(m["content"]) for m in body["messages"] if m["role"] == "tool")
            source = next(f for f in payload["facts"] if f["fact_id"] == "C001:overdue")
            claim = {k: source[k] for k in ("fact_id", "customer_id", "text")}
            if len(responses) == 2:
                claim["text"] = "Invented unsupported balance."
            content = "Not a JSON object" if malformed and len(responses) == 2 else json.dumps({"claims": [claim]})
            message = {"role": "assistant", "content": content}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    engine.provider.transport = httpx.MockTransport(respond)
    result = engine.run(Query(message="Show the overdue balance C001", execution_mode="agent"))
    assert len(responses) == 3 and result["draft_repairs"] == 1
    assert result["provider_calls"][1]["validation_feedback"]
    assert result["grounded_answer"]["verified_claims"][0]["fact_id"] == "C001:overdue"
    assert not result["grounded_answer"]["rejected"] and not result["grounded_answer"]["abstained"]
    assert "Invented unsupported balance" not in result["answer"]


def test_ollama_structured_correction_sends_json_schema_without_tools(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    local = ChatProvider()
    schema = {"type": "object", "properties": {"abstain": {"type": "boolean"}}, "required": ["abstain"]}

    def respond(request):
        payload = json.loads(request.content)
        assert payload["format"] == schema and "tools" not in payload
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"abstain":true}'}})

    local.transport = httpx.MockTransport(respond)
    message, metadata = local.complete([{"role": "user", "content": "Verify evidence"}], response_schema=schema)
    assert json.loads(message["content"])["abstain"]
    assert metadata["structured_output"] and metadata["execution"] == "simulated_provider"
