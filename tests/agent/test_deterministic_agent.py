from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from src.agent.deterministic_agent import DeterministicAgent
from src.agent.runtime_factory import create_deterministic_agent
from src.agent.runtime_factory import _load_tools_config, _SUPPORTED_TOOL_TYPES


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


# ---------------------------------------------------------------------------
# tools.json loading
# ---------------------------------------------------------------------------


def test_no_tools_file_returns_empty() -> None:
    with mock.patch("pathlib.Path.exists", return_value=False):
        config = _load_tools_config()
        assert config == {}


def test_invalid_json_returns_empty() -> None:
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value="not json"):
            config = _load_tools_config()
            assert config == {}


def test_non_dict_json_returns_empty() -> None:
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value='"string"'):
            config = _load_tools_config()
            assert config == {}


def test_oserror_returns_empty() -> None:
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", side_effect=OSError("denied")):
            config = _load_tools_config()
            assert config == {}


def test_valid_config_loaded() -> None:
    data = {
        "zabbix": {
            "tool": "zabbix", "url": "http://z", "token": "t",
            "target": "zabbix",
        },
    }
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            config = _load_tools_config()
            assert config == data


# ---------------------------------------------------------------------------
# Tool registration edge cases
# ---------------------------------------------------------------------------


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_tools_loaded_from_config(mock_load: mock.Mock) -> None:
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


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_missing_tool_field_skips_entry(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "bad_entry": {"url": "http://test"},
    }
    # Should not crash — just skip
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_unknown_tool_type_skips_entry(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "vmware": {
            "tool": "vmware", "url": "http://v", "token": "t",
        },
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_missing_required_fields_skips_entry(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "zabbix": {
            "tool": "zabbix",
            # missing url and token
        },
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_duplicate_target_name_handled(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "zabbix1": {
            "tool": "zabbix", "url": "http://z1", "token": "t1",
            "target": "zabbix",
        },
        "zabbix2": {
            "tool": "zabbix", "url": "http://z2", "token": "t2",
            "target": "zabbix",  # same target name as zabbix1
        },
    }
    # Should not crash — second entry should warn about duplicate
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_non_dict_entry_skipped(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "bad_entry": "not a dict",
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


# ---------------------------------------------------------------------------
# Supported tool types
# ---------------------------------------------------------------------------


def test_supported_tool_types_defined() -> None:
    assert "zabbix" in _SUPPORTED_TOOL_TYPES
    assert "grafana" in _SUPPORTED_TOOL_TYPES
    for tool_type, required in _SUPPORTED_TOOL_TYPES.items():
        assert "url" in required
        assert "token" in required
