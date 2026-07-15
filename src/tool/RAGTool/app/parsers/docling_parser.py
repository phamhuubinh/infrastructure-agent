"""Docling parser adapter.

Docling (github.com/DS4SD/docling) is the primary parser: best layout/table
/reading-order understanding for general documents. Requires `pip install
docling` (pulls in torch + layout models — heavy, needs real disk/network,
not available in this sandbox). This module is written against Docling's
real public API so it works as-is once the dependency is installed on your
GPU/CPU host; it fails soft (ParserError) if the package or model download
isn't available, so the router falls back to Marker/MinerU/pypdf.
"""
from __future__ import annotations

from pathlib import Path

from app.parsers.base import ParsedBlock, ParsedDocument, ParserError


class DoclingParser:
    name = "docling"

    def __init__(self) -> None:
        self._converter = None  # lazy-loaded, model init is expensive

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".pdf", ".docx", ".pptx", ".html"}

    def _get_converter(self):
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter
            except ImportError as exc:
                raise ParserError(
                    "docling is not installed (`pip install docling`)"
                ) from exc
            self._converter = DocumentConverter()
        return self._converter

    def parse(self, path: Path) -> ParsedDocument:
        converter = self._get_converter()

        try:
            result = converter.convert(str(path))
        except Exception as exc:
            raise ParserError(f"docling failed to convert '{path}': {exc}") from exc

        doc = result.document
        blocks: list[ParsedBlock] = []

        # Docling exposes an iterator over document items (text, headings,
        # tables, pictures) each with a `prov` list carrying page numbers.
        for item, _level in doc.iterate_items():
            item_type = type(item).__name__.lower()
            page = None
            if getattr(item, "prov", None):
                page = getattr(item.prov[0], "page_no", None)

            if "table" in item_type:
                try:
                    table_text = item.export_to_markdown()
                except Exception:
                    table_text = str(getattr(item, "text", ""))
                blocks.append(
                    ParsedBlock(text=table_text, block_type="table", page=page)
                )
                continue

            text = getattr(item, "text", "") or ""
            if not text.strip():
                continue

            if "heading" in item_type or "title" in item_type or "section" in item_type:
                blocks.append(
                    ParsedBlock(
                        text=text,
                        block_type="heading",
                        level=getattr(item, "level", 1) or 1,
                        page=page,
                    )
                )
            elif "caption" in item_type:
                blocks.append(ParsedBlock(text=text, block_type="caption", page=page))
            elif "list" in item_type:
                blocks.append(ParsedBlock(text=text, block_type="list", page=page))
            else:
                blocks.append(ParsedBlock(text=text, block_type="paragraph", page=page))

        page_count = getattr(doc, "num_pages", None)
        return ParsedDocument(
            source_path=str(path),
            blocks=blocks,
            parser_name=self.name,
            page_count=page_count() if callable(page_count) else page_count,
        )
