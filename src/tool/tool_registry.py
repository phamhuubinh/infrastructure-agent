from __future__ import annotations

from src.tool.tool import Tool


class ToolRegistry:
    """
    Registry for Tool instances.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        tool_id: str,
        tool: Tool,
    ) -> None:
        if tool_id in self._tools:
            raise ValueError(f"Tool '{tool_id}' is already registered.")

        self._tools[tool_id] = tool

    def get(
        self,
        tool_id: str,
    ) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: '{tool_id}'.") from exc
