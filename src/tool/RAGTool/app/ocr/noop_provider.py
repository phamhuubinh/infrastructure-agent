"""No-op OCR provider — the default until PaddleOCR is installed on the deploy host.

Returns empty text and lets the pipeline record a warning rather than
crash. This keeps ingestion working end-to-end (with a visible gap) on a
machine that hasn't installed PaddleOCR yet.
"""
from __future__ import annotations

from pathlib import Path

from app.ocr.base import OcrResult


class NoOpOcrProvider:
    name = "noop"

    def is_available(self) -> bool:
        return True

    def run(self, image_path: Path) -> OcrResult:
        return OcrResult(text="", confidence=0.0)
