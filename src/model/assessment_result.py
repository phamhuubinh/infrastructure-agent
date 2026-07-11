from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    """Typed output from assessment.

    Attributes:
        content: The assessment text from the model.
        success: True if assessment completed without error.
        model: The model name used for assessment.
        error: Error message if assessment failed.
        latency_ms: Time in milliseconds for the assessment call.
    """

    content: str = ""
    success: bool = True
    model: str = ""
    error: str | None = None
    latency_ms: float = 0.0
