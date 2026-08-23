from __future__ import annotations

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.pipeline.assessment_request import AssessmentRequest

MODEL_UNCONFIGURED_MESSAGE = (
    "Chưa cấu hình model. Hãy mở Cài đặt → Model hoặc dùng lệnh "
    "`orion model add` rồi chạy kiểm tra kết nối."
)
MODEL_UNCONFIGURED_MESSAGE_EN = (
    "No model is configured. Open Settings → Model or use `orion model add`, "
    "then run the connection test."
)


def model_unconfigured_message(raw_request: str) -> str:
    """Return the setup-mode message in the request language."""

    from src.shared.language import detect_language

    return (
        MODEL_UNCONFIGURED_MESSAGE_EN
        if detect_language(raw_request) == "en"
        else MODEL_UNCONFIGURED_MESSAGE
    )


class UnconfiguredAssessmentAdapter(AssessmentModelAdapter):
    """Keeps Orion operational before a user chooses a model."""

    def assess(self, assessment_request: AssessmentRequest) -> str:
        return MODEL_UNCONFIGURED_MESSAGE

    def assess_raw(self, prompt: str) -> str:
        return MODEL_UNCONFIGURED_MESSAGE

    def health_check(self, timeout: float = 5.0) -> bool:
        return False


__all__ = [
    "MODEL_UNCONFIGURED_MESSAGE",
    "MODEL_UNCONFIGURED_MESSAGE_EN",
    "UnconfiguredAssessmentAdapter",
    "model_unconfigured_message",
]
