import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch

import pytest
from app.ocr.base import OcrResult
from app.ocr.paddleocr_provider import PaddleOcrProvider


def test_ocr_exception_handling():
    """Test that OCR exceptions are properly handled and logged."""
    provider = PaddleOcrProvider()

    # Mock the engine to raise a RuntimeError
    with patch.object(provider, "_get_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_engine.ocr.side_effect = RuntimeError("OCR engine failed")
        mock_get_engine.return_value = mock_engine

        # Mock the logger to capture log calls
        with patch.object(provider, "logger") as mock_logger:
            result = provider.run(Path("test_image.png"))

            # Verify that the exception was logged
            mock_logger.exception.assert_called_once_with(
                "OCR processing failed for image %s: %s",
                Path("test_image.png"),
                "OCR engine failed",
            )

            # Verify that the function returns an empty OcrResult
            assert isinstance(result, OcrResult)
            assert result.text == ""
            assert result.confidence is None


def test_ocr_exception_handling_different_exception_types():
    """Test that different exception types are handled properly."""
    provider = PaddleOcrProvider()

    # Test with FileNotFoundError
    with patch.object(provider, "_get_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_engine.ocr.side_effect = FileNotFoundError("File not found")
        mock_get_engine.return_value = mock_engine

        with patch.object(provider, "logger") as mock_logger:
            result = provider.run(Path("missing_image.png"))

            mock_logger.exception.assert_called_once_with(
                "OCR processing failed for image %s: %s",
                Path("missing_image.png"),
                "File not found",
            )

            assert isinstance(result, OcrResult)
            assert result.text == ""
            assert result.confidence is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
