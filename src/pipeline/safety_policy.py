"""Deterministic refusal policy for requests to disclose protected data.

This policy deliberately runs before intent expansion and tool planning.  A
request containing words such as ``SSH`` or ``system`` is not, by itself,
dangerous; only a request to reveal protected instructions, credentials, or
credential files is refused.  That distinction keeps ordinary explanations
available while ensuring a disclosure request never reaches a collector or an
LLM prompt.
"""

from __future__ import annotations

import re
from enum import Enum


class SensitiveRequestKind(str, Enum):
    HIDDEN_INSTRUCTIONS = "hidden_instructions"
    CREDENTIAL = "credential"
    CREDENTIAL_FILE = "credential_file"


class SensitiveRequestPolicy:
    """Classify protected-data disclosure requests without executing work."""

    _HIDDEN_INSTRUCTIONS = re.compile(
        r"(?:system|hidden|developer|internal)\s*(?:prompt|instruction|instructions)"
        r"|(?:system|hidden)\s*(?:lời\s*nhắc|hướng\s*dẫn|chỉ\s*thị)",
        re.IGNORECASE,
    )
    _CREDENTIAL = re.compile(
        r"\b(?:api[ _-]?key|access[ _-]?token|secret|password|credential|"
        r"private\s+(?:ssh\s+)?key|ssh\s+private\s+key)\b"
        r"|(?:khóa|khoa)\s*(?:api|bí\s*mật|bi\s*mat|riêng|rieng)"
        r"|mật\s*khẩu|mat\s*khau|thông\s*tin\s*đăng\s*nhập",
        re.IGNORECASE,
    )
    _CREDENTIAL_FILE = re.compile(
        r"(?:^|[\s'\"])(?:/etc/shadow|/etc/gshadow|/etc/passwd|"
        r"~?/\.ssh/(?:id_[\w.-]+|authorized_keys)|"
        r"(?:[\w.-]+/)*\.env(?:\.[\w.-]+)?|"
        r"(?:[\w.-]+/)*(?:credentials?|secrets?)(?:\.[\w.-]+)?)\b",
        re.IGNORECASE,
    )
    _DISCLOSURE = re.compile(
        r"\b(?:show|print|reveal|display|give|send|export|dump|read|copy|"
        r"repeat|tell\s+me|output|list|in|đọc|doc|gửi|gui|cho\s+tôi|"
        r"cho\s+toi|nhắc\s+lại|nhac\s+lai|hiển\s+thị|hien\s+thi|xuất)\b",
        re.IGNORECASE,
    )
    _OWNED_CREDENTIAL = re.compile(
        r"(?:orion|server|máy|may|hệ\s*thống|he\s*thong).{0,40}"
        r"(?:api[ _-]?key|token|secret|password|private\s+key|mật\s*khẩu|"
        r"mat\s*khau|khóa\s*riêng|khoa\s*rieng)",
        re.IGNORECASE,
    )

    @classmethod
    def classify(cls, raw_request: str) -> SensitiveRequestKind | None:
        """Return a protected-data kind only for an attempted disclosure."""

        text = raw_request.strip()
        if not text:
            return None
        disclosure = bool(cls._DISCLOSURE.search(text))
        if cls._HIDDEN_INSTRUCTIONS.search(text) and disclosure:
            return SensitiveRequestKind.HIDDEN_INSTRUCTIONS
        if cls._CREDENTIAL_FILE.search(text) and disclosure:
            return SensitiveRequestKind.CREDENTIAL_FILE
        if cls._CREDENTIAL.search(text) and (disclosure or cls._OWNED_CREDENTIAL.search(text)):
            return SensitiveRequestKind.CREDENTIAL
        return None

    @classmethod
    def refusal_reason(cls, raw_request: str) -> str | None:
        kind = cls.classify(raw_request)
        return f"sensitive:{kind.value}" if kind is not None else None


def sensitive_refusal(raw_request: str) -> str | None:
    """Compatibility helper for boundaries that only need a refusal reason."""

    return SensitiveRequestPolicy.refusal_reason(raw_request)


__all__ = ["SensitiveRequestKind", "SensitiveRequestPolicy", "sensitive_refusal"]
