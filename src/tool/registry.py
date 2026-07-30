from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
import logging
from pathlib import Path

from src.tool.tool import Tool

logger = logging.getLogger(__name__)


def _tool_type_key(tool_cls: type[Tool]) -> str:
    """Derive the tool type key from the class name.

    GrafanaTool -> 'grafana'
    InternetTool -> 'internet'
    ZabbixTool -> 'zabbix'
    KnowledgeBaseTool -> 'knowledge_base'
    LinuxTool -> 'linux'
    """
    name = tool_cls.__name__
    # Remove 'Tool' suffix
    base = re.sub(r"Tool$", "", name)
    # Convert CamelCase to snake_case
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", base).lower()
    return snake


def _required_fields(tool_cls: type[Tool]) -> list[str]:
    """Inspect constructor to find required (no default) arguments.

    Returns parameter names excluding 'self'.
    If the class does not define its own ``__init__``, returns empty list.
    """
    # Skip classes that inherit the default object.__init__
    if "__init__" not in tool_cls.__dict__:
        return []
    try:
        sig = inspect.signature(tool_cls.__init__)
    except (ValueError, TypeError):
        return []
    return [
        name
        for name, param in sig.parameters.items()
        if name != "self" and param.default is inspect.Parameter.empty
    ]


class ToolRegistry:
    """Auto-discovers Tool subclasses with a _CAPABILITIES module attribute.

    Scans the ``src/tool/`` directory tree for Python modules that define
    a ``_CAPABILITIES`` dict and contain a :class:`Tool` subclass.
    """

    _tool_dir: Path

    def __init__(self, tool_dir: Path | None = None) -> None:
        if tool_dir is None:
            tool_dir = Path(__file__).resolve().parent
        self._tool_dir = tool_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover(self) -> list[tuple[type[Tool], dict]]:
        """Scan ``src/tool/`` for Tool subclasses with ``_CAPABILITIES``.

        Returns:
            List of ``(ToolClass, capabilities_dict)`` tuples.
        """
        result: list[tuple[type[Tool], dict]] = []
        seen: set[str] = set()

        for module_info in pkgutil.walk_packages(
            path=[str(self._tool_dir)],
            prefix="src.tool.",
            onerror=lambda _: None,
        ):
            if module_info.name in seen:
                continue
            seen.add(module_info.name)

            mod = self._safe_import(module_info.name)
            if mod is None:
                continue

            caps = getattr(mod, "_CAPABILITIES", None)
            if not isinstance(caps, dict):
                continue

            tool_cls = self._find_tool_subclass(mod)
            if tool_cls is None:
                continue

            result.append((tool_cls, caps))

        return result

    def discover_classes(self) -> dict[str, type[Tool]]:
        """Return ``{tool_type_key: ToolClass}`` for all discovered tools."""
        mapping: dict[str, type[Tool]] = {}
        for tool_cls, _caps in self.discover():
            key = _tool_type_key(tool_cls)
            mapping[key] = tool_cls
        return mapping

    def discover_required_fields(self) -> dict[str, tuple[str, ...]]:
        """Return ``{tool_type_key: (required_field, ...)}`` for all discovered tools."""
        mapping: dict[str, tuple[str, ...]] = {}
        for tool_cls, _caps in self.discover():
            key = _tool_type_key(tool_cls)
            mapping[key] = tuple(_required_fields(tool_cls))
        return mapping

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_import(module_name: str):
        """Import a module by name, returning None on failure."""
        try:
            return importlib.import_module(module_name)
        except Exception:
            logging.error(f"Failed to import module '{module_name}'", exc_info=True)
            return None

    @staticmethod
    def _find_tool_subclass(module) -> type[Tool] | None:
        """Find a Tool subclass defined in the given module.

        Excludes KnowledgeTool itself since it dispatches to child tools.
        """
        from src.tool.knowledge_tool import KnowledgeTool

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, Tool):
                continue
            if obj is Tool:
                continue
            if obj is KnowledgeTool:
                continue
            # Only pick up classes defined in this module (not imported).
            if obj.__module__ != module.__name__:
                continue
            return obj
        return None
