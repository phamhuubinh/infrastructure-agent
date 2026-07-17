from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

from src.agent.conversation_store import ConversationStore, list_sessions

# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


def test_list_sessions_no_dir() -> None:
    assert list_sessions("/tmp/nonexistent_orion_sessions_xyz") == []


def test_list_sessions_empty_dir(tmp_path: Path) -> None:
    assert list_sessions(str(tmp_path)) == []


def test_list_sessions_with_valid_sessions(tmp_path: Path) -> None:
    session_data = {
        "session_id": "sess-001",
        "title": "Health Check",
        "source": "terminal",
        "updated_at": "2026-07-17T12:00:00",
        "messages": [{"role": "user", "content": "check health"}],
    }
    f = tmp_path / "sess-001.json"
    f.write_text(json.dumps(session_data))

    result = list_sessions(str(tmp_path))
    assert len(result) == 1
    assert result[0]["id"] == "sess-001"
    assert result[0]["title"] == "Health Check"
    assert result[0]["source"] == "terminal"
    assert result[0]["turns"] == 1
    assert result[0]["has_summary"] is False


def test_list_sessions_with_summary(tmp_path: Path) -> None:
    session_data = {
        "session_id": "sess-002",
        "title": "Disk Check",
        "source": "web",
        "updated_at": "2026-07-17T13:00:00",
        "messages": [
            {"role": "user", "content": "check disk"},
            {"role": "assistant", "content": "ok"},
        ],
        "summary": "Disk is healthy",
    }
    f = tmp_path / "sess-002.json"
    f.write_text(json.dumps(session_data))

    result = list_sessions(str(tmp_path))
    assert len(result) == 1
    assert result[0]["has_summary"] is True
    assert result[0]["turns"] == 1


