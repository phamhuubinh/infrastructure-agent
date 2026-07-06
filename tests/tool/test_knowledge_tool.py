from __future__ import annotations

import json

import pytest

from src.tool.knowledge_tool import KnowledgeTool


def test_get_returns_resource(tmp_path) -> None:
    store_root = tmp_path / "stable_store"
    linux = store_root / "linux"

    linux.mkdir(parents=True)

    inventory = linux / "inventory.json"

    inventory.write_text(
        json.dumps(
            {
                "system_info": [
                    {
                        "hostname": "test-host",
                    }
                ],
                "os_version": [
                    {
                        "name": "Ubuntu",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    tool = KnowledgeTool(str(store_root))

    assert tool.get(
        source="linux",
        resource="system_info",
    ) == [
        {
            "hostname": "test-host",
        }
    ]


def test_get_returns_none_for_unknown_resource(tmp_path) -> None:
    store_root = tmp_path / "stable_store"
    linux = store_root / "linux"

    linux.mkdir(parents=True)

    inventory = linux / "inventory.json"

    inventory.write_text(
        json.dumps(
            {
                "system_info": [],
            }
        ),
        encoding="utf-8",
    )

    tool = KnowledgeTool(str(store_root))

    assert (
        tool.get(
            source="linux",
            resource="missing",
        )
        is None
    )


def test_keys_returns_sorted_resource_names(tmp_path) -> None:
    store_root = tmp_path / "stable_store"
    linux = store_root / "linux"

    linux.mkdir(parents=True)

    inventory = linux / "inventory.json"

    inventory.write_text(
        json.dumps(
            {
                "z": [],
                "a": [],
                "m": [],
            }
        ),
        encoding="utf-8",
    )

    tool = KnowledgeTool(str(store_root))

    assert tool.keys(
        source="linux",
    ) == [
        "a",
        "m",
        "z",
    ]


def test_execute_returns_data_for_known_resource(tmp_path) -> None:
    store_root = tmp_path / "stable_store"
    linux = store_root / "linux"

    linux.mkdir(parents=True)

    inventory = linux / "inventory.json"

    inventory.write_text(
        json.dumps(
            {
                "os_version": [{"name": "Ubuntu"}],
            }
        ),
        encoding="utf-8",
    )

    tool = KnowledgeTool(str(store_root))

    result = tool.execute(
        {
            "source": "linux",
            "resource": "os_version",
        }
    )

    assert result.success is True
    assert result.data == [{"name": "Ubuntu"}]
    assert result.error is None


def test_execute_reports_unknown_resource_with_available_list(tmp_path) -> None:
    store_root = tmp_path / "stable_store"
    linux = store_root / "linux"

    linux.mkdir(parents=True)

    inventory = linux / "inventory.json"

    inventory.write_text(
        json.dumps(
            {
                "os_version": [],
                "interface_addresses": [],
            }
        ),
        encoding="utf-8",
    )

    tool = KnowledgeTool(str(store_root))

    result = tool.execute(
        {
            "source": "linux",
            "resource": "ip",
        }
    )

    assert result.success is False
    assert result.data is None
    assert "Unknown resource: 'ip'" in result.error
    assert "interface_addresses" in result.error
    assert "os_version" in result.error


def test_execute_reports_unknown_source(tmp_path) -> None:
    store_root = tmp_path / "stable_store"

    tool = KnowledgeTool(str(store_root))

    result = tool.execute(
        {
            "source": "windows",
            "resource": "os_version",
        }
    )

    assert result.success is False
    assert result.error == "Unknown source: 'windows'."


def test_execute_raises_on_missing_arguments(tmp_path) -> None:
    store_root = tmp_path / "stable_store"

    tool = KnowledgeTool(str(store_root))

    with pytest.raises(ValueError):
        tool.execute({"source": "linux"})

    with pytest.raises(ValueError):
        tool.execute({"resource": "os_version"})
