"""OCR provider interfaces.

OCR is invoked by the ingest pipeline only when a parsed document has pages
with no extractable text (scanned/image PDFs) — see
`app/pipeline/ingest_pipeline.py`. Kept separate from parsers so any parser
can trigger OCR as a repair step rather than each parser reimplementing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class OcrResult:
    text: str
    confidence: float | None = None
    page: int | None = None


class OcrProvider(Protocol):
    name: str

    def is_available(self) -> bool:
        """Cheap check (no heavy load) for whether this provider can run."""
        ...

    def run(self, image_path: Path) -> OcrResult: ...
