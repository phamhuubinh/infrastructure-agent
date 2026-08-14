"""Deterministic postconditions for the final semantic-loop response."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from src.model.action_receipt import guard_action_claims
from src.pipeline.basic_calculator import CalculatorContractResult, format_value


class FinalResponseViolation(str, Enum):
    TARGET_MISMATCH = "target_mismatch"
    CURRENT_UNVERIFIED = "current_unverified"
    READ_ONLY_BOUNDARY = "read_only_boundary"
    CALCULATOR_MISMATCH = "calculator_mismatch"
    LANGUAGE_MISMATCH = "language_mismatch"
    SHAPE_MISMATCH = "shape_mismatch"
    PROVENANCE_NOT_USED = "provenance_not_used"
    SEMANTIC_NOT_ALIGNED = "semantic_not_aligned"


@dataclass(frozen=True, slots=True)
class FinalResponseConstraints:
    validated_target: str | None = None
    current_required: bool = False
    current_verified: bool = False
    read_only: bool = True
    calculator_result: CalculatorContractResult | None = None
    requested_language: str | None = None
    requested_shape: str | None = None
    used_provenance: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FinalResponseGuardResult:
    text: str
    violations: tuple[FinalResponseViolation, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.violations

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "violations": [item.value for item in self.violations],
        }


class FinalResponseGuard:
    """Check hard invariants without asking a model to judge its own output."""

    def validate(
        self,
        response: str,
        constraints: FinalResponseConstraints,
    ) -> FinalResponseGuardResult:
        if not isinstance(response, str) or not response.strip():
            raise ValueError("response must be non-empty text.")
        if not isinstance(constraints, FinalResponseConstraints):
            raise TypeError("constraints must be FinalResponseConstraints.")

        violations: list[FinalResponseViolation] = []
        language = constraints.requested_language or "en"
        lower = response.casefold()

        target = constraints.validated_target
        if target and target.casefold() not in {"localhost", "127.0.0.1", "::1"}:
            if re.search(r"\b(?:localhost|127\.0\.0\.1)\b", lower) or "::1" in lower:
                violations.append(FinalResponseViolation.TARGET_MISMATCH)
            claimed_targets = re.findall(
                r"\b(?:target|host|server|máy)\s*(?:=|:)\s*([a-z0-9_.-]+)",
                lower,
            )
            if any(claim != target.casefold() for claim in claimed_targets):
                violations.append(FinalResponseViolation.TARGET_MISMATCH)

        if constraints.current_required and not constraints.current_verified:
            unavailable_markers = (
                "unverified",
                "not verified",
                "unavailable",
                "cannot verify",
                "cannot be verified",
                "could not be verified",
                "unable to verify",
                "cannot be read",
                "không thể kiểm chứng",
                "chưa được kiểm chứng",
                "không có bằng chứng",
            )
            if not any(marker in lower for marker in unavailable_markers):
                violations.append(FinalResponseViolation.CURRENT_UNVERIFIED)

        if constraints.read_only:
            guarded = guard_action_claims(response, (), lang=language)
            if guarded != response:
                violations.append(FinalResponseViolation.READ_ONLY_BOUNDARY)

        calculation = constraints.calculator_result
        if calculation is not None and calculation.ok and calculation.value is not None:
            expected = calculation.value
            result_claim = _result_claim(response)
            if result_claim is not None and result_claim != expected:
                violations.append(FinalResponseViolation.CALCULATOR_MISMATCH)
            elif not _contains_decimal(response, expected):
                violations.append(FinalResponseViolation.CALCULATOR_MISMATCH)

        if constraints.requested_language in {"en", "vi"}:
            detected = _language(response)
            if detected is not None and detected != constraints.requested_language:
                violations.append(FinalResponseViolation.LANGUAGE_MISMATCH)

        if constraints.requested_shape == "SHORT" and (
            len(response) > 600 or response.count("\n") > 6
        ):
            violations.append(FinalResponseViolation.SHAPE_MISMATCH)

        allowed_urls = {_normalize_url(value) for value in constraints.used_provenance}
        cited_urls = {_normalize_url(value) for value in _URL.findall(response)}
        if cited_urls - allowed_urls:
            violations.append(FinalResponseViolation.PROVENANCE_NOT_USED)

        unique = tuple(dict.fromkeys(violations))
        if not unique:
            return FinalResponseGuardResult(response)
        return FinalResponseGuardResult(
            _fallback(constraints, unique, language),
            unique,
        )


def _result_claim(response: str) -> Decimal | None:
    match = re.search(
        r"(?:result|answer|kết\s+quả|đáp\s+án)\s*(?:is|là|=|:)?\s*"
        r"(-?\d+(?:[.,]\d+)?)",
        response,
        re.IGNORECASE,
    )
    if match is None:
        return None
    try:
        return Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None


def _contains_decimal(response: str, expected: Decimal) -> bool:
    for raw in re.findall(r"(?<![\w.])-?\d+(?:[.,]\d+)?(?![\w.])", response):
        try:
            if Decimal(raw.replace(",", ".")) == expected:
                return True
        except InvalidOperation:
            continue
    return False


def _language(response: str) -> str | None:
    if re.search(
        r"[àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
        r"ùúủũụưừứửữựỳýỷỹỵđ]",
        response,
        re.IGNORECASE,
    ):
        return "vi"
    if re.search(r"\b(?:the|this|is|are|result|cannot|verified|current)\b", response, re.IGNORECASE):
        return "en"
    return None


def _fallback(
    constraints: FinalResponseConstraints,
    violations: tuple[FinalResponseViolation, ...],
    language: str,
) -> str:
    if FinalResponseViolation.CALCULATOR_MISMATCH in violations:
        result = constraints.calculator_result
        assert result is not None and result.value is not None
        value = format_value(result.value)
        unit = f" {result.unit}" if result.unit else ""
        return f"Kết quả: {value}{unit}." if language == "vi" else f"Result: {value}{unit}."
    if FinalResponseViolation.CURRENT_UNVERIFIED in violations:
        return (
            "Không thể kiểm chứng thông tin hiện tại từ bằng chứng đã xác minh."
            if language == "vi"
            else "Current information could not be verified from collected evidence."
        )
    if FinalResponseViolation.READ_ONLY_BOUNDARY in violations:
        return (
            "Orion chỉ đọc; không có thay đổi hệ thống nào được thực hiện."
            if language == "vi"
            else "Orion is read-only; no system change was performed."
        )
    return (
        "Câu trả lời bị chặn vì không khớp bằng chứng đã xác thực."
        if language == "vi"
        else "The response was blocked because it did not match validated evidence."
    )


def _normalize_url(value: str) -> str:
    return value.rstrip(".,);]}")


_URL = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


__all__ = [
    "FinalResponseConstraints",
    "FinalResponseGuard",
    "FinalResponseGuardResult",
    "FinalResponseViolation",
]
