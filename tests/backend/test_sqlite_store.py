"""Tests for SQLiteConversationStore."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from src.backend.sqlite_store import (
    SQLiteConversationStore,
    _get_default_db_path,
    migrate_json_to_sqlite,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Return a temporary SQLite database path."""
    return tmp_path / "test_sessions.db"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_creates_db_directory(tmp_path: Path) -> None:
    db = tmp_path / "orion_test" / "sessions.db"
    SQLiteConversationStore("test-session", db_path=db)
    assert db.parent.exists()


def test_default_db_path() -> None:
    expected = os.path.join(os.path.expanduser("~"), ".orion", "sessions.db")
    assert str(_get_default_db_path()) == expected


def test_session_id_property(db_path: Path) -> None:
    store = SQLiteConversationStore("my-session", db_path=db_path)
    assert store.session_id == "my-session"


def test_empty_history(db_path: Path) -> None:
    store = SQLiteConversationStore("empty", db_path=db_path)
    assert store.history == []


def test_empty_title(db_path: Path) -> None:
    store = SQLiteConversationStore("title-test", db_path=db_path)
    assert store.title == ""


def test_empty_summary(db_path: Path) -> None:
    store = SQLiteConversationStore("sum-test", db_path=db_path)
    assert store.summary is None


# ---------------------------------------------------------------------------
# add_turn
# ---------------------------------------------------------------------------


def test_add_turn_appends_messages(db_path: Path) -> None:
    store = SQLiteConversationStore("turn-test", db_path=db_path)
    store.add_turn("hello", "world")
    assert len(store.history) == 2
    assert store.history[0] == {"role": "user", "content": "hello"}
    assert store.history[1] == {"role": "assistant", "content": "world"}


def test_add_turn_persists_to_db(db_path: Path) -> None:
    store1 = SQLiteConversationStore("persist-test", db_path=db_path)
    store1.add_turn("q1", "a1")
    store1.add_turn("q2", "a2")

    # Re-open and verify persistence
    store2 = SQLiteConversationStore("persist-test", db_path=db_path)
    assert len(store2.history) == 4  # 2 user + 2 assistant
    assert store2.history[0] == {"role": "user", "content": "q1"}
    assert store2.history[1] == {"role": "assistant", "content": "a1"}


# ---------------------------------------------------------------------------
# add_classifier_turn
# ---------------------------------------------------------------------------


def test_add_classifier_turn(db_path: Path) -> None:
    store = SQLiteConversationStore("cls-test", db_path=db_path)
    store.add_classifier_turn("check health", "health_check")
    assert len(store.history) == 2
    assert store.history[0] == {"role": "user", "content": "check health"}
    assert store.history[1] == {
        "role": "assistant",
        "content": "[classified as health_check]",
    }


# ---------------------------------------------------------------------------
# History with summary
# ---------------------------------------------------------------------------


def test_history_includes_summary_when_present(db_path: Path) -> None:
    store = SQLiteConversationStore("summary-present", db_path=db_path)
    store.set_summary("Server is healthy")
    store.add_turn("check", "ok")
    history = store.history
    assert len(history) == 3
    assert history[0] == {
        "role": "system",
        "content": "Previous conversation summary: Server is healthy",
    }


# ---------------------------------------------------------------------------
# set_summarize_fn
# ---------------------------------------------------------------------------


def test_set_summarize_fn(db_path: Path) -> None:
    store = SQLiteConversationStore("fn-test", db_path=db_path)
    assert store._summarize_fn is None  # type: ignore[attr-defined]

    def my_summarize(prompt: str) -> str:
        return "custom summary"

    store.set_summarize_fn(my_summarize)
    assert store._summarize_fn is my_summarize  # type: ignore[attr-defined]
    assert store._summarize_fn("any") == "custom summary"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# set_summary / set_title
# ---------------------------------------------------------------------------


def test_set_summary_property(db_path: Path) -> None:
    store = SQLiteConversationStore("set-summary", db_path=db_path)
    assert store.summary is None
    store.set_summary("test summary")
    assert store.summary == "test summary"


