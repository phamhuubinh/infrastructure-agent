"""Replaceable parsing, chunking, embedding, and retrieval ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ParsedSection:
    """One parser-produced text unit with stable source-location metadata."""

    text: str
    section: str | None = None
    page: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    sections: tuple[ParsedSection, ...]


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page: int | None
    section: str | None


@dataclass(frozen=True)
class IndexedSegment:
    segment_id: str
    text: str


class DocumentParser(Protocol):
    def parse(self, content: bytes, media_type: str | None) -> ParsedDocument: ...


class Chunker(Protocol):
    def chunk(self, parsed: ParsedDocument) -> tuple[Chunk, ...]: ...


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> dict[str, float]: ...


class LexicalIndex(Protocol):
    def search(self, query: str, segments: tuple[IndexedSegment, ...]) -> dict[str, float]: ...


class VectorIndex(Protocol):
    def search(self, query: str, segments: tuple[IndexedSegment, ...]) -> dict[str, float]: ...
