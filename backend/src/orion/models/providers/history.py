"""Validate current native tool exchanges before protocol-specific serialization."""

from collections.abc import Callable

from orion.contracts import ContextMessage
from orion.models.backend import ModelBackendError, ModelBackendErrorKind


def validate_native_exchange(
    messages: tuple[ContextMessage, ...],
    native_keys: set[str],
    native_call_ids: set[str],
    message_key: Callable[[ContextMessage], str],
) -> None:
    pending: set[str] = set()
    seen: set[str] = set()
    for message in messages:
        call_id = message.tool_call_id
        if message.role == "tool" and call_id is not None and call_id in native_call_ids:
            if call_id not in pending:
                raise _invalid_exchange()
            pending.remove(call_id)
            continue
        if pending:
            raise _invalid_exchange()
        if message.role == "assistant" and message_key(message) in native_keys:
            for call in message.tool_calls:
                if call.call_id in seen:
                    raise _invalid_exchange()
                pending.add(call.call_id)
                seen.add(call.call_id)
    if pending:
        raise _invalid_exchange()


def _invalid_exchange() -> ModelBackendError:
    return ModelBackendError(
        "Native model history contains an incomplete or mismatched tool exchange.",
        kind=ModelBackendErrorKind.PROTOCOL,
    )
