from __future__ import annotations

import inspect

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.linux_tool import LinuxTool
from src.tool.target_registry import TargetRegistry
from src.tool.tool import Tool


def _tool_capabilities(tool: Tool) -> list[str]:
    mod = inspect.getmodule(type(tool))
    if mod is not None and hasattr(mod, "_CAPABILITIES"):
        return list(mod._CAPABILITIES.keys())
    return []


class KnowledgeTool(Tool):
    """
    Tool tổng (dispatcher). Đây là Tool duy nhất Model biết tới.

    KnowledgeTool nhận request {"source", "resource"} từ Agent, xác định
    Tool con phụ trách "source", chuyển tiếp "resource" cho Tool con dưới
    dạng "action", và trả nguyên ToolResult mà Tool con sinh ra.

    KnowledgeTool không truy cập Environment, không chạy shell command,
    không biết Linux command hay bất kỳ command nào của Tool con -- nó
    chỉ biết Tool con nào phụ trách source nào.

    Để thêm domain mới (Docker, VMware...): tạo Tool con mới rồi thêm
    một entry vào _child_tools. Không cần sửa gì khác trong KnowledgeTool.
    """

    def __init__(
        self,
        target_registry: TargetRegistry | None = None,
    ) -> None:
        if target_registry is None:
            target_registry = TargetRegistry()
            target_registry.add("localhost")
        self._registry = target_registry

    def get_capabilities(self) -> dict[str, list[str]]:
        caps: dict[str, list[str]] = {}
        for name in self._registry.target_names():
            tool = self._registry.get_tool(name)
            caps[name] = _tool_capabilities(tool)
        return caps

    def get_available_resources(self) -> dict[str, list[str]]:
        return self.get_capabilities()

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        source = arguments.get("source")
        resource = arguments.get("resource")

        if not isinstance(source, str):
            raise ValueError("Missing source.")

        if not isinstance(resource, str):
            raise ValueError("Missing resource.")

        try:
            child_tool = self._registry.get_tool(source)
        except KeyError:
            available = ", ".join(self._registry.target_names())

            return ToolResult(
                success=False,
                error=f"Unknown source: '{source}'. Available sources: {available}.",
            )

        child_args: dict[str, object] = {"action": resource}
        extra = {k: v for k, v in arguments.items() if k not in ("source", "resource")}
        child_args.update(extra)

        return child_tool.execute(child_args)

    def get_child_tool(self, source: str) -> Tool:
        return self._registry.get_tool(source)

    def get_capability_metadata(self) -> dict[str, list[dict[str, object]]]:
        result: dict[str, list[dict[str, object]]] = {}
        for name in self._registry.target_names():
            tool = self._registry.get_tool(name)
            mod = inspect.getmodule(type(tool))
            if mod is None or not hasattr(mod, "_CAPABILITIES"):
                continue
            raw = getattr(mod, "_CAPABILITIES")
            entries: list[dict[str, object]] = []
            for cap_name, value in raw.items():
                if isinstance(value, Capability):
                    entries.append({
                        "name": cap_name,
                        "category": value.category,
                        "intents": list(value.intents),
                        "related": list(value.related),
                        "covers": list(value.covers),
                    })
                else:
                    entries.append({"name": cap_name})
            if entries:
                result[name] = entries
        return result
