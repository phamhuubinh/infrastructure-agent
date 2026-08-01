from __future__ import annotations

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.pipeline.assessment_request import AssessmentRequest

_MESSAGE = (
    "Chưa cấu hình model. Hãy mở Cài đặt → Model hoặc dùng lệnh "
    "`orion model add` rồi chạy kiểm tra kết nối."
)


class UnconfiguredAssessmentAdapter(AssessmentModelAdapter):
    """Keeps Orion operational before a user chooses a model."""

    def assess(self, assessment_request: AssessmentRequest) -> str:
        return _MESSAGE

    def assess_raw(self, prompt: str) -> str:
        return _MESSAGE

    def health_check(self, timeout: float = 5.0) -> bool:
        return False
