"""Client admission and bounded resumable observation, independent of model semantics."""

from typing import Literal

from pydantic import UUID4, Field

from orion.contracts.application import StrictRequest
from orion.contracts.events import RuntimeEvent

RequestStatus = Literal["queued", "running", "completed", "incomplete", "failed", "cancelled"]


class AdmitRequest(StrictRequest):
    content: str = Field(min_length=1, max_length=262_144)
    client_request_id: UUID4


class RequestView(StrictRequest):
    request_id: str
    session_id: str
    status: RequestStatus
    created_at: str
    completed_at: str | None
    error_message: str | None


class RequestEventRecord(RuntimeEvent):
    event_id: str
    created_at: str


class RequestEventPage(StrictRequest):
    events: list[RequestEventRecord] = Field(max_length=256)
    next_cursor: str | None
    has_more: bool
    status: RequestStatus
