"""Explicit adapter registration and request-bound provider dispatch.

The runtime selects no vendor, guesses no model capabilities and falls back to
no other model. Each registry is an immutable application-owned snapshot.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Mapping
from contextlib import aclosing
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import SecretStr

from orion.contracts import (
    ContextMessage,
    ModelTurnCompleted,
    ProviderContinuation,
    ToolDefinition,
    freeze_json,
)
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.models.backend import (
    ModelBackend,
    ModelBackendError,
    ModelBackendErrorKind,
    ModelSettings,
    ModelStreamEvent,
    ModelStreamSettings,
    validated_model_stream,
)
from orion.models.credentials import CredentialResolutionError, CredentialResolver
from orion.models.providers.continuation import ContinuationCodec


@dataclass(frozen=True)
class AdapterRegistration:
    adapter_id: str
    provider_id: str
    protocol: str
    backend: ModelBackend
    option_schema: dict[str, Any]


class ProviderRegistry(ModelBackend):
    def __init__(self, registrations: tuple[AdapterRegistration, ...]) -> None:
        registered: dict[tuple[str, str], AdapterRegistration] = {}
        identifiers: set[str] = set()
        for item in registrations:
            key = (item.provider_id, item.protocol)
            if not item.adapter_id or key in registered or item.adapter_id in identifiers:
                raise ValueError("duplicate or invalid provider adapter registration")
            try:
                Draft202012Validator.check_schema(item.option_schema)
            except SchemaError:
                raise ValueError("invalid provider option schema") from None
            if item.option_schema.get("type") != "object":
                raise ValueError("provider options require an object schema")
            snapshot = AdapterRegistration(
                item.adapter_id,
                item.provider_id,
                item.protocol,
                item.backend,
                freeze_json(item.option_schema),
            )
            registered[key] = snapshot
            identifiers.add(item.adapter_id)
        self._registrations: Mapping[tuple[str, str], AdapterRegistration] = MappingProxyType(
            registered
        )
        self._continuations = {key: ContinuationCodec(key) for key in identifiers}

    @staticmethod
    def _unsupported(message: str) -> ModelBackendError:
        return ModelBackendError(message, kind=ModelBackendErrorKind.UNSUPPORTED)

    def resolve(self, settings: ModelSettings) -> tuple[AdapterRegistration, ModelProfile]:
        profile = settings.profile
        if profile is None:
            if settings.provider_type != "openai_compatible":
                raise self._unsupported("An explicit provider profile is required.")
            # Legacy profiles are explicitly compatible, never inferred from a
            # model name or repurposed for a native vendor protocol.
            identity = hashlib.sha256(
                (settings.base_url + "\0" + settings.model_id).encode("utf-8")
            ).hexdigest()
            stream_timeout = ModelStreamSettings.from_environment().timeout_seconds
            profile = ModelProfile(
                profile_id=f"legacy-{identity}",
                provider_id="openai_compatible",
                protocol="chat_completions",
                endpoint=settings.base_url,
                model_id=settings.model_id,
                transport_timeout_seconds=stream_timeout,
                request_timeout_seconds=max(120, stream_timeout),
                capabilities=ModelCapabilities(
                    streaming=True,
                    tools=True,
                    tool_result_continuation=True,
                    usage=True,
                    reasoning_controls=True,
                ),
            )
        if (
            profile.provider_id != settings.provider_type
            or profile.endpoint != settings.base_url
            or profile.model_id != settings.model_id
        ):
            raise self._unsupported("Model settings do not match their bound profile.")
        registration = self._registrations.get((profile.provider_id, profile.protocol))
        if registration is None:
            raise self._unsupported("The configured provider protocol has no registered adapter.")
        if not Draft202012Validator(registration.option_schema).is_valid(profile.options):
            raise self._unsupported("The configured provider options are unsupported.")
        continuation = settings.provider_continuation
        if continuation is not None and continuation.adapter_id != registration.adapter_id:
            raise self._unsupported("Provider continuation belongs to another adapter.")
        validate = getattr(registration.backend, "validate_settings", None)
        if validate is not None:
            validate(settings)
        return registration, profile

    def bind_profile(self, profile: ModelProfile, credentials: CredentialResolver) -> ModelSettings:
        """Resolve a chosen profile/key once, before entering the runtime loop."""
        settings = ModelSettings(
            provider_type=profile.provider_id,
            base_url=profile.endpoint,
            model_id=profile.model_id,
            profile=profile,
        )
        # Reject missing adapters/options before consulting any credential source.
        registration, _ = self.resolve(settings)
        if profile.credential_ref is None:
            if getattr(registration.backend, "requires_credential", False):
                raise self._unsupported("The configured provider credential reference is required.")
            return settings
        try:
            secret = credentials.resolve(profile.credential_ref)
        except CredentialResolutionError:
            raise self._unsupported("The configured provider credential is unavailable.") from None
        return settings.model_copy(update={"api_key": secret.get_secret_value()})

    async def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        if cancellation.is_set():
            raise asyncio.CancelledError
        registration, profile = self.resolve(settings)
        capabilities = profile.capabilities
        if not capabilities.text or not capabilities.streaming:
            raise self._unsupported("This profile does not support streaming text.")
        if tools and not (capabilities.tools and capabilities.tool_result_continuation):
            raise self._unsupported("This profile does not support the canonical tool loop.")
        if settings.reasoning_mode != "auto" and not capabilities.reasoning_controls:
            raise self._unsupported("This profile does not support reasoning controls.")
        bound = settings.model_copy(update={"profile": profile})
        codec = self._continuations[registration.adapter_id]
        if bound.provider_continuation is not None:
            inner = codec.unpack(bound, bound.provider_continuation)
            if not isinstance(inner, str):
                raise self._unsupported("Invalid adapter continuation envelope.")
            bound = bound.model_copy(
                update={
                    "provider_continuation": ProviderContinuation(
                        adapter_id=registration.adapter_id, payload=SecretStr(inner)
                    )
                }
            )
        for attempt in range(profile.safe_transport_retries + 1):
            if cancellation.is_set():
                raise asyncio.CancelledError
            emitted = False

            async def observed_stream() -> AsyncIterator[ModelStreamEvent]:
                nonlocal emitted
                source = registration.backend.stream(messages, tools, bound, cancellation)
                try:
                    async for item in source:
                        emitted = True
                        yield item
                finally:
                    close = getattr(source, "aclose", None)
                    if close is not None:
                        await close()

            try:
                async with aclosing(
                    validated_model_stream(observed_stream(), credential=bound.api_key)
                ) as events:
                    async for event in events:
                        if isinstance(event, ModelTurnCompleted):
                            state = event.turn.provider_continuation
                            if state is not None:
                                if state.adapter_id != registration.adapter_id:
                                    raise self._unsupported(
                                        "Adapter returned foreign continuation."
                                    )
                                wrapped = codec.pack(bound, state.payload.get_secret_value())
                                event = event.model_copy(
                                    update={
                                        "turn": event.turn.model_copy(
                                            update={"provider_continuation": wrapped}
                                        )
                                    }
                                )
                        yield event
                return
            except ModelBackendError as error:
                if (
                    emitted
                    or not error.retry_safe
                    or error.kind
                    not in {
                        ModelBackendErrorKind.CONNECTION,
                        ModelBackendErrorKind.TIMEOUT,
                    }
                    or attempt >= profile.safe_transport_retries
                ):
                    raise
