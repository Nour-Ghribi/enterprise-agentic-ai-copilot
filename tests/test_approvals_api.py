from fastapi.testclient import TestClient
import pytest

from copilot.api import create_app
from copilot.models import Decision, Query
from copilot.workflow import Engine


def test_restart_and_idempotence(engine):
    directory = engine.store.directory
    run = engine.run(Query(message='Analyze risk and prepare follow-up actions', customer_id='C001'))
    assert run['status'] == 'awaiting_approval'
    assert engine.store.list_table('tasks') == []
    fresh = Engine(directory)
    try:
        resumed = fresh.decide(run['run_id'], Decision(approved=True, actor='Test reviewer'))
        assert resumed['status'] == 'completed'
        assert len(fresh.store.list_table('tasks')) == 1
        with pytest.raises(ValueError):
            fresh.decide(run['run_id'], Decision(approved=True, actor='Test reviewer'))
        assert len(fresh.store.list_table('tasks')) == 1
        duplicate = fresh.run(Query(message='Analyze risk and prepare actions', customer_id='C001'))
        assert duplicate['proposals'] == []
        assert any(e['event'] == 'human_decision' for e in fresh.store.list_table('audit'))
    finally:
        fresh.close()


def test_api_main_scenario_and_access_control(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_MODE', 'offline')
    monkeypatch.setenv('APPROVAL_TOKEN', 'test-approval-token')
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/health').json()['indexed_chunks'] == 60
        assert client.get('/customers?search=Atlas').json()[0]['id'] == 'C001'
        result = client.post('/runs', json={'message': 'Which customers have highest renewal risk? Prepare actions.'})
        assert result.status_code == 200
        run = result.json()
        assert len(run['results']) == 30
        assert run['results'][0]['score'] == 85
        assert run['status'] == 'awaiting_approval'
        assert client.get('/tasks').json() == []
        path = f"/runs/{run['run_id']}/decision"
        decision = {'approved': True, 'actor': 'Human reviewer'}
        assert client.post(path, json=decision).status_code == 403
        assert client.post(path, json=decision, headers={'X-Approval-Token': 'wrong'}).status_code == 403
        assert client.get('/tasks').json() == []
        headers = {'X-Approval-Token': 'test-approval-token'}
        assert client.post(path, json={**decision, 'approved': 'yes'}, headers=headers).status_code == 422
        approved = client.post(path, json=decision, headers=headers)
        assert approved.status_code == 200
        assert approved.json()['status'] == 'completed'
        assert len(client.get('/tasks').json()) == len(run['proposals'])
        assert client.post(path, json=decision, headers=headers).status_code == 409
        assert client.get('/customers/C001').json()['erp']['indicators']['overdue_cents'] == 1020000
        assert client.get('/contracts/C001/pdf').headers['content-type'] == 'application/pdf'
        assert client.get('/runs/not-a-run').status_code == 404
        assert client.post('/runs', json={'message': 'Customer C999'}).status_code == 404
        assert client.post('/search', json={'query': 'renewal', 'limit': 999}).status_code == 422
        assert client.get('/customers/invalid').status_code == 422


def test_rejection_and_cross_run_action_binding(engine):
    from copilot.actions import apply_decision
    run = engine.run(Query(message='Analyze risk and prepare actions', customer_id='C004'))
    with pytest.raises(ValueError):
        apply_decision(engine.store, 'another-run', [run['proposals'][0]['id']], Decision(approved=True, actor='Human'))
    rejected = engine.decide(run['run_id'], Decision(approved=False, actor='Human'))
    assert rejected['proposals'][0]['status'] == 'rejected'
    assert engine.store.list_table('tasks') == []
