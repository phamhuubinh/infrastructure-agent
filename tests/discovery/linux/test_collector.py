from __future__ import annotations

import subprocess

import pytest

from src.discovery.linux.collector import (
    check_osquery_installed,
    clean_object,
    clean_table_value,
    collect_all,
    is_empty,
    query_table,
)


def test_is_empty_detects_empty_values() -> None:
    assert is_empty("") is True
    assert is_empty([]) is True
    assert is_empty({}) is True
    assert is_empty(None) is True


def test_is_empty_detects_non_empty_values() -> None:
    assert is_empty("value") is False
    assert is_empty([1]) is False
    assert is_empty({"a": 1}) is False
    assert is_empty(0) is False


def test_clean_object_removes_empty_fields() -> None:
    result = clean_object(
        {
            "name": "eth0",
            "mtu": "",
            "flags": [],
        }
    )

    assert result == {"name": "eth0"}


def test_clean_object_returns_none_when_all_fields_empty() -> None:
    result = clean_object(
        {
            "mtu": "",
            "flags": [],
        }
    )

    assert result is None


def test_clean_object_passes_through_non_dict() -> None:
    assert clean_object("value") == "value"
    assert clean_object("") is None


def test_clean_table_value_filters_list_of_objects() -> None:
    result = clean_table_value(
        [
            {"name": "eth0", "mtu": ""},
            {"name": "", "mtu": ""},
        ]
    )

    assert result == [{"name": "eth0"}]


def test_clean_table_value_handles_dict() -> None:
    assert clean_table_value({"a": 1, "b": ""}) == {"a": 1}
    assert clean_table_value({"a": ""}) == {}


def test_clean_table_value_passes_through_other_types() -> None:
    assert clean_table_value("value") == "value"


def test_query_table_returns_cleaned_data_on_success(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='[{"name": "eth0", "mtu": ""}]',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    table, data, error = query_table("interface_details")

    assert table == "interface_details"
    assert data == [{"name": "eth0"}]
    assert error is None


def test_query_table_returns_error_on_nonzero_exit(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="no such table",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    table, data, error = query_table("unknown_table")

    assert table == "unknown_table"
    assert data is None
    assert error == "no such table"


def test_query_table_returns_error_on_timeout(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(subprocess, "run", fake_run)

    table, data, error = query_table("slow_table")

    assert table == "slow_table"
    assert data is None
    assert error == "timeout"


def test_query_table_returns_error_on_invalid_json(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="not-json",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    table, data, error = query_table("broken_table")

    assert table == "broken_table"
    assert data is None
    assert error is not None


def test_collect_all_separates_success_and_errors(monkeypatch) -> None:
    def fake_query_table(table, timeout=15):
        if table == "good_table":
            return table, [{"name": "eth0"}], None
        return table, None, "boom"

    monkeypatch.setattr(
        "src.discovery.linux.collector.query_table",
        fake_query_table,
    )

    result, errors = collect_all(
        ["good_table", "bad_table"],
        workers=2,
    )

    assert result == {"good_table": [{"name": "eth0"}]}
    assert errors == {"bad_table": "boom"}


def test_check_osquery_installed_exits_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.discovery.linux.collector.shutil.which",
        lambda name: None,
    )

    with pytest.raises(SystemExit):
        check_osquery_installed()


def test_check_osquery_installed_passes_when_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.discovery.linux.collector.shutil.which",
        lambda name: "/usr/bin/osqueryi",
    )

    check_osquery_installed()
