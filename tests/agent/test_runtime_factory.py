from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from src.agent.runtime_factory import (
    _build_assessment_adapter,
    _load_server_config,
    _project_root,
    _register_single_tool,
    _register_tools,
)
from src.tool.target_registry import TargetRegistry

# ---------------------------------------------------------------------------
# _project_root
# ---------------------------------------------------------------------------


def test_project_root_returns_path() -> None:
    root = _project_root()
    assert isinstance(root, Path)
    assert root.exists()
    assert (root / "src").is_dir()


# ---------------------------------------------------------------------------
# _load_server_config
# ---------------------------------------------------------------------------


def test_load_server_config_missing_file() -> None:
    with mock.patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(RuntimeError, match="servers.json not found"):
            _load_server_config("sv1")


def test_load_server_config_unknown_server() -> None:
    data = {"servers": {"sv1": {"base_url": "http://localhost:8000"}}}
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            with pytest.raises(RuntimeError, match="Server 'sv2' not found"):
                _load_server_config("sv2")


def test_load_server_config_active_server_default() -> None:
    data = {
        "active_server": "sv1",
        "servers": {
            "sv1": {"base_url": "http://localhost:8000", "model": "gpt-4"},
        },
    }
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            cfg = _load_server_config()
            assert cfg["base_url"] == "http://localhost:8000"


def test_load_server_config_explicit_server() -> None:
    data = {
        "servers": {
            "sv1": {"base_url": "http://localhost:8000"},
            "sv2": {"base_url": "http://other:8080", "model": "llama3"},
        },
    }
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            cfg = _load_server_config("sv2")
            assert cfg["base_url"] == "http://other:8080"
            assert cfg["model"] == "llama3"


# ---------------------------------------------------------------------------
# _build_assessment_adapter
# ---------------------------------------------------------------------------


def test_build_assessment_adapter_returns_adapter() -> None:
    """Builds an LLMAssessmentAdapter from a server config."""
    data = {
        "servers": {
            "sv1": {
                "base_url": "http://test-llm:8000",
                "model": "test-model",
                "api_key": "test-key",
                "timeout": 30,
                "temperature": 0.1,
                "max_tokens": 1024,
            },
        },
    }
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            adapter = _build_assessment_adapter("sv1")
            from src.model.llm_assessment_adapter import LLMAssessmentAdapter

            assert isinstance(adapter, LLMAssessmentAdapter)


def test_build_assessment_adapter_defaults() -> None:
    """Uses sensible defaults when config fields are missing."""
    data = {
        "servers": {
            "sv1": {},
        },
    }
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            adapter = _build_assessment_adapter("sv1")
            assert adapter is not None


def test_build_assessment_adapter_model_override() -> None:
    """Explicit model parameter overrides the server config model."""
    data = {
        "servers": {
            "sv1": {"base_url": "http://localhost:8000", "model": "gpt-4"},
        },
    }
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            adapter = _build_assessment_adapter("sv1", model="custom-model")
            assert adapter is not None


# ---------------------------------------------------------------------------
# _register_tools
# ---------------------------------------------------------------------------


def test_register_tools_empty_config() -> None:
    registry = TargetRegistry()
    _register_tools(registry, {})
    assert registry.target_names() == []


def test_register_tools_registers_valid_entries() -> None:
    registry = TargetRegistry()
    config = {
        "zabbix_main": {
            "tool": "zabbix",
            "url": "http://zabbix.example.com",
            "token": "zabbix-token",
            "target": "zabbix",
        },
        "grafana_main": {
            "tool": "grafana",
            "url": "http://grafana.example.com:3000",
            "token": "grafana-token",
            "target": "grafana",
        },
    }
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_tools(registry, config)
    names = registry.target_names()
    assert "zabbix" in names
    assert "grafana" in names


def test_register_tools_skips_invalid_entry() -> None:
    registry = TargetRegistry()
    config = {
        "valid": {
            "tool": "zabbix",
            "url": "http://zabbix.example.com",
            "token": "token",
            "target": "zabbix",
        },
        "invalid": {"tool": "zabbix"},  # missing url and token
    }
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_tools(registry, config)
    assert "zabbix" in registry.target_names()


def test_register_tools_skips_non_dict_entry() -> None:
    registry = TargetRegistry()
    config = {"bad_entry": "not a dict"}
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_tools(registry, config)
    assert registry.target_names() == []


# ---------------------------------------------------------------------------
# _register_single_tool — ZabbixTool construction
# ---------------------------------------------------------------------------


def test_register_single_tool_zabbix() -> None:
    registry = TargetRegistry()
    cfg = {"tool": "zabbix", "url": "http://zabbix.test", "token": "tok"}
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_single_tool(registry, "zabbix1", cfg)
    assert "zabbix1" in registry.target_names()
    tool = registry.get_tool("zabbix1")
    from src.tool.zabbix_tool import ZabbixTool

    assert isinstance(tool, ZabbixTool)


def test_register_single_tool_zabbix_with_timeout() -> None:
    registry = TargetRegistry()
    cfg = {"tool": "zabbix", "url": "http://z.test", "token": "t", "timeout": 30}
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_single_tool(registry, "z", cfg)
    assert "z" in registry.target_names()


# ---------------------------------------------------------------------------
# _register_single_tool — GrafanaTool construction
# ---------------------------------------------------------------------------


def test_register_single_tool_grafana() -> None:
    registry = TargetRegistry()
    cfg = {"tool": "grafana", "url": "http://grafana.test:3000", "token": "tok"}
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_single_tool(registry, "grafana1", cfg)
    assert "grafana1" in registry.target_names()
    tool = registry.get_tool("grafana1")
    from src.tool.grafana_tool import GrafanaTool

    assert isinstance(tool, GrafanaTool)


def test_register_single_tool_grafana_with_timeout() -> None:
    registry = TargetRegistry()
    cfg = {"tool": "grafana", "url": "http://g.test", "token": "t", "timeout": 15}
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_single_tool(registry, "g", cfg)
    assert "g" in registry.target_names()


# ---------------------------------------------------------------------------
# _register_single_tool — target name override
# ---------------------------------------------------------------------------


def test_register_single_tool_target_name_override() -> None:
    registry = TargetRegistry()
    cfg = {
        "tool": "zabbix",
        "url": "http://zabbix.test",
        "token": "tok",
        "target": "custom_name",
    }
    with mock.patch("src.agent.runtime_factory._warn"):
        _register_single_tool(registry, "zabbix1", cfg)
    assert "custom_name" in registry.target_names()
    assert "zabbix1" not in registry.target_names()
