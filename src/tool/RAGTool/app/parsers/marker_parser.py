"""Marker parser adapter (fallback tier).

Marker (github.com/VikParuchuri/marker) converts PDFs to markdown, generally
faster than Docling and a good fallback when Docling's layout models choke
on a document. Requires `pip install marker-pdf`. Written against Marker's
real API (`PdfConverter` + model dict loader); fails soft to let the router
try MinerU/pypdf next.
"""

from __future__ import annotations

from pathlib import Path

from app.parsers.base import ParsedBlock, ParsedDocument, ParserError


class MarkerParser:
    name = "marker"

    def __init__(self) -> None:
        self._converter = None

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def _get_converter(self):
        if self._converter is None:
            try:
                from marker.converters.pdf import PdfConverter
                from marker.models import create_model_dict
            except ImportError as exc:
                msg = "marker-pdf is not installed (`pip install marker-pdf`)"
                raise ParserError(msg) from exc
            self._converter = PdfConverter(artifact_dict=create_model_dict())
        return self._converter

    def parse(self, path: Path) -> ParsedDocument:
        converter = self._get_converter()

        try:
            from marker.output import text_from_rendered

            rendered = converter(str(path))
            markdown_text, _, _images = text_from_rendered(rendered)
        except Exception as exc:
            pargs_msg = f"marker failed to convert '{path}': {exc}"
            raise ParserError(pargs_msg) from exc

        blocks = _markdown_to_blocks(markdown_text)
        return ParsedDocument(
            source_path=str(path),
            blocks=blocks,
            parser_name=self.name,
        )


def _markdown_to_blocks(markdown_text: str) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    for raw_line in markdown_text.split("\n\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            blocks.append(
                ParsedBlock(
                    text=line.lstrip("# ").strip(), block_type="heading", level=level
                )
            )
        elif line.startswith("|"):
            blocks.append(ParsedBlock(text=line, block_type="table"))
        elif line.startswith(("- ", "* ", "1. ")):
            blocks.append(ParsedBlock(text=line, block_type="list"))
        else:
            blocks.append(ParsedBlock(text=line, block_type="paragraph"))
    return blocks
