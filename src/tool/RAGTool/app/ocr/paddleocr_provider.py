"""PaddleOCR provider.

Requires `pip install paddlepaddle paddleocr` (+ GPU build of paddlepaddle
for reasonable throughput). Written against PaddleOCR's real API
(`PaddleOCR(...).ocr(...)`). Model weights download on first use — needs
network the first time it runs, then caches locally.
"""
from __future__ import annotations

from pathlib import Path

from app.ocr.base import OcrResult


class PaddleOcrProvider:
    name = "paddleocr"

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang
        self._engine = None

    def is_available(self) -> bool:
        try:
            import paddleocr  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_engine(self):
        if self._engine is None:
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(use_angle_cls=True, lang=self._lang, show_log=False)
        return self._engine

    def run(self, image_path: Path) -> OcrResult:
        engine = self._get_engine()
        result = engine.ocr(str(image_path), cls=True)

        lines: list[str] = []
        confidences: list[float] = []
        for page_result in result or []:
            for detection in page_result or []:
                _box, (text, confidence) = detection
                lines.append(text)
                confidences.append(confidence)

        avg_confidence = sum(confidences) / len(confidences) if confidences else None
        return OcrResult(text="\n".join(lines), confidence=avg_confidence)
