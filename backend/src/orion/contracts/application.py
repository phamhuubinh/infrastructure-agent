"""Shared application inputs for HTTP, CLI and native client adapters.

Payloads express a requested operation. Authentication, scope resolution and
authorization remain in application services and transport boundaries.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orion.contracts import MutationMode


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class SubmitMessage(StrictRequest):
    content: str = Field(min_length=1)


class SessionTitleUpdate(StrictRequest):
    title: str = Field(max_length=120)


class SessionMutationModeUpdate(StrictRequest):
    mutation_mode: MutationMode


class ToolAuthorizationDecision(StrictRequest):
    decision: str = Field(pattern=r"^(allow|deny)$")
    payload_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ProjectInput(StrictRequest):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    instructions: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)
