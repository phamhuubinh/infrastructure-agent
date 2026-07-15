"""Document parser interfaces.

A DocumentParser turns a raw file (PDF, DOCX, etc.) into a ParsedDocument:
plain text plus structural hints (pages, headings, tables) that downstream
chunking can use. All parsers must implement the same contract so the
router can fall back between them transparently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ParsedBlock:
    """One structural unit extracted from a document."""

    text: str
    block_type: str = "paragraph"  # paragraph | heading | table | caption | list
    level: int = 0  # heading level (1 = H1), 0 for non-headings
    page: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    source_path: str
    blocks: list[ParsedBlock]
    parser_name: str
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text.strip())


class DocumentParser(Protocol):
    """Contract every parser (Docling, Marker, MinerU, pypdf...) must satisfy."""

    name: str

    def supports(self, path: Path) -> bool:
        """Return True if this parser can attempt to handle the given file."""
        ...

    def parse(self, path: Path) -> ParsedDocument:
        """Parse the file. Raise ParserError on failure so the router can fall back."""
        ...


class ParserError(RuntimeError):
    """Raised when a parser fails to process a document (triggers fallback)."""
