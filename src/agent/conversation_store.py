from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from src.shared.logger import info


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


def list_sessions(store_dir: str | None = None) -> list[dict]:
    store_path = Path(store_dir or os.path.join(os.path.expanduser("~"), ".orion", "sessions"))
    sessions = []
    if not store_path.exists():
        return sessions
    for f in sorted(store_path.glob("*.json"), key=os.path.getmtime, reverse=True)[:50]:
        try:
            data = json.loads(f.read_text())
            msgs = data.get("messages", [])
            sessions.append({
                "id": data.get("session_id", f.stem),
                "title": data.get("title", ""),
                "source": data.get("source", "terminal"),
                "updated": data.get("updated_at", ""),
                "turns": len([m for m in msgs if m.get("role") == "user"]),
                "preview": (msgs[:1] or [{}])[0].get("content", "")[:80] if msgs else "",
                "has_summary": bool(data.get("summary")),
            })
        except Exception:
            pass
    return sessions


class ConversationStore:
    def __init__(self, session_id: str, store_dir: str | None = None,
                 summarize_fn: Callable[[str], str] | None = None,
                 source: str = "terminal") -> None:
        self._session_id = session_id
        self._source = source
        self._store_dir = Path(store_dir or os.path.join(os.path.expanduser("~"), ".orion", "sessions"))
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._mem: list[dict[str, str]] = []
        self._summary: str | None = None
        self._dirty = False
        self._summarize_fn = summarize_fn
        self._load()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> list[dict[str, str]]:
        if self._summary:
            return [{"role": "system", "content": f"Previous conversation summary: {self._summary}"}] + self._mem
        return list(self._mem)

    def add_turn(self, user: str, assistant: str) -> None:
        self._mem.append({"role": "user", "content": user})
        self._mem.append({"role": "assistant", "content": assistant})
        self._dirty = True
        self._save()
        self._check_compress()

    def add_classifier_turn(self, user: str, label: str) -> None:
        self._mem.append({"role": "user", "content": user})
        self._mem.append({"role": "assistant", "content": f"[classified as {label}]"})
        self._dirty = True
        self._save()
        self._check_compress()

    def summarize(self) -> None:
        all_turns = list(self._mem)
        if not all_turns:
            return

        new_turns_text = "\n".join(
            f"{m['role']}: {m['content'][:500]}"
            for m in all_turns
        )

        prompt = _SUMMARIZE_SYSTEM_PROMPT.format(
            previous_summary=self._summary or "None",
            new_turns=new_turns_text,
        )

        try:
            if self._summarize_fn:
                new_summary = self._summarize_fn(prompt).strip()
                if new_summary:
                    self._summary = new_summary
                    self._mem = []
                    self._dirty = True
                    self._save()
                    info("session", session=self._session_id, summary_length=len(self._summary),
                         message="Conversation summarized via LLM")
        except Exception as exc:
            info("session", session=self._session_id, error=str(exc)[:80],
                 message="Summarization failed, keeping full history")

    def set_summary(self, summary: str) -> None:
        self._summary = summary

    @property
    def summary(self) -> str | None:
        return self._summary

    def _check_compress(self) -> None:
        turn_count = len([m for m in self._mem if m["role"] == "user"])
        if turn_count >= 4:
            self.summarize()

    @property
    def store_path(self) -> Path:
        return self._store_dir / f"{self._session_id}.json"

    def _load(self) -> None:
        path = self.store_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._mem = data.get("messages", [])
            self._summary = data.get("summary")
            info("session", session=self._session_id, messages=len(self._mem),
                 has_summary=self._summary is not None,
                 message="Session loaded from disk")
        except (json.JSONDecodeError, OSError) as exc:
            info("session", session=self._session_id, error=str(exc)[:60],
                 message="Failed to load session, starting fresh")

    def _save(self) -> None:
        if not self._dirty:
            return
        try:
            data: dict[str, Any] = {
                "session_id": self._session_id,
                "source": self._source,
                "updated_at": datetime.now().isoformat(),
                "messages": self._mem,
            }
            if self._summary:
                data["summary"] = self._summary
            self.store_path.write_text(json.dumps(data, indent=2))
            self._dirty = False
        except OSError as exc:
            info("session", session=self._session_id, error=str(exc)[:60],
                 message="Failed to save session")
