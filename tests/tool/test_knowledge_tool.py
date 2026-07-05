from __future__ import annotations

import json

from src.tool.knowledge_tool import KnowledgeTool


def test_get_returns_resource(tmp_path) -> None:
    store = tmp_path / "knowledge_store.json"

    store.write_text(
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

    tool = KnowledgeTool(str(store))

    assert tool.get("system_info") == [
        {
            "hostname": "test-host",
        }
    ]


def test_get_returns_none_for_unknown_resource(tmp_path) -> None:
    store = tmp_path / "knowledge_store.json"

    store.write_text(
        json.dumps(
            {
                "system_info": [],
            }
        ),
        encoding="utf-8",
    )

    tool = KnowledgeTool(str(store))

    assert tool.get("missing") is None


def test_keys_returns_sorted_resource_names(tmp_path) -> None:
    store = tmp_path / "knowledge_store.json"

    store.write_text(
        json.dumps(
            {
                "z": [],
                "a": [],
                "m": [],
            }
        ),
        encoding="utf-8",
    )

    tool = KnowledgeTool(str(store))

    assert tool.keys() == [
        "a",
        "m",
        "z",
    ]
