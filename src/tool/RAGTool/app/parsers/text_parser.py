"""Parser for UTF-8 text-like documents used by project knowledge bases."""

from __future__ import annotations

import json
from pathlib import Path

from app.parsers.base import ParsedBlock, ParsedDocument, ParserError

_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".log", ".csv", ".json", ".yaml", ".yml"}


class TextParser:
    name = "text"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in _TEXT_SUFFIXES

    def parse(self, path: Path) -> ParsedDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except OSError as exc:
                raise ParserError(f"Cannot read text document: {exc}") from exc
        except OSError as exc:
            raise ParserError(f"Cannot read text document: {exc}") from exc

        if path.suffix.lower() == ".json":
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass

        blocks: list[ParsedBlock] = []
        for raw in text.split("\n\n"):
            value = raw.strip()
            if not value:
                continue
            first_line = value.splitlines()[0].strip()
            is_heading = first_line.startswith("#") and len(value.splitlines()) == 1
            blocks.append(
                ParsedBlock(
                    text=first_line.lstrip("# ") if is_heading else value,
                    block_type="heading" if is_heading else "paragraph",
                    level=min(len(first_line) - len(first_line.lstrip("#")), 6)
                    if is_heading
                    else 0,
                )
            )

        return ParsedDocument(
            source_path=str(path),
            blocks=blocks,
            parser_name=self.name,
            page_count=None,
            warnings=[] if blocks else ["Document contains no readable text."],
        )
