from __future__ import annotations

import importlib
from unittest import mock

from src.cli.main import _list_saved_sessions, _print_saved_sessions

cli_main = importlib.import_module("src.cli.main")


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
        mock.patch(
            "src.backend.db.list_sessions_db", return_value=[postgres_session]
        ),
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
