import httpx

from copilot.models import Interpretation, Query, Route


def test_optional_llm_routing_and_explanation(engine, monkeypatch):
    engine.llm.enabled = True

    def structured(system, payload, schema):
        if schema == Route:
            return Route(intent='risk', customer_id='C001', reason='Renewal analysis requested')
        return Interpretation(interpretation='Escalate the account for review.', evidence_ids=['INV-C001-0'])
    monkeypatch.setattr(engine.llm, 'structured', structured)
    run = engine.run(Query(message='Please prioritize this account'))
    assert run['route']['mode'] == 'LLM structured routing'
    assert run['results'][0]['score'] == 85
    assert run['results'][0]['interpretation']['evidence_ids'] == ['INV-C001-0']


def test_invalid_llm_reference_rejected(engine, monkeypatch):
    engine.llm.enabled = True

    def structured(system, payload, schema):
        if schema == Route:
            return Route(intent='risk', customer_id='C001', reason='Requested')
        return Interpretation(interpretation='Unsupported claim', evidence_ids=['FABRICATED'])
    monkeypatch.setattr(engine.llm, 'structured', structured)
    run = engine.run(Query(message='Analyze risk C001'))
    assert run['results'][0]['interpretation'] is None
    assert 'invalid' in run['results'][0]['warnings'][-1]


def test_llm_timeout_falls_back(engine, monkeypatch):
    engine.llm.enabled = True

    def timeout(*args):
        raise httpx.ReadTimeout('simulated provider timeout')
    monkeypatch.setattr(engine.llm, 'structured', timeout)
    run = engine.run(Query(message='Analyze risk C001'))
    assert run['route']['mode'] == 'offline rules'
    assert run['results'][0]['score'] == 85
    assert run['warnings']
