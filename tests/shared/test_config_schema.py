from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from src.shared.config_schema import (
    ConfigValidationError,
    ServerConfig,
    ServersConfig,
    TargetEntry,
    TargetsConfig,
    ToolEntry,
    _validate_tools_dict,
    validate_all_configs,
)

# ---------------------------------------------------------------------------
# ServerConfig
# ---------------------------------------------------------------------------


class TestServerConfig:
    def test_valid_minimal(self) -> None:
        cfg = ServerConfig.model_validate({"base_url": "http://localhost:8000"})
        assert cfg.base_url == "http://localhost:8000"
        assert cfg.model == "gpt-4"
        assert cfg.timeout == 60
        assert cfg.temperature == 0.0
        assert cfg.provider_max_tokens is None

    def test_valid_full(self) -> None:
        cfg = ServerConfig.model_validate(
            {
                "base_url": "http://example.com",
                "api_key": "sk-123",
                "model": "qwen",
                "provider": "openai",
                "timeout": 120,
                "temperature": 0.7,
            }
        )
        assert cfg.model == "qwen"
        assert cfg.timeout == 120

    def test_invalid_timeout_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            ServerConfig.model_validate({"base_url": "http://x", "timeout": 0})
        with pytest.raises(ValueError, match="timeout"):
            ServerConfig.model_validate({"base_url": "http://x", "timeout": 301})

    def test_invalid_temperature_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="temperature"):
            ServerConfig.model_validate({"base_url": "http://x", "temperature": -0.1})
        with pytest.raises(ValueError, match="temperature"):
            ServerConfig.model_validate({"base_url": "http://x", "temperature": 2.1})

    def test_missing_base_url(self) -> None:
        with pytest.raises(ValueError, match="base_url"):
            ServerConfig.model_validate({})


# ---------------------------------------------------------------------------
# ServersConfig
# ---------------------------------------------------------------------------


class TestServersConfig:
    def test_empty_registry_is_valid(self) -> None:
        cfg = ServersConfig.model_validate({"active_server": "", "servers": {}})
        assert cfg.active_server == ""
        assert cfg.servers == {}

    def test_valid(self) -> None:
        cfg = ServersConfig.model_validate(
            {
                "active_server": "sv1",
                "servers": {
                    "sv1": {"base_url": "http://localhost:8000"},
                },
            }
        )
        assert cfg.active_server == "sv1"

    def test_active_server_not_in_servers(self) -> None:
        with pytest.raises(ValueError, match="active_server 'sv2' is not defined"):
            ServersConfig.model_validate(
                {
                    "active_server": "sv2",
                    "servers": {
                        "sv1": {"base_url": "http://localhost:8000"},
                    },
                }
            )

    def test_inactive_registry_with_models_is_valid(self) -> None:
        cfg = ServersConfig.model_validate(
            {
                "servers": {"sv1": {"base_url": "http://x"}},
            }
        )
        assert cfg.active_server == ""

    def test_missing_servers_is_valid_when_active_is_empty(self) -> None:
        cfg = ServersConfig.model_validate({})
        assert cfg.active_server == ""
        assert cfg.servers == {}


# ---------------------------------------------------------------------------
# ToolEntry
# ---------------------------------------------------------------------------


class TestToolEntry:
    def test_valid_minimal(self) -> None:
        entry = ToolEntry.model_validate({"tool": "zabbix"})
        assert entry.tool == "zabbix"
        assert entry.url is None

    def test_valid_with_extra_fields(self) -> None:
        entry = ToolEntry.model_validate(
            {
                "tool": "grafana",
                "url": "http://g:3000",
                "token": "tok",
                "timeout": 30,
                "target": "grafana",
                "extra": "ignored",
            }
        )
        assert entry.tool == "grafana"
        assert entry.url == "http://g:3000"

    def test_missing_tool_field(self) -> None:
        with pytest.raises(ValueError, match="tool"):
            ToolEntry.model_validate({"url": "http://x"})


# ---------------------------------------------------------------------------
# _validate_tools_dict
# ---------------------------------------------------------------------------


