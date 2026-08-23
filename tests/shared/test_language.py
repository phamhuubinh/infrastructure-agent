from __future__ import annotations

import pytest

from src.shared.language import (
    detect_language,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Kiểm tra CPU của máy này",
            "vi",
        ),
        (
            "Check CPU on this host",
            "en",
        ),
        (
            "Trả lời bằng tiếng Anh",
            "en",
        ),
        (
            "Please answer in Vietnamese",
            "vi",
        ),
        (
            "",
            "en",
        ),
    ],
)
def test_detect_language(
    text: str,
    expected: str,
) -> None:
    assert detect_language(text) == expected


def test_detect_language_requires_text() -> None:
    with pytest.raises(
        TypeError,
        match="string",
    ):
        detect_language(None)  # type: ignore[arg-type]
