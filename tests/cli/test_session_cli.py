from __future__ import annotations

import argparse
import importlib
import io
import json
from datetime import datetime, timezone
from unittest import mock

from src.agent.canonical_factory import create_canonical_session_agent
from src.agent.contracts import AgentDecision, DecisionKind
from src.cli.main import (
    _list_saved_sessions,
    _print_runtime_event,
    _print_saved_sessions,
)
from src.observability.events import AgentEvent, EventStatus, get_event_store
from tests.fixtures.fake_agent_backend import ScriptedAgentBackend

cli_main = importlib.import_module("src.cli.main")


def _controller_final(answer: str) -> str:
    return json.dumps(
        AgentDecision(
            kind=DecisionKind.FINAL,
            goal="Answer the request.",
            answer=answer,
        ).to_wire()
    )


def _session(
    session_id: str,
    *,
    source: str,
    updated: str,
    title: str = "",
    preview: str = "",
) -> dict:
    return {
        "id": session_id,
        "source": source,
        "turns": 1,
        "updated": updated,
        "title": title,
        "preview": preview,
        "messages": [],
    }


def test_list_saved_sessions_merges_postgres_and_sqlite() -> None:
    sqlite_session = _session(
        "terminal-1",
        source="terminal",
        updated="2026-08-01T09:00:00",
        preview="terminal question",
    )
    web_session = _session(
        "web-1",
        source="api",
        updated="2026-08-02T10:00:00+00:00",
        title="Web investigation",
    )

    with (
        mock.patch.object(
            cli_main.SQLiteConversationStore,
            "list_sessions",
            return_value=[sqlite_session],
        ),
        mock.patch("src.backend.db._get_dsn", return_value="postgresql://orion"),
        mock.patch("src.backend.db.list_sessions_db", return_value=[web_session]),
    ):
        result = _list_saved_sessions()

    assert [item["id"] for item in result] == ["web-1", "terminal-1"]


def test_list_saved_sessions_uses_sqlite_without_postgres() -> None:
    sqlite_session = _session(
        "terminal-1",
        source="terminal",
        updated="2026-08-01T09:00:00",
    )

    with (
        mock.patch.object(
            cli_main.SQLiteConversationStore,
            "list_sessions",
            return_value=[sqlite_session],
        ),
        mock.patch("src.backend.db._get_dsn", return_value=None),
        mock.patch("src.backend.db.list_sessions_db") as list_postgres,
    ):
        result = _list_saved_sessions()

    assert result == [sqlite_session]
    list_postgres.assert_not_called()


def test_postgres_copy_wins_when_session_exists_in_both_stores() -> None:
    sqlite_session = _session(
        "shared",
        source="terminal",
        updated="2026-08-01T09:00:00",
    )
    postgres_session = _session(
        "shared",
        source="api",
        updated="2026-08-02T10:00:00+00:00",
        title="Authoritative Web title",
    )

    with (
        mock.patch.object(
            cli_main.SQLiteConversationStore,
            "list_sessions",
            return_value=[sqlite_session],
        ),
        mock.patch("src.backend.db._get_dsn", return_value="postgresql://orion"),
        mock.patch("src.backend.db.list_sessions_db", return_value=[postgres_session]),
    ):
        result = _list_saved_sessions()

    assert result == [postgres_session]


def test_print_saved_sessions_prefers_title(capsys) -> None:
    _print_saved_sessions(
        [
            _session(
                "web-1",
                source="api",
                updated="2026-08-02T10:00:00+00:00",
                title="Saved title",
                preview="first question",
            )
        ]
    )

    output = capsys.readouterr().out
    assert "Title / Preview" in output
    assert "Saved title" in output
    assert "first question" not in output


def test_cli_chat_prints_one_configured_v2_final_without_controller_wire(
    tmp_path, monkeypatch, capsys
) -> None:
    agent = create_canonical_session_agent(
        target_store_path=str(tmp_path / "targets.json"),
        model_backend=ScriptedAgentBackend(
            _controller_final("CLI final answer.")
        ),
    )
    args = argparse.Namespace(
        resume="cli-v2",
        target_file=str(tmp_path / "targets.json"),
        server=None,
        model=None,
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("hello from CLI\n"))

    with (
        mock.patch.object(cli_main, "SQLiteConversationStore"),
        mock.patch.object(cli_main, "create_canonical_session_agent", return_value=agent),
    ):
        cli_main._run_agent(args)

    output = capsys.readouterr().out
    assert output.count("CLI final answer.") == 1
    assert '"k":"final"' not in output
    assert "controller_prompt_metadata" not in output


def test_cli_status_and_verbose_project_safe_runtime_events(
    tmp_path, monkeypatch, capsys
) -> None:
    store = get_event_store()
    store.clear()
    agent = create_canonical_session_agent(
        target_store_path=str(tmp_path / "targets.json"),
        model_backend=ScriptedAgentBackend(_controller_final("CLI final answer.")),
    )
    args = argparse.Namespace(
        resume="cli-status",
        target_file=str(tmp_path / "targets.json"),
        server=None,
        model=None,
        status=True,
        verbose=True,
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("hello from CLI\n"))

    with (
        mock.patch.object(cli_main, "SQLiteConversationStore"),
        mock.patch.object(cli_main, "create_canonical_session_agent", return_value=agent),
    ):
        cli_main._run_agent(args)

    output = capsys.readouterr().out
    assert "[status] event=model.decision status=succeeded decision_kind=final" in output
    assert "[status] event=model.final status=succeeded" in output
    assert "[trace] terminal=final model_calls=1" in output
    assert "hello from CLI" not in output


def test_cli_verbose_projects_safe_provider_generation_diagnostics(capsys) -> None:
    event = AgentEvent(
        occurred_at=datetime.now(timezone.utc),
        request_id="req-1",
        component="model",
        event_type="model.failed",
        status=EventStatus.FAILED,
        error_code="invalid_output",
        metadata={
            "parse_diagnostics": {
                "provider_generation": {
                    "finish_reason": "length",
                    "completion_count": 1024,
                    "prompt_count": 312,
                    "stop_sequence_configured": False,
                    "content_bytes_before_sanitization": 1309,
                    "content_bytes_after_sanitization": 1309,
                    "provider_http_status": 200,
                }
            }
        },
    )

    _print_runtime_event(event, verbose=True)

    output = capsys.readouterr().out
    assert "finish_reason=length" in output
    assert "completion_count=1024" in output
    assert "prompt_count=312" in output
    assert "requested_output_limit" not in output
    assert "requested_completion_limit" not in output
    assert "stop_configured=False" in output
    assert "sanitize_before=1309" in output
    assert "sanitize_after=1309" in output
    assert "http_status=200" in output
