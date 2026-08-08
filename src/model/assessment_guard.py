"""EPIC 7 wiring: run all assessment output guards in a fixed, fail-closed order.

Order matters:
1. Action hallucination guard (DR1-704) — if the model claims it performed a
   mutation, that is the most dangerous failure mode, so it short-circuits
   everything else with a safe refusal.
2. Claim grounding (DR1-703) — redact numeric/target claims not traceable to
   a fact or finding the model was given.
3. Numeric consistency scope note (DR1-705) — surface (not silently fix)
   arithmetic contradictions between the facts collected.
4. Language quality (DR1-706) — strip unexpected script leakage.
"""

from __future__ import annotations

from src.model.action_receipt import ActionReceipt, guard_action_claims
from src.model.claim_validator import (
    ClaimValidator,
    redact_ungrounded_claims,
    redact_ungrounded_external_claims,
)
from src.model.numeric_claim_validator import validate_numeric_consistency
from src.model.output_sanitizer import enforce_language_quality
from src.model.protocol.prompt_builder_v2 import _detect_language
from src.pipeline.assessment_request import AssessmentRequest

_NUMERIC_SCOPE_NOTE_VI = (
    "\n\n_Lưu ý: dữ liệu thu thập được có mâu thuẫn số liệu ở một số chỉ số; "
    "hãy kiểm tra lại thủ công trước khi kết luận._"
)
_NUMERIC_SCOPE_NOTE_EN = (
    "\n\n_Note: the collected evidence has a numeric contradiction on some "
    "metrics; verify manually before concluding._"
)


def apply_assessment_guards(
    response_text: str,
    assessment_request: AssessmentRequest,
    *,
    action_receipts: tuple[ActionReceipt, ...] = (),
    enable_claim_guard: bool = True,
) -> str:
    """Apply the EPIC 7 output guards to a raw assessment response.

    ``enable_claim_guard`` rolls back evidence-grounding, numeric, and
    language validators as one temporary rollout unit.  The action-claim
    guard remains mandatory: a rollout switch must never weaken Orion's
    read-only safety boundary.
    """

    lang = _detect_language(assessment_request.raw_request)

    guarded = guard_action_claims(response_text, action_receipts, lang=lang)
    if guarded != response_text:
        # Action claim was rejected outright — nothing else to check, the
        # rest of the response is discarded along with the false claim.
        return guarded

    if not enable_claim_guard:
        return guarded

    guarded = redact_ungrounded_claims(guarded, assessment_request, lang=lang)
    guarded = redact_ungrounded_external_claims(
        guarded,
        assessment_request,
        lang=lang,
    )

    if validate_numeric_consistency(assessment_request.facts):
        note = _NUMERIC_SCOPE_NOTE_VI if lang == "vi" else _NUMERIC_SCOPE_NOTE_EN
        if note.strip() not in guarded:
            guarded = guarded + note

    guarded = enforce_language_quality(guarded, lang)

    return guarded


__all__ = ["apply_assessment_guards", "ClaimValidator"]
