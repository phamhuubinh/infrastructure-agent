import pytest
from pydantic import ValidationError

from orion.contracts import ProviderContinuation
from orion.contracts.events import RuntimeEvent


@pytest.mark.parametrize(
    "payload", [object(), ProviderContinuation(adapter_id="fixture", payload="private")]
)
def test_public_event_rejects_sdk_objects_and_private_envelopes(payload):
    with pytest.raises(ValidationError):
        RuntimeEvent(type="assistant.message", payload={"native": payload})


def test_event_namespace_rejects_private_vendor_events():
    with pytest.raises(ValidationError):
        RuntimeEvent(type="provider.reasoning.delta", payload={"content": "private"})


def test_json_event_retains_untrusted_text_as_data():
    event = RuntimeEvent(
        type="assistant.delta", payload={"content": "Unicode 秘", "nested": [None, 1, True]}
    )
    assert event.model_dump() == {
        "type": "assistant.delta",
        "payload": {"content": "Unicode 秘", "nested": [None, 1, True]},
    }
