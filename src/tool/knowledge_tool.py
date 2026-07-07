from __future__ import annotations

from src.shared.execution.tool_result import ToolResult
from src.tool.linux_tool import LinuxTool
from src.tool.tool import Tool


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

    def __init__(self) -> None:
        self._child_tools: dict[str, Tool] = {
            "linux": LinuxTool(),
        }

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

        child_tool = self._child_tools.get(source)

        if child_tool is None:
            available = ", ".join(sorted(self._child_tools))

            return ToolResult(
                success=False,
                error=f"Unknown source: '{source}'. Available sources: {available}.",
            )

        return child_tool.execute({"action": resource})
