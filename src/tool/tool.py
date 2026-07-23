from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from src.shared.capability import Capability
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

    @staticmethod
    def _resolve_capability(
        capabilities: dict[str, Capability],
        action: str,
        tool_name: str,
    ) -> Capability | ToolResult:
        """Look up a capability by name; return ToolResult on failure."""
        cap = capabilities.get(action)
        if cap is None:
            available = ", ".join(sorted(capabilities))
            return ToolResult(
                success=False,
                error=f"{tool_name}: Unknown action '{action}'. Available: {available}.",
            )
        return cap

    @staticmethod
    def _filter_arguments(
        handler: Callable[..., Any],
        arguments: dict[str, object],
    ) -> dict[str, object]:
        """Return only the arguments accepted by handler's signature."""
        params = inspect.signature(handler).parameters
        return {k: v for k, v in arguments.items() if k in params}

    @classmethod
    def _dispatch(
        cls,
        capabilities: dict[str, Capability],
        arguments: dict[str, object],
        tool_name: str,
        *,
        provider: object = None,
    ) -> ToolResult:
        """Common capability dispatch logic.

        1. Validate 'action' key.
        2. Resolve capability.
        3. Filter arguments to match handler signature.
        4. Call handler(provider, **filtered) if provider is given,
           else handler(**filtered).
        """
        action = arguments.get("action")
        if not isinstance(action, str):
            return ToolResult(success=False, error="Missing action.")

        cap_or_err = cls._resolve_capability(capabilities, action, tool_name)
        if not isinstance(cap_or_err, Capability):
            return cap_or_err

        handler = cap_or_err.handler
        filtered = cls._filter_arguments(
            handler,
            {k: v for k, v in arguments.items() if k != "action"},
        )

        if provider is not None:
            return ToolResult(success=True, data=handler(provider, **filtered))
        return ToolResult(success=True, data=handler(**filtered))
