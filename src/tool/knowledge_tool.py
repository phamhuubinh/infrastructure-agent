from __future__ import annotations

import json
from pathlib import Path


class KnowledgeTool:
    """
    Tool for reading data from the Stable Store.

    The Stable Store contains long-lived information collected by
    Discovery Collectors.
    """

    def __init__(
        self,
        store_root: str = "stable_store",
    ) -> None:
        self.store_root = Path(store_root)

    def _load(
        self,
        source: str,
    ) -> dict[str, object]:
        inventory = self.store_root / source / "inventory.json"

        with inventory.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    def get(
        self,
        source: str,
        resource: str,
    ) -> object | None:
        data = self._load(source)
        return data.get(resource)

    def keys(
        self,
        source: str,
    ) -> list[str]:
        data = self._load(source)
        return sorted(data.keys())
