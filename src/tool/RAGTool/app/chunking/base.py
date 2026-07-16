"""Chunking interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.parsers.base import ParsedDocument


@dataclass
class Chunk:
    text: str
    chunk_id: str
    doc_id: str
    heading_path: list[str] = field(
        default_factory=list
    )  # e.g. ["1. Intro", "1.2 Scope"]
    page: int | None = None
    metadata: dict = field(default_factory=dict)


class Chunker(Protocol):
    def chunk(self, document: ParsedDocument, doc_id: str) -> list[Chunk]: ...
