"""Public runtime event namespace and JSON-only payload boundary.

Wire transport/replay cursors are separate from these semantic events. Private
provider state and native SDK objects have no representation in this contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, JsonValue

from orion.contracts import CanonicalModel

RuntimeEventType = Literal[
    "request.accepted",
    "request.completed",
    "request.incomplete",
    "request.cancelled",
    "request.failed",
    "model.started",
    "model.completed",
    "model.resumed",
    "assistant.delta",
    "assistant.message",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "tool.authorization",
    "tool.authorization_required",
    "recovery.stalled",
]


class RuntimeEvent(CanonicalModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    type: RuntimeEventType
    payload: dict[str, JsonValue]
