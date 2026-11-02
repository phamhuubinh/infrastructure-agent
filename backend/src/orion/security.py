"""Small boundary redaction helpers for public diagnostics and tool outputs."""

from __future__ import annotations

import os
import re
from contextvars import ContextVar, Token
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_STATIC_MARKERS = ("ORION_TEST_SECRET_TOKEN", "ORION_TEST_PRIVATE_URL", "/private/test/key")
_SECRET_ENV_NAME = re.compile(r"(?:SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE|API_KEY|AUTH)", re.I)
_URL_USERINFO = re.compile(r"(https?://)([^/@\s:]+)(?::[^/@\s]*)?@", re.I)
_AUTHORIZATION = re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)\S+")
_REQUEST_SECRETS: ContextVar[tuple[str, ...]] = ContextVar("orion_request_secrets", default=())


def protect_request_values(*values: str | None) -> Token[tuple[str, ...]]:
    return _REQUEST_SECRETS.set(
        tuple(dict.fromkeys((*_REQUEST_SECRETS.get(), *(value for value in values if value))))
    )


def reset_request_values(token: Token[tuple[str, ...]]) -> None:
    _REQUEST_SECRETS.reset(token)


def _active_secrets() -> tuple[str, ...]:
    environment = tuple(
        secret
        for name, secret in os.environ.items()
        if _SECRET_ENV_NAME.search(name) and secret and len(secret) >= 4
    )
    return tuple(dict.fromkeys((*environment, *_REQUEST_SECRETS.get())))


def _redact_text(value: str, secrets: tuple[str, ...]) -> str:
    redacted = _URL_USERINFO.sub(r"\1[REDACTED]@", value)
    redacted = _AUTHORIZATION.sub(r"\1[REDACTED]", redacted)
    for marker in _STATIC_MARKERS:
        redacted = redacted.replace(marker, "[REDACTED]")
    for secret in secrets:
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def redact_text(value: str, *, sensitive: tuple[str, ...] = ()) -> str:
    """Remove known local configuration secrets without interpreting user content."""
    return _redact_text(value, (*_active_secrets(), *sensitive))


def protected_value_present(value: Any, sensitive: tuple[str, ...] = ()) -> bool:
    secrets = tuple(dict.fromkeys(item for item in (*_REQUEST_SECRETS.get(), *sensitive) if item))
    if isinstance(value, str):
        return any(item in value for item in secrets)
    if isinstance(value, (tuple, list)):
        return any(protected_value_present(item, secrets) for item in value)
    if isinstance(value, dict):
        return any(
            protected_value_present(str(key), secrets) or protected_value_present(item, secrets)
            for key, item in value.items()
        )
    return False


class SecretStreamRedactor:
    """Hold only suffixes that could finish a known secret in a later delta."""

    def __init__(self, sensitive: tuple[str, ...] = ()) -> None:
        self._secrets = tuple(
            dict.fromkeys((*_STATIC_MARKERS, *_active_secrets(), *(v for v in sensitive if v)))
        )
        self._pending = ""
        self._tables: dict[str, list[int]] = {}
        for secret in self._secrets:
            table = [0] * len(secret)
            for index in range(1, len(secret)):
                matched = table[index - 1]
                while matched and secret[index] != secret[matched]:
                    matched = table[matched - 1]
                if secret[index] == secret[matched]:
                    matched += 1
                table[index] = matched
            self._tables[secret] = table

    def feed(self, fragment: str) -> str:
        combined = self._pending + fragment
        for secret in self._secrets:
            combined = combined.replace(secret, "[REDACTED]")
        held = 0
        for secret, table in self._tables.items():
            if len(secret) == 1:
                continue
            matched = 0
            for character in combined[-(len(secret) - 1) :]:
                while matched and character != secret[matched]:
                    matched = table[matched - 1]
                if character == secret[matched]:
                    matched += 1
            held = max(held, matched)
        visible = combined[:-held] if held else combined
        self._pending = combined[-held:] if held else ""
        return _redact_text(visible, self._secrets)

    def finish(self) -> str:
        visible, self._pending = self._pending, ""
        return _redact_text(visible, self._secrets)


def _redact_public(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return _redact_text(value, secrets)
    if isinstance(value, list):
        return [_redact_public(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_public(item, secrets) for item in value)
    if isinstance(value, dict):
        return {
            _redact_text(str(key), secrets): _redact_public(item, secrets)
            for key, item in value.items()
        }
    return value


def redact_public(value: Any) -> Any:
    """Recursively sanitize data leaving the application boundary."""
    return _redact_public(value, _active_secrets())


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
