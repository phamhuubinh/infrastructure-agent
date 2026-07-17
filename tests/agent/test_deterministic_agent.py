from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from src.agent.deterministic_agent import DeterministicAgent
from src.agent.runtime_factory import (
    _SUPPORTED_TOOL_TYPES,
    _load_tools_config,
    _warn,
    create_deterministic_agent,
)


def test_deterministic_agent_runs_pipeline() -> None:
    from src.pipeline.target_resolver import TargetResolver

    original_resolve = TargetResolver.resolve

    def patched_resolve(self, request):
        request.target = "localhost"

    TargetResolver.resolve = patched_resolve
    try:
        agent = create_deterministic_agent()
        result = agent.run("check the server health")
    finally:
        TargetResolver.resolve = original_resolve
    assert isinstance(result, str)
    assert len(result) > 50


def test_pipeline_only() -> None:
    from src.pipeline.target_resolver import TargetResolver

    original_resolve = TargetResolver.resolve

    def patched_resolve(self, request):
        request.target = "localhost"

    TargetResolver.resolve = patched_resolve
    try:
        agent = create_deterministic_agent()
        request = agent.execute_pipeline_only("check the server health")
        assert len(request.evidence) > 0
        assert request.intent is not None
    finally:
        TargetResolver.resolve = original_resolve


# ---------------------------------------------------------------------------
# tools.json loading
# ---------------------------------------------------------------------------


def test_no_tools_file_returns_empty() -> None:
    with mock.patch("pathlib.Path.exists", return_value=False):
        config = _load_tools_config()
        assert config == {}


def test_invalid_json_returns_empty() -> None:
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value="not json"):
            config = _load_tools_config()
            assert config == {}


def test_non_dict_json_returns_empty() -> None:
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value='"string"'):
            config = _load_tools_config()
            assert config == {}


def test_oserror_returns_empty() -> None:
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", side_effect=OSError("denied")):
            config = _load_tools_config()
            assert config == {}


def test_valid_config_loaded() -> None:
    data = {
        "zabbix": {
            "tool": "zabbix",
            "url": "http://z",
            "token": "t",
            "target": "zabbix",
        },
    }
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(data)):
            config = _load_tools_config()
            assert config == data


