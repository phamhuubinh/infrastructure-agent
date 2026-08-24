"""Small language helpers shared by user-visible Orion boundaries.

Language detection is presentation metadata only. It performs no intent
classification, routing, capability selection, reference resolution, or
execution authorization.
"""

from __future__ import annotations

import re

_VIETNAMESE_PATTERN = re.compile(
    r"[àáảãạâầấẩẫậăằắẳẵặ"
    r"èéẻẽẹêềếểễệ"
    r"ìíỉĩị"
    r"òóỏõọôồốổỗộơờớởỡợ"
    r"ùúủũụưừứửữự"
    r"ỳýỷỹỵđ]",
    re.IGNORECASE,
)

_EXPLICIT_ENGLISH_RESPONSE = re.compile(
    r"(?:answer|reply|respond)\s+in\s+english|"
    r"(?:trả\s+lời|dịch)\s+(?:bằng|sang)\s+tiếng\s+anh|"
    r"(?:translate|translation)\s+(?:to|into)\s+english",
    re.IGNORECASE,
)

_EXPLICIT_VIETNAMESE_RESPONSE = re.compile(
    r"(?:answer|reply|respond)\s+in\s+vietnamese|"
    r"(?:trả\s+lời|dịch)\s+(?:bằng|sang)\s+tiếng\s+việt|"
    r"(?:translate|translation)\s+(?:to|into)\s+vietnamese",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """Return the requested/predominant response language.

    This deliberately distinguishes only Vietnamese and English because the
    current user-visible fallback and output-quality boundaries only require
    those two presentation modes.
    """

    if not isinstance(text, str):
        raise TypeError(
            "text must be a string."
        )

    if _EXPLICIT_ENGLISH_RESPONSE.search(
        text
    ):
        return "en"

    if _EXPLICIT_VIETNAMESE_RESPONSE.search(
        text
    ):
        return "vi"

    if _VIETNAMESE_PATTERN.search(text):
        return "vi"

    return "en"


__all__ = ["detect_language"]
