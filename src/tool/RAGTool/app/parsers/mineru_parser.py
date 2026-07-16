"""MinerU parser adapter (scientific-document tier).

MinerU (github.com/opendatalab/MinerU) is strongest on scientific papers —
formulas, multi-column layout, figure/table extraction with proper
reading order. Requires `pip install magic-pdf[full]`. This is the third
tier in the router: tried when the document looks like a scientific
paper (see router heuristic) and Docling/Marker are unavailable or fail.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.parsers.base import ParsedBlock, ParsedDocument, ParserError


class MinerUParser:
    name = "mineru"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDocument:
        try:
            from magic_pdf.data.data_reader_writer import (
                FileBasedDataReader,
                FileBasedDataWriter,
            )
            from magic_pdf.data.dataset import PymuDocDataset
            from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
        except ImportError as exc:
            raise ParserError(
                "MinerU (magic-pdf) is not installed (`pip install magic-pdf[full]`)"
            ) from exc

        with TemporaryDirectory() as tmp:
            try:
                reader = FileBasedDataReader("")
                pdf_bytes = reader.read(str(path))
                dataset = PymuDocDataset(pdf_bytes)

                infer_result = dataset.apply(doc_analyze, ocr=False)
                pipe_result = infer_result.pipe_ocr_mode(FileBasedDataWriter(tmp))

                content_list_writer = FileBasedDataWriter(tmp)
                pipe_result.dump_content_list(
                    content_list_writer, "content_list.json", "images"
                )
                content_list = json.loads(Path(tmp, "content_list.json").read_text())
            except Exception as exc:
                raise ParserError(f"MinerU failed to convert '{path}': {exc}") from exc

        blocks: list[ParsedBlock] = []
        for item in content_list:
            item_type = item.get("type", "text")
            text = item.get("text") or item.get("table_body") or ""
            if not text.strip():
                continue
            page = item.get("page_idx")
            if item_type == "table":
                blocks.append(ParsedBlock(text=text, block_type="table", page=page))
            elif item_type in {"title", "heading"}:
                blocks.append(
                    ParsedBlock(
                        text=text,
                        block_type="heading",
                        level=item.get("text_level", 1) or 1,
                        page=page,
                    )
                )
            elif item_type == "equation":
                blocks.append(
                    ParsedBlock(
                        text=text,
                        block_type="paragraph",
                        page=page,
                        metadata={"formula": True},
                    )
                )
            else:
                blocks.append(ParsedBlock(text=text, block_type="paragraph", page=page))

        return ParsedDocument(
            source_path=str(path), blocks=blocks, parser_name=self.name
        )