# ---------------------------------------------------------------------------
# Tool registration edge cases
# ---------------------------------------------------------------------------


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_tools_loaded_from_config(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "zabbix": {
            "tool": "zabbix",
            "url": "http://test-zabbix/zabbix",
            "token": "test-token",
            "target": "zabbix",
        },
        "grafana": {
            "tool": "grafana",
            "url": "http://test-grafana:3000",
            "token": "test-grafana-token",
            "target": "grafana",
        },
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_missing_tool_field_skips_entry(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "bad_entry": {"url": "http://test"},
    }
    # Should not crash — just skip
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_unknown_tool_type_skips_entry(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "vmware": {
            "tool": "vmware",
            "url": "http://v",
            "token": "t",
        },
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_missing_required_fields_skips_entry(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "zabbix": {
            "tool": "zabbix",
            # missing url and token
        },
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_duplicate_target_name_handled(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "zabbix1": {
            "tool": "zabbix",
            "url": "http://z1",
            "token": "t1",
            "target": "zabbix",
        },
        "zabbix2": {
            "tool": "zabbix",
            "url": "http://z2",
            "token": "t2",
            "target": "zabbix",  # same target name as zabbix1
        },
    }
    # Should not crash — second entry should warn about duplicate
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


@mock.patch("src.agent.runtime_factory._load_tools_config")
def test_non_dict_entry_skipped(mock_load: mock.Mock) -> None:
    mock_load.return_value = {
        "bad_entry": "not a dict",
    }
    agent = create_deterministic_agent()
    request = agent.execute_pipeline_only("check health")
    assert len(request.evidence) > 0


# ---------------------------------------------------------------------------
# Supported tool types
# ---------------------------------------------------------------------------


def test_supported_tool_types_defined() -> None:
    assert "zabbix" in _SUPPORTED_TOOL_TYPES
    assert "grafana" in _SUPPORTED_TOOL_TYPES
    assert "internet" in _SUPPORTED_TOOL_TYPES
    for tool_type, required in _SUPPORTED_TOOL_TYPES.items():
        if tool_type == "internet":
            assert required == ()
        else:
            assert "url" in required
            assert "token" in required


# ---------------------------------------------------------------------------
# Warning helper
# ---------------------------------------------------------------------------


def test_warn_output(capsys: pytest.CaptureFixture) -> None:
    """_warn() should print 'Warning:' prefix to stderr."""
    _warn("test warning")
    captured = capsys.readouterr()
    assert captured.err == "Warning: test warning\n"
    assert captured.out == ""


def test_warn_called_on_invalid_json() -> None:
    """Loading invalid JSON should trigger a warning."""
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value="not json"):
            with mock.patch("src.agent.runtime_factory._warn") as mock_warn:
                _load_tools_config()
                mock_warn.assert_called_once()
                assert "invalid JSON" in mock_warn.call_args[0][0]


def test_warn_called_on_non_dict_json() -> None:
    """Loading non-dict JSON should trigger a warning."""
    with mock.patch.object(Path, "exists", return_value=True):
        with mock.patch.object(Path, "read_text", return_value='"string"'):
            with mock.patch("src.agent.runtime_factory._warn") as mock_warn:
                _load_tools_config()
                mock_warn.assert_called_once()
                assert "JSON object" in mock_warn.call_args[0][0]


def test_warn_called_on_missing_tool_field() -> None:
    """Entry without tool field should trigger a warning."""
    from src.agent.runtime_factory import _register_single_tool
    from src.tool.target_registry import TargetRegistry

    registry = TargetRegistry()
    with mock.patch("src.agent.runtime_factory._warn") as mock_warn:
        _register_single_tool(registry, "bad_entry", {"url": "x"})
        mock_warn.assert_called_once()
        assert "missing" in mock_warn.call_args[0][0]


def test_warn_called_on_unknown_tool_type() -> None:
    """Unknown tool type should trigger a warning."""
    from src.agent.runtime_factory import _register_single_tool
    from src.tool.target_registry import TargetRegistry

    registry = TargetRegistry()
    with mock.patch("src.agent.runtime_factory._warn") as mock_warn:
        _register_single_tool(registry, "bad", {"tool": "nonexistent"})
        mock_warn.assert_called_once()
        assert "Unknown" in mock_warn.call_args[0][0]


def test_warn_called_on_missing_required_fields() -> None:
    """Missing required fields should trigger a warning."""
    from src.agent.runtime_factory import _register_single_tool
    from src.tool.target_registry import TargetRegistry

    registry = TargetRegistry()
    with mock.patch("src.agent.runtime_factory._warn") as mock_warn:
        _register_single_tool(registry, "bad", {"tool": "zabbix"})
        mock_warn.assert_called_once()
        assert "missing" in mock_warn.call_args[0][0]


def test_warn_called_on_duplicate_registration() -> None:
    """Duplicate tool name should trigger a warning."""
    from src.agent.runtime_factory import _register_single_tool
    from src.shared.execution.tool_result import ToolResult
    from src.tool.target_registry import TargetRegistry
    from src.tool.tool import Tool

    # Register first tool with target name "zabbix"
    registry = TargetRegistry()
    registry.register_tool(
        name="zabbix",
        tool=type(
            "FakeZabbix",
            (Tool,),
            {
                "execute": lambda self, args: ToolResult(success=True),
            },
        )(),
    )

    with mock.patch("src.agent.runtime_factory._warn") as mock_warn:
        _register_single_tool(
            registry,
            "zabbix2",
            {"tool": "zabbix", "url": "http://z", "token": "t", "target": "zabbix"},
        )
        mock_warn.assert_called_once()
        assert "Failed to register" in mock_warn.call_args[0][0]


import pytest  # noqa: E402, F811

# ---------------------------------------------------------------------------
# ConversationStore summarization integration
# ---------------------------------------------------------------------------


def test_agent_sets_summarize_fn_on_conversation_store() -> None:
    """Agent should call set_summarize_fn on the conversation store."""
    from src.agent.conversation_store import ConversationStore

    store = ConversationStore("test_summarize_fn_integration")
    assert store._summarize_fn is None

    agent = create_deterministic_agent(conversation_store=store)
    assert agent._conversation_store is store
    # The summarize function should be set via public API
    assert store._summarize_fn is not None


def test_set_summarize_fn_replaces_function() -> None:
    from src.agent.conversation_store import ConversationStore

    store = ConversationStore("test_set_fn")

    def my_fn(prompt: str) -> str:
        return "summarized"

    store.set_summarize_fn(my_fn)
    assert store._summarize_fn is my_fn

    result = store._summarize_fn("some prompt")
    assert result == "summarized"
