#!/usr/bin/env python3

import json
from pathlib import Path


class KnowledgeTool:

    def __init__(self, store="knowledge_store.json"):
        self.store = Path(store)

    def _load(self):
        with self.store.open("r", encoding="utf-8") as f:
            return json.load(f)

    def get(self, key):
        data = self._load()
        return data.get(key)

    def keys(self):
        data = self._load()
        return sorted(data.keys())


if __name__ == "__main__":
    tool = KnowledgeTool()

    print("Keys:")
    for k in tool.keys():
        print("-", k)
