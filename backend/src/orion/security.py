"""Small boundary redaction helpers for public diagnostics and tool outputs."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_STATIC_MARKERS = ("ORION_TEST_SECRET_TOKEN", "ORION_TEST_PRIVATE_URL", "/private/test/key")
_SECRET_ENV_NAME = re.compile(r"(?:SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE|API_KEY|AUTH)", re.I)
_URL_USERINFO = re.compile(r"(https?://)([^/@\s:]+)(?::[^/@\s]*)?@", re.I)
_AUTHORIZATION = re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)\S+")


def redact_text(value: str) -> str:
    """Remove known local configuration secrets without interpreting user content."""
    redacted = _URL_USERINFO.sub(r"\1[REDACTED]@", value)
    redacted = _AUTHORIZATION.sub(r"\1[REDACTED]", redacted)
    for marker in _STATIC_MARKERS:
        redacted = redacted.replace(marker, "[REDACTED]")
    for name, secret in os.environ.items():
        if _SECRET_ENV_NAME.search(name) and secret and len(secret) >= 4:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def redact_public(value: Any) -> Any:
    """Recursively sanitize data leaving the application boundary."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_public(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_public(item) for item in value)
    if isinstance(value, dict):
        return {str(key): redact_public(item) for key, item in value.items()}
    return value


def safe_endpoint(value: str) -> str:
    """Keep an endpoint's non-secret identity for settings and diagnostics."""
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.hostname:
            return redact_text(value)
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        netloc = host if parsed.port is None else f"{host}:{parsed.port}"
        return redact_text(urlunsplit((parsed.scheme, netloc, parsed.path, "", "")))
    except ValueError:
        return "configured"
