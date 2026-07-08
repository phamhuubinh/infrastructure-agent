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

    def get_capabilities(self) -> dict[str, list[str]]:
        """
        Get all available capabilities from child tools.
        This method provides capability metadata for bootstrap generation.
        """
        capabilities = {}
        for source, tool in self._child_tools.items():
            # For LinuxTool, we extract the capability names from its _CAPABILITIES dictionary
            if hasattr(tool, "_CAPABILITIES"):
                capabilities[source] = list(tool._CAPABILITIES.keys())
            elif source == "linux":
                # Special handling for LinuxTool - get capabilities from the module directly
                import src.tool.linux_tool as linux_tool_module

                if hasattr(linux_tool_module, "_CAPABILITIES"):
                    capabilities[source] = list(linux_tool_module._CAPABILITIES.keys())
                else:
                    capabilities[source] = []
            else:
                # Fallback for other tools that might not have this attribute
                capabilities[source] = []
        return capabilities

    def get_available_resources(self) -> dict[str, list[str]]:
        """
        Get all available resources from child tools.
        This method provides resource names that can be requested.
        """
        resources = {}
        for source, tool in self._child_tools.items():
            if hasattr(tool, "_CAPABILITIES"):
                # For LinuxTool, the resource names are the values in _CAPABILITIES
                if hasattr(tool, "_CAPABILITIES") and isinstance(tool._CAPABILITIES, dict):
                    # Extract resource names from the capability definitions
                    resource_list = []
                    for capability_def in tool._CAPABILITIES.values():
                        if isinstance(capability_def, dict) and "resource" in capability_def:
                            resource_list.append(capability_def["resource"])
                        elif isinstance(capability_def, str):
                            # If capability_def is just a string, it might be the resource name
                            resource_list.append(capability_def)
                    resources[source] = resource_list
                else:
                    resources[source] = []
            elif source == "linux":
                # Special handling for LinuxTool - get resources from the module directly
                import src.tool.linux_tool as linux_tool_module

                if hasattr(linux_tool_module, "_CAPABILITIES") and isinstance(linux_tool_module._CAPABILITIES, dict):
                    resource_list = []
                    for capability_def in linux_tool_module._CAPABILITIES.values():
                        if isinstance(capability_def, dict) and "resource" in capability_def:
                            resource_list.append(capability_def["resource"])
                        elif isinstance(capability_def, str):
                            resource_list.append(capability_def)
                    resources[source] = resource_list
                else:
                    resources[source] = []
            else:
                resources[source] = []
        return resources

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
