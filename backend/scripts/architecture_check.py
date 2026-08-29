"""AST/source checks for executable forbidden architecture regressions only."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

DEFAULT_ROOT = Path(__file__).parents[1] / "src" / "orion"
DEFAULT_UI_ROOT = Path(__file__).parents[2] / "ui" / "src"
PUBLIC_BOUNDARIES = ("api", "chat", "models")
ROUTER_IDENTIFIERS = {
    "semantic_router",
    "keyword_router",
    "capability_search",
    "capability_discovery",
}
LEGACY_STATES = {"ACTION", "ACTION_DETAIL", "OBSERVATION", "FEEDBACK"}
GENERIC_TOOL_NAMES = {
    "shell",
    "shell.execute",
    "shell.run",
    "linux.shell",
    "linux.exec",
    "grafana.request",
    "grafana.api_request",
    "grafana.api",
    "zabbix.jsonrpc",
    "zabbix.rpc",
    "zabbix.request",
}
UI_FORBIDDEN = re.compile(
    r"\b(enabled_tools|semantic_router|keyword_router|capability_search|"
    r"handler_key)\b"
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names(tree: ast.AST) -> set[str]:
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names.update(node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute))
    return names


def _strings(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _tool_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "ToolDefinition":
            continue
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, str):
                    names.add(keyword.value.value)
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def _imports(tree: ast.AST) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _is_public_boundary(root: Path, path: Path) -> bool:
    return any(part in PUBLIC_BOUNDARIES for part in path.relative_to(root).parts)


def check(root: Path, ui_root: Path | None = None) -> list[str]:
    files = tuple(root.rglob("*.py"))
    violations: list[str] = []
    chat_runtimes = 0
    project_runtimes = 0
    for path in files:
        tree = _tree(path)
        names, strings = _names(tree), _strings(tree)
        chat_runtimes += sum(
            isinstance(node, ast.ClassDef) and node.name == "ChatRuntime" for node in ast.walk(tree)
        )
        project_runtimes += sum(
            isinstance(node, ast.ClassDef) and node.name == "ProjectRuntime"
            for node in ast.walk(tree)
        )
        if names & ROUTER_IDENTIFIERS:
            violations.append(f"{path}: semantic/capability routing identifier present")
        if strings & LEGACY_STATES:
            violations.append(f"{path}: legacy FSM state present")
        if _tool_names(tree) & GENERIC_TOOL_NAMES:
            violations.append(f"{path}: generic model-facing tool present")
        if _is_public_boundary(root, path) and names & {"enabled_tools", "handler_key"}:
            violations.append(f"{path}: public boundary exposes internal tool routing metadata")
        imported = _imports(tree)
        if any(name.startswith(("agent", "legacy")) for name in imported):
            violations.append(f"{path}: legacy import present")
        if any(
            name.startswith(("openai", "anthropic", "google.generativeai")) for name in imported
        ):
            if "models/providers" not in str(path):
                violations.append(f"{path}: provider-native import outside provider adapter")
    if chat_runtimes != 1:
        violations.append(f"expected one ChatRuntime, found {chat_runtimes}")
    if project_runtimes:
        violations.append(f"expected no ProjectRuntime, found {project_runtimes}")
    if ui_root is not None and ui_root.exists():
        for path in ui_root.rglob("*.ts*"):
            if "__tests__" in path.parts:
                continue
            if UI_FORBIDDEN.search(path.read_text(encoding="utf-8")):
                violations.append(f"{path}: forbidden UI exposure identifier present")
    return violations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--ui-root", type=Path, default=DEFAULT_UI_ROOT)
    arguments = parser.parse_args()
    violations = check(arguments.root, arguments.ui_root)
    if violations:
        raise SystemExit("\n".join(violations))


if __name__ == "__main__":
    main()
