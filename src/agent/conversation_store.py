from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.shared.logger import info


@runtime_checkable
class ConversationStoreProtocol(Protocol):
    """Protocol defining the interface all conversation stores must implement.

    Implemented by:
    - ConversationStore (JSON files — legacy)
    - PostgresConversationStore (PostgreSQL — when ORION_DATABASE_URL is set)
    - SQLiteConversationStore (SQLite — default as of Task 011)
    """

    @property
    def history(self) -> list[dict[str, Any]]: ...

    def set_title(self, value: str) -> None: ...

    def add_turn(self, user: str, assistant: str) -> None: ...

    def truncate_for_regeneration(
        self, turn_index: int
    ) -> list[dict[str, Any]] | None: ...

    def restore_messages(self, messages: list[dict[str, Any]]) -> None: ...

    def set_last_response_time(
        self, response_time_ms: int, asked_at: str | None = None
    ) -> None: ...

    def add_classifier_turn(self, user: str, label: str) -> None: ...

    def set_summarize_fn(self, fn: Callable[[str], str]) -> None: ...

    def set_summary(self, summary: str) -> None: ...

    def summarize(self) -> None: ...

    @property
    def summary(self) -> str | None: ...
    @property
    def title(self) -> str: ...
    @property
    def session_id(self) -> str: ...


_SUMMARIZE_SYSTEM_PROMPT = """You are a conversation summarizer for an infrastructure monitoring assistant.

Summarize the key technical details from the conversation history below. Focus on:
- What servers/systems were checked and their health status
- Specific metrics mentioned (CPU, memory, disk, network, services)
- Issues found and recommendations given
- Any decisions or follow-up actions

Keep the summary concise (3-5 sentences) but include all specific numbers and findings.
If this is an update to an existing summary, merge the new information with the old.

Previous summary (if any):
{previous_summary}

New conversation turns to incorporate:
{new_turns}

Produce only the new merged summary, nothing else."""


def regeneration_start_index(
    messages: list[dict[str, Any]], turn_index: int
) -> int | None:
    """Locate the raw-message offset for a visible user/assistant turn."""
    if turn_index < 0:
        return None

    visible_turn = 0
    for index, message in enumerate(messages[:-1]):
        next_message = messages[index + 1]
        if message.get("role") != "user" or next_message.get("role") != "assistant":
            continue
        if next_message.get("content", "").startswith("[classified as"):
            continue
        if visible_turn != turn_index:
            visible_turn += 1
            continue

        start = index
        if (
            index >= 2
            and messages[index - 2].get("role") == "user"
            and messages[index - 2].get("content") == message.get("content")
            and messages[index - 1].get("role") == "assistant"
            and messages[index - 1]
            .get("content", "")
            .startswith("[classified as")
        ):
            start = index - 2
        return start

    return None


def list_sessions(store_dir: str | None = None) -> list[dict]:
    store_path = Path(store_dir or Path.home() / ".orion" / "sessions")
    sessions: list[dict[str, Any]] = []
    if not store_path.exists():
        return sessions
    for f in sorted(
        store_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )[:50]:
        try:
            data = json.loads(f.read_text())
            msgs = data.get("messages", [])
            # Filter out classifier pairs: user + assistant "[classified as ...]"
            real_msgs = []
            skip_next = False
            for i, m in enumerate(msgs):
                if skip_next:
                    skip_next = False
                    continue
                if (
                    m.get("role") == "user"
                    and i + 1 < len(msgs)
                    and msgs[i + 1].get("role") == "assistant"
                    and msgs[i + 1].get("content", "").startswith("[classified as")
                ):
                    skip_next = True
                    continue
                real_msgs.append(m)
            sessions.append(
                {
                    "id": data.get("session_id", f.stem),
                    "title": data.get("title", ""),
                    "source": data.get("source", "terminal"),
                    "updated": data.get("updated_at", ""),
                    "turns": len([m for m in real_msgs if m.get("role") == "user"]),
                    "preview": (
                        (real_msgs[:1] or [{}])[0].get("content", "")[:80]
                        if real_msgs
                        else ""
                    ),
                    "has_summary": bool(data.get("summary")),
                    "messages": real_msgs,
                }
            )
        except Exception:
            info("conversation", message=f"failed to load session {f.name}")
    return sessions


