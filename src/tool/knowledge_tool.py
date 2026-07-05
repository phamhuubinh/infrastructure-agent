from __future__ import annotations

import json
from pathlib import Path


class KnowledgeTool:
    """
    Tool for reading the Stable Knowledge Store.

    This MVP implementation provides simple read access to
    knowledge_store.json.
    """

    def __init__(
        self,
        store: str = "knowledge_store.json",
    ) -> None:
        self.store = Path(store)

    def _load(self) -> dict[str, object]:
        with self.store.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    def get(
        self,
        key: str,
    ) -> object | None:
        data = self._load()
        return data.get(key)

    def keys(self) -> list[str]:
        data = self._load()
        return sorted(data.keys())
