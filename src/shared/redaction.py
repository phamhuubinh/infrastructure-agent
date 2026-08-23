"""Shared credential redaction for logs, model errors, and evidence."""

from __future__ import annotations

import re


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b("
    r"password|passwd|token|api[_-]?key|authorization|"
    r"proxy[_-]?authorization|private[_-]?key|secret|"
    r"cookie|set[_-]?cookie"
    r")(\s*[:=]\s*)([^\s,;]+)"
)

_BEARER_TOKEN = re.compile(
    r"(?i)\bBearer\s+[^\s,;]+"
)

_URL_CREDENTIAL = re.compile(
    r"(://[^\s:/@]+:)[^\s@]+(@)"
)

_PEM_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?P<label>(?:RSA |OPENSSH )?PRIVATE KEY)-----"
    r"[ \t]*\r?\n.*?\r?\n"
    r"-----END (?P=label)-----",
    re.DOTALL,
)

_PROVIDER_STYLE_KEY = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}\b"
)


def redact_sensitive(value: str) -> str:
    """Redact common credential forms from diagnostic text."""

    if not isinstance(value, str):
        raise TypeError("value must be a string.")

    value = _PEM_PRIVATE_KEY_BLOCK.sub(
        "<redacted>",
        value,
    )
    value = _PROVIDER_STYLE_KEY.sub(
        "<redacted>",
        value,
    )
    value = _BEARER_TOKEN.sub(
        "Bearer <redacted>",
        value,
    )
    value = _SECRET_ASSIGNMENT.sub(
        r"\1\2<redacted>",
        value,
    )
    return _URL_CREDENTIAL.sub(
        r"\1<redacted>\2",
        value,
    )


__all__ = ["redact_sensitive"]
