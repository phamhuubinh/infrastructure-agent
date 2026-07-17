"""Fallback router: Docling -> Marker -> MinerU (if scientific) -> pypdf.

This is the piece that actually implements "Docling primary, Marker
fallback, MinerU for scientific docs" from the architecture. It never
hard-fails on a missing heavy dependency: each parser in the chain either
isn't installed (skip) or raises ParserError (try next). pypdf is always
last because it has no external dependency and therefore always works —
this guarantees ingestion never dies just because Docling/Marker aren't
deployed yet.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.parsers.base import DocumentParser, ParsedDocument, ParserError

logger = logging.getLogger(__name__)

_SCIENTIFIC_HINTS = (
    "abstract",
    "references",
    "doi:",
    "arxiv",
    "et al.",
    "fig.",
    "eq.",
)


class ParserRouter:
    def __init__(self, parsers: list[DocumentParser] | None = None) -> None:
        if parsers is None:
            parsers = self._default_chain()
        self._parsers = parsers

    @staticmethod
    def _default_chain() -> list[DocumentParser]:
        # Imported lazily so a missing heavy dependency doesn't crash the
        # whole service at import time — only when that parser is actually used.
        from app.parsers.docling_parser import DoclingParser
        from app.parsers.marker_parser import MarkerParser
        from app.parsers.mineru_parser import MinerUParser
        from app.parsers.pypdf_parser import PyPdfParser

        return [DoclingParser(), MarkerParser(), MinerUParser(), PyPdfParser()]

    def looks_scientific(self, path: Path) -> bool:
        try:
            sample = (
                path.read_bytes()[:20000].decode("latin-1", errors="ignore").lower()
            )
        except Exception:
            return False
        return sum(hint in sample for hint in _SCIENTIFIC_HINTS) >= 2

    def parse(self, path: Path) -> ParsedDocument:
        path = Path(path)
        if not path.exists():
            pargs_msg = f"File not found: {path}"
            raise ParserError(pargs_msg)

        chain = self._order_for(path)
        errors: list[str] = []

        for parser in chain:
            if not parser.supports(path):
                continue
            try:
                doc = parser.parse(path)
                if not doc.blocks:
                    errors.append(f"{parser.name}: produced no blocks")
                    continue
                if errors:
                    logger.info(
                        "Parsed '%s' with fallback parser '%s' after: %s",
                        path,
                        parser.name,
                        "; ".join(errors),
                    )
                return doc
            except ParserError as exc:
                errors.append(f"{parser.name}: {exc}")
                continue

        pargs_msg = f"All parsers failed for '{path}': {'; '.join(errors) or 'no applicable parser'}"
        raise ParserError(pargs_msg)

    def _order_for(self, path: Path) -> list[DocumentParser]:
        """MinerU jumps ahead of Marker for documents that look scientific."""
        if not self.looks_scientific(path):
            return self._parsers

        by_name = {p.name: p for p in self._parsers}
        ordered_names = ["docling", "mineru", "marker", "pypdf"]
        return [by_name[n] for n in ordered_names if n in by_name]
