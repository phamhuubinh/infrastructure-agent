"""Request-bound, integrity-checked private protocol envelopes.

The MAC key lives only in the adapter instance. These envelopes cannot resume
after application restart and must never be persisted as conversation content.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from pydantic import SecretStr

from orion.contracts import ProviderContinuation
from orion.models.backend import ModelBackendError, ModelBackendErrorKind, ModelSettings
from orion.models.providers.transport import strict_json


class ContinuationCodec:
    def __init__(self, adapter_id: str) -> None:
        self.adapter_id = adapter_id
        self._key = secrets.token_bytes(32)

    @staticmethod
    def _binding(settings: ModelSettings) -> str:
        value = {
            "provider": settings.provider_type,
            "endpoint": settings.base_url,
            "model": settings.model_id,
            "profile": settings.profile.model_dump(mode="json") if settings.profile else None,
            "credential": hashlib.sha256((settings.api_key or "").encode()).hexdigest(),
            "reasoning": settings.reasoning_mode,
            "request": settings.request_binding,
            "scope": settings.runtime_scope.model_dump(mode="json")
            if settings.runtime_scope
            else None,
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()

    def pack(self, settings: ModelSettings, state: Any) -> ProviderContinuation:
        try:
            body = json.dumps(
                {"binding": self._binding(settings), "state": state},
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            tag = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
            return ProviderContinuation(
                adapter_id=self.adapter_id, payload=SecretStr(tag + ":" + body)
            )
        except (TypeError, ValueError, RecursionError):
            raise ModelBackendError(
                "Provider continuation exceeds supported protocol bounds.",
                kind=ModelBackendErrorKind.PROTOCOL,
            ) from None

    def unpack(self, settings: ModelSettings, state: ProviderContinuation) -> Any:
        try:
            if state.adapter_id != self.adapter_id:
                raise ValueError("adapter mismatch")
            tag, body = state.payload.get_secret_value().split(":", 1)
            expected = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(tag, expected):
                raise ValueError("integrity mismatch")
            value = strict_json(body)
            if value["binding"] != self._binding(settings):
                raise ValueError("request/profile/scope mismatch")
            return value["state"]
        except (TypeError, ValueError, KeyError, RecursionError):
            raise ModelBackendError(
                "Provider continuation is invalid for this request, profile or runtime instance.",
                kind=ModelBackendErrorKind.PROTOCOL,
            ) from None