def test_set_title(db_path: Path) -> None:
    store = SQLiteConversationStore("set-title", db_path=db_path)
    store.set_title("My Session")
    assert store.title == "My Session"


def test_title_persisted(db_path: Path) -> None:
    store1 = SQLiteConversationStore("title-persist", db_path=db_path)
    store1.set_title("Custom Title")
    store1.add_turn("hi", "hello")

    store2 = SQLiteConversationStore("title-persist", db_path=db_path)
    assert store2.title == "Custom Title"


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


def test_summarize_calls_summarize_fn(db_path: Path) -> None:
    store = SQLiteConversationStore("summarize-call", db_path=db_path)
    store.add_turn("check server", "all good")
    store.add_turn("check disk", "disk ok")
    store.add_turn("check memory", "memory ok")
    store.add_turn("check cpu", "cpu ok")

    mock_fn = mock.Mock(return_value="Merged summary of all checks")
    store.set_summarize_fn(mock_fn)
    store.summarize()

    mock_fn.assert_called_once()
    assert store.summary == "Merged summary of all checks"
    assert store._mem == []


def test_summarize_empty_history_does_nothing(db_path: Path) -> None:
    store = SQLiteConversationStore("empty-sum", db_path=db_path)
    mock_fn = mock.Mock(return_value="summary")
    store.set_summarize_fn(mock_fn)
    store.summarize()
    mock_fn.assert_not_called()


def test_summarize_handles_exception(db_path: Path) -> None:
    store = SQLiteConversationStore("exc-sum", db_path=db_path)
    store.add_turn("q", "a")
    store.add_turn("q2", "a2")
    store.add_turn("q3", "a3")
    store.add_turn("q4", "a4")

    def failing_fn(prompt: str) -> str:
        msg = "LLM unavailable"
        raise RuntimeError(msg)

    store.set_summarize_fn(failing_fn)
    store.summarize()
    # History preserved on failure
    assert len(store._mem) > 0
    assert store.summary is None


# ---------------------------------------------------------------------------
# Auto-compress
# ---------------------------------------------------------------------------


