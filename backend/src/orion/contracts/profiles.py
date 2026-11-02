"""Versioned provider-neutral profile configuration, without resolved secrets."""

from __future__ import annotations

from typing import Literal, cast
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from orion.contracts import CanonicalModel, freeze_json

ProviderId = Literal["deepseek", "claude", "openai", "openai_compatible"]
ModelProtocol = Literal["chat_completions", "anthropic_messages", "openai_responses"]


class ModelCapabilities(CanonicalModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    text: bool = True
    streaming: bool = False
    tools: bool = False
    tool_result_continuation: bool = False
    structured_output: bool = False
    vision: bool = False
    usage: bool = False
    reasoning_controls: bool = False

    @model_validator(mode="after")
    def coherent_tools(self) -> ModelCapabilities:
        if self.tool_result_continuation and not self.tools:
            raise ValueError("tool-result continuation requires tool support")
        return self


class ModelProfile(CanonicalModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    profile_id: str = Field(min_length=1, max_length=128)
    provider_id: ProviderId
    protocol: ModelProtocol
    endpoint: str = Field(min_length=1, max_length=2048)
    model_id: str = Field(min_length=1, max_length=256)
    credential_ref: str | None = Field(default=None, min_length=1, max_length=128)
    capabilities: ModelCapabilities
    # Adapter registration supplies the option schema; core retains an immutable
    # JSON snapshot and never interprets vendor-specific fields or model aliases.
    options: dict[str, JsonValue] = Field(default_factory=dict, validate_default=True)
    context_max_bytes: int = Field(default=131_072, strict=True, ge=4096, le=8_388_608)
    request_max_bytes: int = Field(default=262_144, strict=True, ge=4096, le=16_777_216)
    request_timeout_seconds: float = Field(default=120, ge=1, le=3600, allow_inf_nan=False)
    transport_timeout_seconds: float = Field(default=30, ge=1, le=300, allow_inf_nan=False)
    # Retry permission is only for safe provider transport attempts, never tools.
    safe_transport_retries: int = Field(default=0, strict=True, ge=0, le=2)

    @field_validator("endpoint")
    @classmethod
    def safe_endpoint(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError:
            raise ValueError("Profile endpoint is invalid.") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(char.isspace() or ord(char) < 32 for char in value)
        ):
            raise ValueError(
                "profile endpoint must be an HTTP(S) URL without credentials/query/fragment"
            )
        return value

    @field_validator("options")
    @classmethod
    def snapshot_options(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        import json

        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
        if len(encoded) > 32_768:
            raise ValueError("profile options exceed UTF-8 byte limit")
        return cast(dict[str, JsonValue], freeze_json(value))

    @model_validator(mode="after")
    def coherent_profile(self) -> ModelProfile:
        supported = {
            "deepseek": {"chat_completions"},
            "claude": {"anthropic_messages"},
            "openai": {"openai_responses", "chat_completions"},
            "openai_compatible": {"chat_completions"},
        }
        if self.protocol not in supported[self.provider_id]:
            raise ValueError("provider and protocol do not match")
        if self.request_max_bytes < self.context_max_bytes:
            raise ValueError("request bound must include the conversation context")
        if self.transport_timeout_seconds > self.request_timeout_seconds:
            raise ValueError("transport timeout exceeds request timeout")
        return self
