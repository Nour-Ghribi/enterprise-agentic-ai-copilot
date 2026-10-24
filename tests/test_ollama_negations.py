"""Real local inference must preserve denied CRM writes even with the explicit action flag."""

import pytest

from copilot.local_check import local_provider
from copilot.models import Query
from copilot.workflow import Engine


@pytest.mark.ollama
@pytest.mark.parametrize(
    "message",
    [
        "Analyze renewal risk C001 and recommend follow-up actions, but do not create any CRM task.",
        "Analyse le risque de renouvellement C004 et recommande des actions, sans créer de tâche CRM.",
    ],
)
def test_real_ollama_negation_overrides_action_flag(tmp_path, monkeypatch, message):
    status = local_provider().ollama_status(refresh=True)
    if status["status"] != "ready":
        pytest.skip("Real Ollama negation check not executed: " + status["status"])
    for key, value in {
        "LLM_MODE": "ollama", "LLM_PROVIDER": "ollama", "CRM_MODE": "mock", "ERP_MODE": "mock",
    }.items():
        monkeypatch.setenv(key, value)
    instance = Engine(tmp_path)
    try:
        result = instance.run(Query(message=message, execution_mode="hybrid", prepare_actions=True))
        assert result["execution"]["mode"] == "local_ollama"
        assert any(call["execution"] == "local_ollama" for call in result["provider_calls"])
        assert result["grounded_answer"]["verified_claims"] and not result["grounded_answer"]["abstained"]
        assert result["action_policy"]["explicitly_suppressed"]
        assert result["status"] == "completed" and not result["proposals"]
        assert instance.store.list_table("tasks") == []
    finally:
        instance.close()
