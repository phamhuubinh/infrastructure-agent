from __future__ import annotations

import json
import sys

from src.discovery.linux import transformer
from src.discovery.linux.transformer import (
    build_knowledge_store,
    build_table,
    clean_object_full,
    is_empty,
    select_fields,
)


def test_is_empty_detects_empty_values() -> None:
    assert is_empty("") is True
    assert is_empty([]) is True
    assert is_empty({}) is True
    assert is_empty(None) is True


def test_is_empty_detects_non_empty_values() -> None:
    assert is_empty("value") is False
    assert is_empty(0) is False


def test_select_fields_keeps_only_declared_fields() -> None:
    result = select_fields(
        {
            "hostname": "server01",
            "cpu_brand": "Intel",
            "internal_id": "abc123",
        },
        ["hostname", "cpu_brand"],
    )

    assert result == {
        "hostname": "server01",
        "cpu_brand": "Intel",
    }


def test_select_fields_drops_empty_values() -> None:
    result = select_fields(
        {
            "hostname": "server01",
            "cpu_brand": "",
        },
        ["hostname", "cpu_brand"],
    )

    assert result == {"hostname": "server01"}


def test_select_fields_returns_none_when_result_empty() -> None:
    result = select_fields(
        {"hostname": ""},
        ["hostname"],
    )

    assert result is None


def test_clean_object_full_removes_empty_fields() -> None:
    result = clean_object_full(
        {
            "name": "eth0",
            "mtu": "",
        }
    )

    assert result == {"name": "eth0"}


def test_clean_object_full_returns_none_when_empty() -> None:
    assert clean_object_full({"mtu": ""}) is None


def test_clean_object_full_passes_through_non_dict() -> None:
    assert clean_object_full("value") == "value"
    assert clean_object_full("") is None


def test_build_table_applies_field_selection() -> None:
    result = build_table(
        "system_info",
        [
            {
                "hostname": "server01",
                "cpu_brand": "Intel",
                "internal_id": "abc123",
            }
        ],
    )

    assert result == [
        {
            "hostname": "server01",
            "cpu_brand": "Intel",
        }
    ]


def test_build_table_falls_back_to_full_object_for_undeclared_table() -> None:
    result = build_table(
        "some_new_table",
        [
            {
                "a": "1",
                "b": "",
            }
        ],
    )

    assert result == [{"a": "1"}]


def test_build_table_handles_dict_value() -> None:
    result = build_table(
        "system_info",
        {
            "hostname": "server01",
            "internal_id": "abc123",
        },
    )

    assert result == {"hostname": "server01"}


def test_build_table_drops_empty_items_from_list() -> None:
    result = build_table(
        "system_info",
        [
            {"internal_id": "abc123"},
        ],
    )

    assert result == []


def test_build_knowledge_store_excludes_excluded_tables() -> None:
    data = {
        "system_info": [{"hostname": "server01"}],
        "memory_info": [{"total": "1024"}],
    }

    result = build_knowledge_store(data)

    assert "memory_info" not in result
    assert result["system_info"] == [{"hostname": "server01"}]


def test_main_writes_inventory_file(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "osquery.json"
    output_path = tmp_path / "inventory.json"

    input_path.write_text(
        json.dumps(
            {
                "system_info": [
                    {
                        "hostname": "server01",
                        "internal_id": "abc123",
                    }
                ],
                "memory_info": [{"total": "1024"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transformer.py",
            str(input_path),
            "-o",
            str(output_path),
        ],
    )

    transformer.main()

    inventory = json.loads(output_path.read_text(encoding="utf-8"))

    assert inventory == {
        "system_info": [
            {
                "hostname": "server01",
            }
        ]
    }


def test_main_exits_when_input_file_missing(tmp_path, monkeypatch) -> None:
    missing_input = tmp_path / "missing.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transformer.py",
            str(missing_input),
        ],
    )

    try:
        transformer.main()
        raised = False
    except SystemExit:
        raised = True

    assert raised is True