def test_list_sessions_corrupted_file_skipped(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("not valid json")
    session_data = {
        "session_id": "sess-003",
        "messages": [{"role": "user", "content": "hi"}],
    }
    (tmp_path / "sess-003.json").write_text(json.dumps(session_data))

    result = list_sessions(str(tmp_path))
    assert len(result) == 1
    assert result[0]["id"] == "sess-003"


def test_list_sessions_preview_empty_when_no_messages(tmp_path: Path) -> None:
    session_data = {"session_id": "sess-004", "messages": []}
    (tmp_path / "sess-004.json").write_text(json.dumps(session_data))

    result = list_sessions(str(tmp_path))
    assert result[0]["preview"] == ""


def test_list_sessions_preview_truncated(tmp_path: Path) -> None:
    long_content = "x" * 200
    session_data = {
        "session_id": "sess-005",
        "messages": [{"role": "user", "content": long_content}],
    }
    (tmp_path / "sess-005.json").write_text(json.dumps(session_data))

    result = list_sessions(str(tmp_path))
    assert len(result[0]["preview"]) == 80
    assert result[0]["preview"] == long_content[:80]


def test_list_sessions_limits_to_50(tmp_path: Path) -> None:
    for i in range(60):
        data = {
            "session_id": f"sess-{i:03d}",
            "messages": [{"role": "user", "content": "hi"}],
        }
        (tmp_path / f"sess-{i:03d}.json").write_text(json.dumps(data))

    result = list_sessions(str(tmp_path))
    assert len(result) == 50


# ---------------------------------------------------------------------------
# ConversationStore - construction
# ---------------------------------------------------------------------------


def test_creates_store_dir(tmp_path: Path) -> None:
    store_dir = tmp_path / "sessions"
    ConversationStore("test-session", store_dir=str(store_dir))
    assert store_dir.exists()


def test_default_store_dir() -> None:
    expected = os.path.join(os.path.expanduser("~"), ".orion", "sessions")
    store = ConversationStore("test-session")
    assert str(store._store_dir) == expected


def test_session_id_property() -> None:
    store = ConversationStore("my-session", store_dir="/tmp")
    assert store.session_id == "my-session"


def test_store_path_property(tmp_path: Path) -> None:
    store = ConversationStore("abc", store_dir=str(tmp_path))
    assert store.store_path == tmp_path / "abc.json"


def test_empty_history(tmp_path: Path) -> None:
    store = ConversationStore("empty", store_dir=str(tmp_path))
    assert store.history == []


# ---------------------------------------------------------------------------
# ConversationStore - add_turn
# ---------------------------------------------------------------------------


def test_add_turn_appends_messages(tmp_path: Path) -> None:
    store = ConversationStore("turn-test", store_dir=str(tmp_path))
    store.add_turn("hello", "world")
    assert len(store.history) == 2
    assert store.history[0] == {"role": "user", "content": "hello"}
    assert store.history[1] == {"role": "assistant", "content": "world"}


def test_add_turn_persists_to_disk(tmp_path: Path) -> None:
    store = ConversationStore("persist-test", store_dir=str(tmp_path))
    store.add_turn("q1", "a1")
    data = json.loads((tmp_path / "persist-test.json").read_text())
    assert data["session_id"] == "persist-test"
    assert len(data["messages"]) == 2


def test_add_turn_updates_timestamp(tmp_path: Path) -> None:
    store = ConversationStore("ts-test", store_dir=str(tmp_path))
    store.add_turn("q", "a")
    data = json.loads((tmp_path / "ts-test.json").read_text())
    assert "updated_at" in data
    assert data["updated_at"] != ""


# ---------------------------------------------------------------------------
# ConversationStore - add_classifier_turn
# ---------------------------------------------------------------------------


def test_add_classifier_turn(tmp_path: Path) -> None:
    store = ConversationStore("cls-test", store_dir=str(tmp_path))
    store.add_classifier_turn("check health", "health_check")
    assert len(store.history) == 2
    assert store.history[0] == {"role": "user", "content": "check health"}
    assert store.history[1] == {
        "role": "assistant",
        "content": "[classified as health_check]",
    }


# ---------------------------------------------------------------------------
# ConversationStore - history with summary
# ---------------------------------------------------------------------------


def test_history_includes_summary_when_present(tmp_path: Path) -> None:
    store = ConversationStore("summary-present", store_dir=str(tmp_path))
    store.set_summary("Server is healthy")
    store.add_turn("check", "ok")
    history = store.history
    assert len(history) == 3
    assert history[0] == {
        "role": "system",
        "content": "Previous conversation summary: Server is healthy",
    }
    assert history[1:] == [
        {"role": "user", "content": "check"},
        {"role": "assistant", "content": "ok"},
    ]


# ---------------------------------------------------------------------------
# ConversationStore - set_summarize_fn
# ---------------------------------------------------------------------------


def test_set_summarize_fn(tmp_path: Path) -> None:
    store = ConversationStore("fn-test", store_dir=str(tmp_path))
    assert store._summarize_fn is None

    def my_summarize(prompt: str) -> str:
        return "custom summary"

    store.set_summarize_fn(my_summarize)
    assert store._summarize_fn is my_summarize
    assert store._summarize_fn("any") == "custom summary"


# ---------------------------------------------------------------------------
# ConversationStore - set_summary / summary property
# ---------------------------------------------------------------------------


def test_set_summary_property(tmp_path: Path) -> None:
    store = ConversationStore("set-summary", store_dir=str(tmp_path))
    assert store.summary is None
    store.set_summary("test summary")
    assert store.summary == "test summary"


# ---------------------------------------------------------------------------
# ConversationStore - summarize
# ---------------------------------------------------------------------------


def test_summarize_calls_summarize_fn(tmp_path: Path) -> None:
    store = ConversationStore("summarize-call", store_dir=str(tmp_path))
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


def test_summarize_empty_history_does_nothing(tmp_path: Path) -> None:
    store = ConversationStore("empty-sum", store_dir=str(tmp_path))
    mock_fn = mock.Mock(return_value="summary")
    store.set_summarize_fn(mock_fn)
    store.summarize()
    mock_fn.assert_not_called()


def test_summarize_handles_fn_returning_empty(tmp_path: Path) -> None:
    store = ConversationStore("empty-ret", store_dir=str(tmp_path))
    store.add_turn("q", "a")
    store.add_turn("q2", "a2")
    store.add_turn("q3", "a3")
    store.add_turn("q4", "a4")
    mock_fn = mock.Mock(return_value="")
    store.set_summarize_fn(mock_fn)
    store.summarize()
    # Summary not updated when fn returns empty
    assert store.summary is None


def test_summarize_handles_exception(tmp_path: Path) -> None:
    store = ConversationStore("exc-sum", store_dir=str(tmp_path))
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


def test_summarize_merges_with_existing_summary(tmp_path: Path) -> None:
    store = ConversationStore("merge-sum", store_dir=str(tmp_path))
    store.set_summary("Previous summary: all good")
    store.add_turn("new check", "new result")
    store.add_turn("another", "another result")
    store.add_turn("third", "third result")
    store.add_turn("fourth", "fourth result")

    def capturing_fn(prompt: str) -> str:
        assert "Previous summary: all good" in prompt
        return "Updated summary"

    store.set_summarize_fn(capturing_fn)
    store.summarize()
    assert store.summary == "Updated summary"
    assert store._mem == []


# ---------------------------------------------------------------------------
# ConversationStore - auto-compress after 4 turns
# ---------------------------------------------------------------------------


def test_check_compress_triggers_summarize_at_4_turns(tmp_path: Path) -> None:
    store = ConversationStore("compress-4", store_dir=str(tmp_path))
    mock_fn = mock.Mock(return_value="auto summary")
    store.set_summarize_fn(mock_fn)
    # Add 4 user turns -> triggers _check_compress
    store.add_turn("q1", "a1")
    assert mock_fn.call_count == 0  # only 1 user turn
    store.add_turn("q2", "a2")
    assert mock_fn.call_count == 0  # 2
    store.add_turn("q3", "a3")
    assert mock_fn.call_count == 0  # 3
    store.add_turn("q4", "a4")
    assert mock_fn.call_count == 1  # 4 -> triggers


# ---------------------------------------------------------------------------
# ConversationStore - persistence (load / save)
# ---------------------------------------------------------------------------


def test_loads_existing_session(tmp_path: Path) -> None:
    data = {
        "session_id": "existing",
        "source": "terminal",
        "messages": [{"role": "user", "content": "hello"}],
        "summary": "greeting",
    }
    (tmp_path / "existing.json").write_text(json.dumps(data))

    store = ConversationStore("existing", store_dir=str(tmp_path))
    assert store._mem == [{"role": "user", "content": "hello"}]
    assert store._summary == "greeting"


def test_load_corrupted_session_starts_fresh(tmp_path: Path) -> None:
    (tmp_path / "corrupt.json").write_text("{{{bad")
    store = ConversationStore("corrupt", store_dir=str(tmp_path))
    assert store._mem == []
    assert store._summary is None


def test_save_creates_file(tmp_path: Path) -> None:
    store = ConversationStore("save-test", store_dir=str(tmp_path))
    store.add_turn("q", "a")
    assert (tmp_path / "save-test.json").exists()
    data = json.loads((tmp_path / "save-test.json").read_text())
    assert data["session_id"] == "save-test"
    assert data["source"] == "terminal"
    assert "updated_at" in data


def test_save_oserror_does_not_crash(tmp_path: Path) -> None:
    store = ConversationStore("save-err", store_dir=str(tmp_path), source="terminal")
    store._dirty = True
    with mock.patch.object(Path, "write_text", side_effect=OSError("disk full")):
        store._save()  # should not raise


# ---------------------------------------------------------------------------
# ConversationStore - source parameter
# ---------------------------------------------------------------------------


def test_source_in_saved_file(tmp_path: Path) -> None:
    store = ConversationStore("src-test", store_dir=str(tmp_path), source="web")
    store.add_turn("q", "a")
    data = json.loads((tmp_path / "src-test.json").read_text())
    assert data["source"] == "web"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_add_turn_save_failure_does_not_corrupt_mem(tmp_path: Path) -> None:
    store = ConversationStore("fail-mem", store_dir=str(tmp_path))
    with mock.patch.object(ConversationStore, "_save", side_effect=OSError("no write")):
        with mock.patch.object(ConversationStore, "_check_compress"):
            store.add_turn("q", "a")
    # Memory updated regardless of save failure
    assert len(store._mem) == 2


def test_double_summarize_does_not_lose_turns(tmp_path: Path) -> None:
    store = ConversationStore("double-sum", store_dir=str(tmp_path))
    # First batch: 4 turns
    mock1 = mock.Mock(return_value="summary1")
    store.set_summarize_fn(mock1)
    store.add_turn("q1", "a1")
    store.add_turn("q2", "a2")
    store.add_turn("q3", "a3")
    store.add_turn("q4", "a4")
    assert store.summary == "summary1"
    assert store._mem == []
    mock1.assert_called_once()

    # Second batch: 4 more turns
    mock2 = mock.Mock(return_value="summary2")
    store.set_summarize_fn(mock2)
    store.add_turn("q5", "a5")
    store.add_turn("q6", "a6")
    store.add_turn("q7", "a7")
    store.add_turn("q8", "a8")
    # After second compression, previous summary + new turns merged
    assert store.summary == "summary2"
    assert store._mem == []
    mock2.assert_called_once()
