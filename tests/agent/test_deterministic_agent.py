from __future__ import annotations

from src.agent.deterministic_agent import DeterministicAgent
from src.agent.runtime_factory import create_deterministic_agent


def test_deterministic_agent_runs_pipeline() -> None:
    agent = create_deterministic_agent(register_zabbix=False, register_grafana=False)
    result = agent.run("check the server health")
    assert "Investigation: check the server health" in result
    assert "Evidence collected: 13" in result
    assert "Successful: 12" in result
    assert "Failed: 1" in result
    assert "Evidence complete: True" in result


def test_pipeline_only() -> None:
    agent = create_deterministic_agent(register_zabbix=False, register_grafana=False)
    request = agent.execute_pipeline_only("check the server health")
    assert len(request.evidence) > 0
    assert request.intent is not None
