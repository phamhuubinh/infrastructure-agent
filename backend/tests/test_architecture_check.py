from __future__ import annotations

import importlib.util
from pathlib import Path


def _checker():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "scripts" / "architecture_check.py"
    spec = importlib.util.spec_from_file_location("architecture_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime(root: Path) -> None:
    root.mkdir()
    (root / "runtime.py").write_text("class ChatRuntime:\n    pass\n", encoding="utf-8")


def test_architecture_check_rejects_executable_forbidden_patterns(tmp_path: Path) -> None:
    checker = _checker()
    root, ui = tmp_path / "orion", tmp_path / "ui"
    _runtime(root)
    (root / "api").mkdir()
    (root / "api" / "bad.py").write_text(
        "import openai\n"
        "from legacy.runtime import Legacy\n"
        "enabled_tools = []\n"
        "handler_key = 'internal'\n"
        "semantic_router = object()\n"
        "keyword_router = object()\n"
        "capability_search = object()\n"
        "dynamic_tool_exposure = object()\n"
        "dynamic_capability_exposure = object()\n"
        "capability_discovery = object()\n"
        "ACTION = 'ACTION'\n"
        "ACTION_DETAIL = 'ACTION_DETAIL'\n"
        "OBSERVATION = 'OBSERVATION'\n"
        "FEEDBACK = 'FEEDBACK'\n"
        "ToolDefinition(name='shell.execute')\n"
        "ToolDefinition(name='grafana.request')\n"
        "ToolDefinition(name='zabbix.jsonrpc')\n"
        "class ChatRuntime: pass\n"
        "class ProjectRuntime: pass\n",
        encoding="utf-8",
    )
    ui.mkdir()
    (ui / "bad.ts").write_text(
        "const enabled_tools = semantic_router + keyword_router + capability_search + "
        "dynamic_tool_exposure + dynamic_capability_exposure + handler_key;",
        encoding="utf-8",
    )

    violations = "\n".join(checker.check(root, ui))
    for expected in (
        "semantic/capability routing",
        "legacy FSM",
        "generic model-facing tool",
        "public boundary exposes",
        "legacy import",
        "provider-native import",
        "expected one ChatRuntime",
        "ProjectRuntime",
        "forbidden UI",
    ):
        assert expected in violations


def test_architecture_check_ignores_docs_and_test_prose(tmp_path: Path) -> None:
    checker = _checker()
    root, ui = tmp_path / "orion", tmp_path / "ui"
    _runtime(root)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text(
        "enabled_tools semantic_router shell.execute", encoding="utf-8"
    )
    (root / "test_notes.py").write_text(
        "TEXT = 'enabled_tools semantic_router shell.execute'\n", encoding="utf-8"
    )
    (ui / "__tests__").mkdir(parents=True)
    (ui / "__tests__" / "notes.test.ts").write_text(
        "const note = 'enabled_tools';", encoding="utf-8"
    )
    assert checker.check(root, ui) == []