class ConversationStore:
    def __init__(
        self,
        session_id: str,
        store_dir: str | None = None,
        summarize_fn: Callable[[str], str] | None = None,
        source: str = "terminal",
    ) -> None:
        self._session_id = session_id
        self._source = source
        self._store_dir = Path(store_dir or Path.home() / ".orion" / "sessions")
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._mem: list[dict[str, Any]] = []
        self._summary: str | None = None
        self._title: str = ""
        self._dirty = False
        self._summarize_fn = summarize_fn
        self._load()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._summary:
                return [
                    {
                        "role": "system",
                        "content": f"Previous conversation summary: {self._summary}",
                    }
                ] + self._mem
            return list(self._mem)

    def add_turn(self, user: str, assistant: str) -> None:
        with self._lock:
            self._mem.append({"role": "user", "content": user})
            self._mem.append({"role": "assistant", "content": assistant})
            self._dirty = True
            try:
                self._save()
            except OSError:
                info(
                    "conversation",
                    message=f"failed to save session {self._session_id}",
                )
            self._check_compress()

    def truncate_for_regeneration(
        self, turn_index: int
    ) -> list[dict[str, Any]] | None:
        with self._lock:
            start = regeneration_start_index(self._mem, turn_index)
            if start is None:
                return None
            snapshot = list(self._mem)
            self._mem = self._mem[:start]
            self._dirty = True
            self._save()
            return snapshot

    def restore_messages(self, messages: list[dict[str, Any]]) -> None:
        with self._lock:
            self._mem = list(messages)
            self._dirty = True
            self._save()

    def set_last_response_time(
        self, response_time_ms: int, asked_at: str | None = None
    ) -> None:
        with self._lock:
            assistant_updated = False
            for message in reversed(self._mem):
                role = message.get("role")
                if not assistant_updated and role == "assistant":
                    message["response_time_ms"] = max(0, int(response_time_ms))
                    assistant_updated = True
                elif assistant_updated and asked_at is not None and role == "user":
                    message["asked_at"] = asked_at
                    break
            if not assistant_updated:
                return
            self._dirty = True
            try:
                self._save()
            except OSError:
                info(
                    "conversation",
                    message=f"failed to save turn timing for {self._session_id}",
                )

    def add_classifier_turn(self, user: str, label: str) -> None:
        with self._lock:
            self._mem.append({"role": "user", "content": user})
            self._mem.append(
                {"role": "assistant", "content": f"[classified as {label}]"}
            )
            self._dirty = True
            try:
                self._save()
            except OSError:
                info(
                    "conversation",
                    message=f"failed to save classifier session {self._session_id}",
                )
            self._check_compress()

    def summarize(self) -> None:
        with self._lock:
            all_turns = list(self._mem)
            previous_summary = self._summary
            summarize_fn = self._summarize_fn
            if not all_turns:
                return

        new_turns_text = "\n".join(
            f"{m['role']}: {m['content'][:500]}" for m in all_turns
        )

        prompt = _SUMMARIZE_SYSTEM_PROMPT.format(
            previous_summary=previous_summary or "None",
            new_turns=new_turns_text,
        )

        try:
            if summarize_fn:
                new_summary = summarize_fn(prompt).strip()
            else:
                new_summary = ""
        except Exception as exc:
            info(
                "session",
                session=self._session_id,
                error=str(exc)[:80],
                message="Summarization failed, keeping full history",
            )
            return

        if not new_summary:
            return

        with self._lock:
            len_before = len(all_turns)
            # Remove the summarized prefix only if it is still present. A
            # concurrent summarizer may already have removed the same
            # snapshot; slicing again would discard newer turns.
            if self._mem[:len_before] == all_turns:
                self._mem = self._mem[len_before:]
            self._summary = new_summary
            self._dirty = True
            self._save()
            info(
                "session",
                session=self._session_id,
                summary_length=len(self._summary),
                message="Conversation summarized via LLM",
            )

    def set_summarize_fn(self, fn: Callable[[str], str]) -> None:
        with self._lock:
            self._summarize_fn = fn

    def set_summary(self, summary: str) -> None:
        with self._lock:
            self._summary = summary

    @property
    def title(self) -> str:
        with self._lock:
            return self._title

    def set_title(self, value: str) -> None:
        with self._lock:
            self._title = value

    @property
    def summary(self) -> str | None:
        with self._lock:
            return self._summary

    def _check_compress(self) -> None:
        # Count real turns — skip classifier messages
        turn_count = 0
        for i, m in enumerate(self._mem):
            if m["role"] == "user":
                next_msg = self._mem[i + 1] if i + 1 < len(self._mem) else None
                if next_msg is None or not next_msg.get("content", "").startswith(
                    "[classified as"
                ):
                    turn_count += 1
        from src.shared.config import get_config

        threshold = int(get_config().env("ORION_CONVERSATION_THRESHOLD", "50"))
        if turn_count >= threshold:
            self.summarize()

    @property
    def store_path(self) -> Path:
        return self._store_dir / f"{self._session_id}.json"

    def _load(self) -> None:
        with self._lock:
            path = self.store_path
            if not path.exists():
                return
            try:
                data = json.loads(path.read_text())
                self._mem = data.get("messages", [])
                self._summary = data.get("summary")
                self._title = data.get("title", "")
                loaded_source = data.get("source")
                if loaded_source:
                    self._source = loaded_source
                info(
                    "session",
                    session=self._session_id,
                    messages=len(self._mem),
                    has_summary=self._summary is not None,
                    title=self._title,
                    message="Session loaded from disk",
                )
            except (json.JSONDecodeError, OSError) as exc:
                info(
                    "session",
                    session=self._session_id,
                    error=str(exc)[:60],
                    message="Failed to load session, starting fresh",
                )

    def _save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            try:
                data: dict[str, Any] = {
                    "session_id": self._session_id,
                    "source": self._source,
                    "title": self._title,
                    "updated_at": datetime.now().isoformat(),
                    "messages": self._mem,
                }
                if self._summary:
                    data["summary"] = self._summary
                self.store_path.write_text(json.dumps(data, indent=2))
                self._dirty = False
            except OSError as exc:
                info(
                    "session",
                    session=self._session_id,
                    error=str(exc)[:60],
                    message="Failed to save session",
                )
