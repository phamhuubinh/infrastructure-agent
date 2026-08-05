from __future__ import annotations

from src.pipeline.answer_type import AnswerType
from src.pipeline.intent_resolver import IntentResolver
from src.pipeline.normalizer import Normalizer
from src.pipeline.request_frame import RequestFrame


def test_normalizer_builds_one_canonical_request_frame() -> None:
    frame = Normalizer().normalize("Kiem tra CPU on server01 trong 1 giờ")

    assert isinstance(frame, RequestFrame)
    assert frame.raw_request == "Kiem tra CPU on server01 trong 1 giờ"
    assert frame.concepts == ("cpu",)
    assert frame.operation == "inspect"
    assert frame.target_raw == "server01"
    assert frame.parameters is not None
    assert frame.timeframe == "1h"
    assert frame.answer_type is AnswerType.FACT


def test_intent_resolver_enriches_instead_of_rebuilding_frame() -> None:
    original = Normalizer().normalize("check RAM")
    request = IntentResolver().resolve(original)

    assert request.request_frame is request.semantic_request
    assert request.request_frame is not None
    assert request.request_frame.raw_request == original.raw_request
    assert request.request_frame.concepts == original.concepts
    assert request.request_frame.parameters is original.parameters
    assert request.request_frame.intent_candidates


def test_request_frame_trace_serialization_is_canonical() -> None:
    frame = Normalizer().normalize("chek network status")
    serialized = frame.to_dict()

    assert serialized["concepts"] == ["network"]
    assert serialized["operation"] == "inspect"
    assert serialized["answer_type"] == "FACT"
    assert serialized["concept_candidates"]