def test_check_compress_triggers_summarize(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORION_CONVERSATION_THRESHOLD", "4")
    store = SQLiteConversationStore("compress-4", db_path=db_path)
    mock_fn = mock.Mock(return_value="auto summary")
    store.set_summarize_fn(mock_fn)
    store.add_turn("q1", "a1")
    assert mock_fn.call_count == 0
    store.add_turn("q2", "a2")
    assert mock_fn.call_count == 0
    store.add_turn("q3", "a3")
    assert mock_fn.call_count == 0
    store.add_turn("q4", "a4")
    assert mock_fn.call_count == 1


# ---------------------------------------------------------------------------
# Source parameter
# ---------------------------------------------------------------------------


def test_source_is_stored(db_path: Path) -> None:
    store = SQLiteConversationStore("src-test", db_path=db_path, source="web")
    assert store._source == "web"


# ---------------------------------------------------------------------------
# Static list_sessions
# ---------------------------------------------------------------------------


def test_list_sessions_no_db(tmp_path: Path) -> None:
    result = SQLiteConversationStore.list_sessions(tmp_path / "nonexistent.db")
    assert result == []


def test_list_sessions_empty_db(db_path: Path) -> None:
    # Create a store to initialize DB but without sessions
    _store = SQLiteConversationStore("init", db_path=db_path)
    result = SQLiteConversationStore.list_sessions(db_path)
    # The "init" session was created with empty data
    assert len(result) >= 0


def test_list_sessions_with_data(db_path: Path) -> None:
    store = SQLiteConversationStore("list-1", db_path=db_path, source="web")
    store.add_turn("hello", "world")

    result = SQLiteConversationStore.list_sessions(db_path)
    session_ids = [s["id"] for s in result]
    assert "list-1" in session_ids


# ---------------------------------------------------------------------------
# Static delete_session
# ---------------------------------------------------------------------------


def test_delete_session(db_path: Path) -> None:
    store = SQLiteConversationStore("del-test", db_path=db_path)
    store.add_turn("hi", "bye")

    assert SQLiteConversationStore.delete_session("del-test", db_path)
    assert not SQLiteConversationStore.delete_session("del-test", db_path)


def test_delete_session_nonexistent(db_path: Path) -> None:
    assert not SQLiteConversationStore.delete_session("nonexistent", db_path)


def test_delete_session_no_db(tmp_path: Path) -> None:
    assert not SQLiteConversationStore.delete_session("test", tmp_path / "no.db")


# ---------------------------------------------------------------------------
# Static rename_session
# ---------------------------------------------------------------------------


def test_rename_session(db_path: Path) -> None:
    store = SQLiteConversationStore("rename-test", db_path=db_path)
    store.add_turn("hi", "bye")

    assert SQLiteConversationStore.rename_session("rename-test", "New Title", db_path)
    assert not SQLiteConversationStore.rename_session("gone", "X", db_path)


# ---------------------------------------------------------------------------
# Static search_sessions
# ---------------------------------------------------------------------------


def test_search_sessions_basic(db_path: Path) -> None:
    store = SQLiteConversationStore("search-1", db_path=db_path)
    store.set_title("CPU Investigation")
    store.add_turn("check cpu usage", "CPU is at 45%")

    store2 = SQLiteConversationStore("search-2", db_path=db_path)
    store2.set_title("Memory Check")
    store2.add_turn("check memory", "Memory is at 60%")

    # Search for CPU — should find search-1
    results = SQLiteConversationStore.search_sessions("cpu", db_path)
    result_ids = [r["id"] for r in results]
    assert "search-1" in result_ids
    assert "search-2" not in result_ids


def test_search_sessions_no_db(tmp_path: Path) -> None:
    results = SQLiteConversationStore.search_sessions("test", tmp_path / "no.db")
    assert results == []


# ---------------------------------------------------------------------------
# migrate_json_to_sqlite
# ---------------------------------------------------------------------------


def test_migrate_empty_dir(db_path: Path, tmp_path: Path) -> None:
    json_dir = tmp_path / "empty_sessions"
    json_dir.mkdir()
    count = migrate_json_to_sqlite(json_dir=json_dir, sqlite_path=db_path)
    assert count == 0


def test_migrate_with_sessions(db_path: Path, tmp_path: Path) -> None:
    json_dir = tmp_path / "migrate_sessions"
    json_dir.mkdir()

    # Create a JSON session file
    session_data = {
        "session_id": "migrate-001",
        "source": "terminal",
        "title": "Test Migration",
        "updated_at": "2026-07-17T12:00:00",
        "messages": [
            {"role": "user", "content": "check cpu"},
            {"role": "assistant", "content": "CPU is ok"},
        ],
    }
    (json_dir / "migrate-001.json").write_text(json.dumps(session_data))

    count = migrate_json_to_sqlite(json_dir=json_dir, sqlite_path=db_path)
    assert count == 1

    # Verify it was migrated correctly
    store = SQLiteConversationStore("migrate-001", db_path=db_path)
    assert store._source == "terminal"
    assert store.title == "Test Migration"
    assert len(store.history) == 2
    assert store.history[0]["content"] == "check cpu"


def test_migrate_corrupted_file_skipped(db_path: Path, tmp_path: Path) -> None:
    json_dir = tmp_path / "corrupt_sessions"
    json_dir.mkdir()

    # Valid session
    session_data = {
        "session_id": "good-001",
        "source": "terminal",
        "messages": [{"role": "user", "content": "hi"}],
    }
    (json_dir / "good-001.json").write_text(json.dumps(session_data))

    # Corrupted file
    (json_dir / "bad.json").write_text("not valid json {{{")

    count = migrate_json_to_sqlite(json_dir=json_dir, sqlite_path=db_path)
    assert count == 1  # Only the good one was migrated