class TestValidateToolsDict:
    def test_valid_entries(self) -> None:
        data = {
            "zabbix": {"tool": "zabbix", "url": "http://z"},
            "grafana": {"tool": "grafana", "token": "t"},
        }
        result = _validate_tools_dict(data)
        assert len(result) == 2
        assert isinstance(result["zabbix"], ToolEntry)

    def test_non_dict_entry(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            _validate_tools_dict({"bad": "not_a_dict"})

    def test_invalid_entry(self) -> None:
        with pytest.raises(ValueError, match="tool"):
            _validate_tools_dict({"bad": {"url": "http://x"}})


# ---------------------------------------------------------------------------
# TargetEntry / TargetsConfig
# ---------------------------------------------------------------------------


class TestTargetEntry:
    def test_valid_minimal(self) -> None:
        entry = TargetEntry.model_validate({"backend": "local"})
        assert entry.backend == "local"

    def test_valid_with_extra(self) -> None:
        entry = TargetEntry.model_validate(
            {
                "backend": "ssh",
                "host": "monitor",
                "user": "monitor",
            }
        )
        assert entry.host == "monitor"

    def test_missing_backend(self) -> None:
        with pytest.raises(ValueError, match="backend"):
            TargetEntry.model_validate({})


class TestTargetsConfig:
    def test_valid(self) -> None:
        cfg = TargetsConfig.model_validate(
            {
                "default": "localhost",
                "targets": {
                    "localhost": {"backend": "local"},
                },
            }
        )
        assert cfg.default == "localhost"

    def test_missing_targets(self) -> None:
        with pytest.raises(ValueError, match="targets"):
            TargetsConfig.model_validate({"default": "localhost"})

    def test_no_default(self) -> None:
        cfg = TargetsConfig.model_validate(
            {
                "targets": {"localhost": {"backend": "local"}},
            }
        )
        assert cfg.default is None


# ---------------------------------------------------------------------------
# validate_all_configs
# ---------------------------------------------------------------------------


class TestValidateAllConfigs:
    def test_all_valid(self, tmp_path: Path) -> None:
        """All three config files are valid."""
        # servers.json
        (tmp_path / "servers.json").write_text(
            json.dumps(
                {
                    "active_server": "sv1",
                    "servers": {
                        "sv1": {"base_url": "http://localhost:8000", "model": "qwen"},
                    },
                }
            )
        )
        # tools.json
        (tmp_path / "tools.json").write_text(
            json.dumps(
                {
                    "zabbix": {"tool": "zabbix", "url": "http://z", "token": "t"},
                    "grafana": {"tool": "grafana", "url": "http://g", "token": "t"},
                    "internet": {"tool": "internet"},
                }
            )
        )
        # targets.json
        (tmp_path / "targets.json").write_text(
            json.dumps(
                {
                    "default": "localhost",
                    "targets": {
                        "localhost": {"backend": "local"},
                    },
                }
            )
        )

        with mock.patch(
            "src.shared.config_schema._project_root", return_value=tmp_path
        ):
            # Should not raise
            validate_all_configs()

    def test_servers_json_missing_is_setup_mode(self, tmp_path: Path) -> None:
        """A missing model registry is valid before first model setup."""
        # Only tools.json and targets.json exist
        (tmp_path / "tools.json").write_text(
            json.dumps(
                {
                    "zabbix": {"tool": "zabbix"},
                }
            )
        )
        (tmp_path / "targets.json").write_text(
            json.dumps(
                {
                    "targets": {"localhost": {"backend": "local"}},
                }
            )
        )

        with mock.patch(
            "src.shared.config_schema._project_root", return_value=tmp_path
        ):
            validate_all_configs()

    def test_servers_json_invalid(self, tmp_path: Path) -> None:
        """Invalid servers.json triggers an error."""
        (tmp_path / "servers.json").write_text(
            json.dumps(
                {
                    "active_server": "sv99",  # not in servers dict
                    "servers": {
                        "sv1": {"base_url": "http://localhost:8000"},
                    },
                }
            )
        )
        (tmp_path / "tools.json").write_text(
            json.dumps(
                {
                    "zabbix": {"tool": "zabbix"},
                }
            )
        )
        (tmp_path / "targets.json").write_text(
            json.dumps(
                {
                    "targets": {"localhost": {"backend": "local"}},
                }
            )
        )

        with mock.patch(
            "src.shared.config_schema._project_root", return_value=tmp_path
        ):
            with pytest.raises(ConfigValidationError) as exc_info:
                validate_all_configs()
            error_msgs = "\n".join(exc_info.value.errors)
            assert "servers.json" in error_msgs
            assert "sv99" in error_msgs

    def test_tools_json_invalid(self, tmp_path: Path) -> None:
        """Invalid tools.json triggers an error."""
        (tmp_path / "servers.json").write_text(
            json.dumps(
                {
                    "active_server": "sv1",
                    "servers": {
                        "sv1": {"base_url": "http://localhost:8000"},
                    },
                }
            )
        )
        (tmp_path / "tools.json").write_text(
            json.dumps(
                {
                    "bad_entry": {"url": "http://x"},  # missing 'tool' field
                }
            )
        )
        (tmp_path / "targets.json").write_text(
            json.dumps(
                {
                    "targets": {"localhost": {"backend": "local"}},
                }
            )
        )

        with mock.patch(
            "src.shared.config_schema._project_root", return_value=tmp_path
        ):
            with pytest.raises(ConfigValidationError) as exc_info:
                validate_all_configs()
            error_msgs = "\n".join(exc_info.value.errors)
            assert "tools.json" in error_msgs

    def test_tools_json_missing_ok(self, tmp_path: Path) -> None:
        """tools.json is optional — no error if missing."""
        (tmp_path / "servers.json").write_text(
            json.dumps(
                {
                    "active_server": "sv1",
                    "servers": {
                        "sv1": {"base_url": "http://localhost:8000"},
                    },
                }
            )
        )
        (tmp_path / "targets.json").write_text(
            json.dumps(
                {
                    "targets": {"localhost": {"backend": "local"}},
                }
            )
        )

        with mock.patch(
            "src.shared.config_schema._project_root", return_value=tmp_path
        ):
            # Should not raise
            validate_all_configs()

    def test_targets_json_invalid(self, tmp_path: Path) -> None:
        """Invalid targets.json triggers an error."""
        (tmp_path / "servers.json").write_text(
            json.dumps(
                {
                    "active_server": "sv1",
                    "servers": {
                        "sv1": {"base_url": "http://localhost:8000"},
                    },
                }
            )
        )
        (tmp_path / "tools.json").write_text(
            json.dumps(
                {
                    "zabbix": {"tool": "zabbix"},
                }
            )
        )
        (tmp_path / "targets.json").write_text(
            json.dumps(
                {
                    "targets": {"localhost": {}},  # missing 'backend' field
                }
            )
        )

        with mock.patch(
            "src.shared.config_schema._project_root", return_value=tmp_path
        ):
            with pytest.raises(ConfigValidationError) as exc_info:
                validate_all_configs()
            error_msgs = "\n".join(exc_info.value.errors)
            assert "targets.json" in error_msgs

    def test_multiple_errors_collected(self, tmp_path: Path) -> None:
        """All errors are collected before raising."""
        # servers.json: missing (valid setup mode)
        # tools.json: invalid (error)
        # targets.json: invalid (error)
        (tmp_path / "tools.json").write_text(
            json.dumps(
                {
                    "bad": {"url": "http://x"},  # missing tool field
                }
            )
        )
        (tmp_path / "targets.json").write_text(
            json.dumps(
                {
                    "targets": {"x": {}},  # missing backend
                }
            )
        )

        with mock.patch(
            "src.shared.config_schema._project_root", return_value=tmp_path
        ):
            with pytest.raises(ConfigValidationError) as exc_info:
                validate_all_configs()
            # 2 errors: tools invalid and targets invalid
            assert len(exc_info.value.errors) == 2

    def test_config_validation_error_str(self) -> None:
        """ConfigValidationError has readable str output."""
        exc = ConfigValidationError(
            [
                "servers.json: something wrong",
                "tools.json: another issue",
            ]
        )
        msg = str(exc)
        assert "Configuration validation failed" in msg
        assert "servers.json" in msg
        assert "tools.json" in msg
