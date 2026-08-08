"""Deterministic clarification and unsupported-request responses."""

from __future__ import annotations

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

    def respond(self, decision: RoutingDecision) -> str:
        if decision.status is RoutingStatus.UNSUPPORTED:
            if (decision.reason or "").startswith("sensitive:"):
                return (
                    "Tôi không thể tiết lộ hướng dẫn nội bộ, bí mật, thông tin "
                    "đăng nhập hoặc tệp chứa thông tin xác thực."
                )
            return (
                "Orion hiện chỉ điều tra read-only và không thực hiện thay đổi hệ "
                "thống. Hãy yêu cầu kiểm tra trạng thái hoặc số liệu cần xác minh."
            )

        field = decision.missing_field or "concept"
        prompt = self._TEMPLATES.get(field, self._TEMPLATES["concept"])
        candidates = tuple(dict.fromkeys(decision.candidates))[:3]
        if candidates:
            return f"{prompt} Các lựa chọn gần nhất: {', '.join(candidates)}."
        if decision.reason and field not in self._TEMPLATES:
            return f"{prompt} ({decision.reason})"
        return prompt
