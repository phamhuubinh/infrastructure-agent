"""Deterministic clarification and unsupported-request responses."""

from __future__ import annotations

from src.model.protocol.prompt_builder_v2 import _detect_language
from src.pipeline.routing_decision import RoutingDecision, RoutingStatus


class ClarificationResponder:
    """Render bounded questions for the exact unresolved request field."""

    _TEMPLATES = {
        "target": "Bạn muốn kiểm tra target nào?",
        "service": "Bạn muốn kiểm tra service nào?",
        "path": "Bạn muốn kiểm tra đường dẫn filesystem nào?",
        "timeframe": "Bạn muốn dùng khoảng thời gian nào?",
        "concept": "Bạn muốn kiểm tra khía cạnh nào của hạ tầng?",
        "operation": "Bạn muốn xem số liệu, so sánh hay chẩn đoán?",
    }

    # GA2-B06: refusals preserve the request language when confidently
    # detectable.  Each pair is equivalent content; the detector picks the
    # matching language instead of leaking mixed scripts.
    _SENSITIVE_REFUSAL_VI = (
        "Tôi không thể tiết lộ hướng dẫn nội bộ, bí mật, thông tin "
        "đăng nhập hoặc tệp chứa thông tin xác thực."
    )
    _SENSITIVE_REFUSAL_EN = (
        "I cannot disclose hidden instructions, secrets, credentials, "
        "or credential files."
    )
    _READ_ONLY_REFUSAL_VI = (
        "Orion hiện chỉ điều tra read-only và không thực hiện thay đổi hệ "
        "thống. Hãy yêu cầu kiểm tra trạng thái hoặc số liệu cần xác minh."
    )
    _READ_ONLY_REFUSAL_EN = (
        "Orion is read-only and does not execute changes to the system. "
        "Please ask for a status check or verifiable metric instead."
    )

    def respond(self, decision: RoutingDecision) -> str:
        if decision.status is RoutingStatus.UNSUPPORTED:
            language = _detect_language(decision.request_frame.raw_request)
            if (decision.reason or "").startswith("sensitive:"):
                return (
                    self._SENSITIVE_REFUSAL_EN
                    if language == "en"
                    else self._SENSITIVE_REFUSAL_VI
                )
            return (
                self._READ_ONLY_REFUSAL_EN
                if language == "en"
                else self._READ_ONLY_REFUSAL_VI
            )

        field = decision.missing_field or "concept"
        prompt = self._TEMPLATES.get(field, self._TEMPLATES["concept"])
        candidates = tuple(dict.fromkeys(decision.candidates))[:3]
        if candidates:
            return f"{prompt} Các lựa chọn gần nhất: {', '.join(candidates)}."
        if decision.reason and field not in self._TEMPLATES:
            return f"{prompt} ({decision.reason})"
        return prompt
