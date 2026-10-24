import pytest

from copilot.workflow import Engine


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_MODE', 'offline')
    instance = Engine(tmp_path / 'business')
    yield instance
    instance.close()
