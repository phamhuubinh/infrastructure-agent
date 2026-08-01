from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from src.agent.runtime_factory import (
    _build_assessment_adapter,
    _register_single_tool,
    _register_tools,
    create_deterministic_agent,
)
from src.shared.config import OrionConfig, _reset_config
from src.shared.config_errors import InvalidConfigValueError
from src.shared.secrets import DEFAULT_TOOL_SECRETS_PATH
from src.tool.target_registry import TargetRegistry

# ---------------------------------------------------------------------------
# Fixture to reset OrionConfig singleton between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_orion_config() -> None:
    """Reset the global OrionConfig singleton before each test."""
    _reset_config()


# ---------------------------------------------------------------------------
# OrionConfig — server loading (replaces old _load_server_config)
# ---------------------------------------------------------------------------


def test_config_missing_servers_file() -> None:
    """A missing model registry loads as valid setup mode."""
    config = OrionConfig.load(project_root=Path("/nonexistent/path"))
    assert config.servers == {}
    assert config.active_server_name == ""


def test_default_tool_credentials_path_is_system_wide() -> None:
    assert DEFAULT_TOOL_SECRETS_PATH == Path("/etc/orion/tool-credentials.json")


def test_agent_starts_with_setup_adapter_when_no_model_is_configured(
    tmp_path: Path,
) -> None:
    mock_config = OrionConfig(servers={}, active_server_name="", tools={})
    with mock.patch("src.agent.runtime_factory.get_config", return_value=mock_config):
        agent = create_deterministic_agent(
            target_store_path=str(tmp_path / "targets.json")
        )

    from src.model.unconfigured_adapter import UnconfiguredAssessmentAdapter

    assert isinstance(agent.assessment_model, UnconfiguredAssessmentAdapter)
    assert agent.health_check() is False


def test_config_unknown_server_in_build_adapter() -> None:
    """_build_assessment_adapter raises InvalidConfigValueError for unknown server."""
    mock_config = OrionConfig(
        servers={"sv1": {"base_url": "http://localhost:8000"}},
        active_server_name="sv1",
    )
    with (
        mock.patch("src.shared.config._config", mock_config),
        mock.patch("src.agent.runtime_factory.get_config", return_value=mock_config),
    ):
        with pytest.raises(InvalidConfigValueError, match="sv2"):
            _build_assessment_adapter("sv2")


def test_config_active_server_default() -> None:
    """OrionConfig.active_server returns the active server config."""
    config = OrionConfig(
        servers={
            "sv1": {"base_url": "http://localhost:8000", "model": "gpt-4"},
        },
        active_server_name="sv1",
    )
    assert config.active_server["base_url"] == "http://localhost:8000"


def test_config_applies_active_server_environment_overrides() -> None:
    config = OrionConfig(
        servers={"sv1": {"base_url": "http://old", "model": "old"}},
        active_server_name="sv1",
    )
    with mock.patch.dict(
        "os.environ",
        {
            "ORION_LLM_BASE_URL": "http://docker-host:8000",
            "ORION_LLM_MODEL": "new-model",
            "ORION_LLM_API_KEY": "secret",
        },
    ):
        OrionConfig._apply_llm_env_overrides(config)

    assert config.active_server == {
        "base_url": "http://docker-host:8000",
        "model": "new-model",
        "api_key": "secret",
    }


def test_config_uses_mounted_tool_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "tools.json").write_text(
        json.dumps(
            {
                "grafana": {
                    "tool": "grafana",
                    "target": "grafana",
                    "timeout": 10,
                }
            }
        )
    )
    mounted_secret = tmp_path / "orion-tool-credentials.json"
    mounted_secret.write_text(
        json.dumps(
            {
                "grafana": {
                    "url": "http://grafana.internal:3000",
                    "token": "private-token",
                }
            }
        )
    )
    monkeypatch.setenv("ORION_SECRETS_PATH", str(mounted_secret))

    config = OrionConfig.load(project_root=project_root)

    assert config.tools["grafana"] == {
        "tool": "grafana",
        "target": "grafana",
        "timeout": 10,
        "url": "http://grafana.internal:3000",
        "token": "private-token",
    }
    assert config.secrets["grafana"]["token"] == "private-token"


# ---------------------------------------------------------------------------
# _build_assessment_adapter
# ---------------------------------------------------------------------------


def test_build_assessment_adapter_returns_adapter() -> None:
    """Builds an LLMAssessmentAdapter from a server config."""
    mock_config = OrionConfig(
        servers={
            "sv1": {
                "base_url": "http://test-llm:8000",
                "model": "test-model",
                "api_key": "test-key",
                "timeout": 30,
                "temperature": 0.1,
                "max_tokens": 1024,
            },
        },
        active_server_name="sv1",
    )
    with mock.patch("src.agent.runtime_factory.get_config", return_value=mock_config):
        adapter = _build_assessment_adapter("sv1")
        from src.model.llm_assessment_adapter import LLMAssessmentAdapter

        assert isinstance(adapter, LLMAssessmentAdapter)


def test_build_assessment_adapter_defaults() -> None:
    """Uses server config with minimal fields and model defaults."""
    mock_config = OrionConfig(
        servers={"sv1": {"base_url": "http://localhost:8000"}},
        active_server_name="sv1",
    )
    with mock.patch("src.agent.runtime_factory.get_config", return_value=mock_config):
        adapter = _build_assessment_adapter("sv1")
        assert adapter is not None


def test_build_assessment_adapter_model_override() -> None:
    """Explicit model parameter overrides the server config model."""
    mock_config = OrionConfig(
        servers={"sv1": {"base_url": "http://localhost:8000", "model": "gpt-4"}},
        active_server_name="sv1",
    )
    with mock.patch("src.agent.runtime_factory.get_config", return_value=mock_config):
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
    from typing import Any

    registry = TargetRegistry()
    config: dict[str, dict[str, Any]] = {"bad_entry": "not a dict"}  # type: ignore[dict-item]
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
