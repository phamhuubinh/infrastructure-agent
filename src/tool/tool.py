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

    def build_links(
        self,
        evidence_list: list,
        user_request: str,
    ) -> str:
        """Build tool-specific deep links from collected evidence.
        
        Optional hook for tools that can generate external URLs.
        Returns an empty string by default.
        """
        return ""
