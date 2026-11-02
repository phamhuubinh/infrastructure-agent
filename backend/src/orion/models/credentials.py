"""Server-side credential references, resolved once at the request boundary."""

from __future__ import annotations

import os
import re
from typing import Protocol

from pydantic import SecretStr


class CredentialResolutionError(ValueError):
    """Category-only error; never include the reference value or resolved secret."""


class CredentialResolver(Protocol):
    def resolve(self, reference: str) -> SecretStr: ...


class EnvironmentCredentialResolver:
    """Explicit env:NAME references, without probing or guessing vendor keys."""

    def resolve(self, reference: str) -> SecretStr:
        if not re.fullmatch(r"env:[A-Za-z_][A-Za-z0-9_]{0,127}", reference):
            raise CredentialResolutionError("Unsupported credential reference.")
        value = os.getenv(reference[4:])
        if not value:
            raise CredentialResolutionError("Configured provider credential is unavailable.")
        if len(value) > 16_384 or any(not 33 <= ord(char) <= 126 for char in value):
            raise CredentialResolutionError("Configured provider credential is invalid.")
        return SecretStr(value)
