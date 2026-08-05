from __future__ import annotations

from src.pipeline.clarification_responder import ClarificationResponder
from src.pipeline.normalizer import Normalizer
from src.pipeline.routing_decision import RoutingDecision, RoutingStatus


def test_target_clarification_is_bounded_and_specific() -> None:
    decision = RoutingDecision(
        status=RoutingStatus.CLARIFICATION_REQUIRED,
        request_frame=Normalizer().normalize("check cpu on server0"),
        missing_field="target",
        candidates=("server01", "server02", "server03", "server04"),
    )

    response = ClarificationResponder().respond(decision)

    assert "target" in response
    assert "server01" in response
    assert "server03" in response
    assert "server04" not in response


def test_missing_service_uses_service_template() -> None:
    decision = RoutingDecision(
        status=RoutingStatus.CLARIFICATION_REQUIRED,
        request_frame=Normalizer().normalize("service kia bị lỗi"),
        missing_field="service",
    )

    assert "service nào" in ClarificationResponder().respond(decision)


def test_unsupported_action_is_read_only_refusal() -> None:
    decision = RoutingDecision(
        status=RoutingStatus.UNSUPPORTED,
        request_frame=Normalizer().normalize("restart nginx"),
    )

    response = ClarificationResponder().respond(decision)
    assert "read-only" in response
    assert "không thực hiện" in response
