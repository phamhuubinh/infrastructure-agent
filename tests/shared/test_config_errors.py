"""Tests for configuration error handling policy (Task 012)."""

from __future__ import annotations

from collections.abc import Sequence

from src.shared.config_errors import (
    ConfigurationError,
    InvalidConfigValueError,
    MissingConfigFileError,
    MissingRequiredKeyError,
    format_error_batch,
)


class TestConfigurationError:
    """Tests for the base ConfigurationError class."""

    def test_format_includes_all_fields(self) -> None:
        err = ConfigurationError(
            file="servers.json",
            key="sv1.base_url",
            expected="string",
            received="null",
        )
        formatted = err.format()
        assert "servers.json" in formatted
        assert "sv1.base_url" in formatted
        assert "string" in formatted
        assert "null" in formatted

    def test_str_returns_formatted_message(self) -> None:
        err = ConfigurationError(
            file="tools.json",
            key="zabbix.url",
            expected="http://...",
            received="None",
        )
        message = str(err)
        assert "tools.json" in message
        assert "zabbix.url" in message

    def test_attributes_accessible(self) -> None:
        err = ConfigurationError(
            file="tools.json",
            key="grafana.timeout",
            expected="int",
            received="abc",
        )
        assert err.file == "tools.json"
        assert err.key == "grafana.timeout"
        assert err.expected == "int"
        assert err.received == "abc"


class TestMissingConfigFileError:
    """Tests for MissingConfigFileError."""

    def test_is_configuration_error(self) -> None:
        err = MissingConfigFileError(
            file="servers.json",
            key="(file)",
            expected="existing file",
            received="not found",
        )
        assert isinstance(err, ConfigurationError)
        assert isinstance(err, MissingConfigFileError)

    def test_format_includes_file_name(self) -> None:
        err = MissingConfigFileError(
            file="targets.json",
            key="(file)",
            expected="existing file",
            received="not found",
        )
        assert "targets.json" in str(err)
        assert "not found" in str(err)


class TestInvalidConfigValueError:
    """Tests for InvalidConfigValueError."""

    def test_is_configuration_error(self) -> None:
        err = InvalidConfigValueError(
            file="servers.json",
            key="sv1.timeout",
            expected="integer (1-300)",
            received='"abc"',
        )
        assert isinstance(err, ConfigurationError)

    def test_format_includes_expected_and_received(self) -> None:
        err = InvalidConfigValueError(
            file="servers.json",
            key="sv1.temperature",
            expected="float (0.0-2.0)",
            received='"hot"',
        )
        msg = str(err)
        assert "sv1.temperature" in msg
        assert "float (0.0-2.0)" in msg
        assert '"hot"' in msg


class TestMissingRequiredKeyError:
    """Tests for MissingRequiredKeyError."""

    def test_is_configuration_error(self) -> None:
        err = MissingRequiredKeyError(
            file="servers.json",
            key="active_server",
            expected="present",
            received="missing",
        )
        assert isinstance(err, ConfigurationError)

    def test_format_includes_key(self) -> None:
        err = MissingRequiredKeyError(
            file="tools.json",
            key="zabbix.tool",
            expected="present",
            received="missing",
        )
        msg = str(err)
        assert "zabbix.tool" in msg
        assert "present" in msg
        assert "missing" in msg


class TestFormatErrorBatch:
    """Tests for format_error_batch helper."""

    def test_single_error(self) -> None:
        errors: Sequence[ConfigurationError] = [
            MissingConfigFileError(
                file="servers.json",
                key="(file)",
                expected="existing file",
                received="not found",
            ),
        ]
        result = format_error_batch(errors)
        assert "servers.json" in result
        assert "not found" in result

    def test_multiple_errors_joined_with_separator(self) -> None:
        errors: Sequence[ConfigurationError] = [
            MissingConfigFileError(
                file="servers.json",
                key="(file)",
                expected="existing file",
                received="not found",
            ),
            InvalidConfigValueError(
                file="tools.json",
                key="zabbix.timeout",
                expected="int",
                received='"abc"',
            ),
        ]
        result = format_error_batch(errors)
        assert "servers.json" in result
        assert "tools.json" in result
        assert "\n\n" in result

    def test_empty_list(self) -> None:
        result = format_error_batch([])
        assert result == ""
