"""Lightweight PDF parser using pypdf.

This is the always-available fallback: no GPU, no extra services, works
offline. It is intentionally last in the router's fallback chain because
Docling/Marker/MinerU produce much better structure (headings, tables,
reading order) — but this one always works, so ingestion never hard-fails
just because a heavier parser's dependency isn't installed yet.
"""

from __future__ import annotations

from pathlib import Path

from app.parsers.base import ParsedBlock, ParsedDocument, ParserError


class PyPdfParser:
    name = "pypdf"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency always expected
            raise ParserError(f"pypdf not installed: {exc}") from exc

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise ParserError(f"pypdf failed to open '{path}': {exc}") from exc

        blocks: list[ParsedBlock] = []
        warnings: list[str] = []

        for page_idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                warnings.append(f"page {page_idx}: extraction failed ({exc})")
                continue

            for para in _split_paragraphs(text):
                blocks.append(
                    ParsedBlock(
                        text=para,
                        block_type="heading"
                        if _looks_like_heading(para)
                        else "paragraph",
                        level=1 if _looks_like_heading(para) else 0,
                        page=page_idx,
                    )
                )

        if not blocks:
            warnings.append(
                "No extractable text found — this PDF may be scanned/image-only "
                "and requires OCR (see app/ocr/)."
            )

        return ParsedDocument(
            source_path=str(path),
            blocks=blocks,
            parser_name=self.name,
            page_count=len(reader.pages),
            warnings=warnings,
        )


def _split_paragraphs(text: str) -> list[str]:
    raw_parts = [p.strip() for p in text.split("\n\n")]
    parts = [p for p in raw_parts if p]
    if len(parts) <= 1:
        parts = [p.strip() for p in text.split("\n") if p.strip()]
    return parts


def _looks_like_heading(text: str) -> bool:
    """Cheap heuristic: short line, no terminal punctuation, title-ish."""
    if len(text) > 80:
        return False
    if text.endswith((".", ",", ";")):
        return False
    words = text.split()
    if not words:
        return False
    return sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) // 2)
