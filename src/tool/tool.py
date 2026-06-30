from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.execution.tool_result import ToolResult


class Tool(ABC):
    """
    Abstract base class for all executable tools.
    """

    @abstractmethod
    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        """
        Execute one atomic operation.

        Implementations shall return exactly one ToolResult.
        """
        raise NotImplementedError
