from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from src.agent.deterministic_agent import DeterministicAgent
from src.agent.runtime_factory import create_deterministic_agent


def test_deterministic_agent_runs_pipeline() -> None:
    agent = create_deterministic_agent()
    result = agent.run("check the server health")
    assert "Investigation: check the server health" in result
    assert "Evidence collected: 13" in result
    assert "Successful: 12" in result
    assert "Failed: 1" in result
    assert "Evidence complete: True" in result


def test_pipeline_only() -> None:
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check the server health")
    assert len(request.evidence) > 0
    assert request.intent is not None


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_tools_loaded_from_config(mock_load: mock.Mock) -> None:
    """Verify that tools are registered from tools.json config."""
    mock_load.return_value = {
        "zabbix": {
            "tool": "zabbix",
            "url": "http://test-zabbix/zabbix",
            "token": "test-token",
            "target": "zabbix",
        },
        "grafana": {
            "tool": "grafana",
            "url": "http://test-grafana:3000",
            "token": "test-grafana-token",
            "target": "grafana",
        },
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0
