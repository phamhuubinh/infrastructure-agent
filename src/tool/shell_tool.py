from __future__ import annotations

import subprocess

from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool


class ShellTool(Tool):
    """
    Tool for executing a single local shell command.
    """

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        command = arguments.get("command")

        if not isinstance(command, str):
            raise ValueError("Missing command.")

        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )

        if completed.returncode == 0:
            return ToolResult(
                success=True,
                data=completed.stdout,
            )

        return ToolResult(
            success=False,
            error=completed.stderr,
        )
