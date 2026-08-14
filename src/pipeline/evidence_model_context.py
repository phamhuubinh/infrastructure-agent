"""Bounded, credential-safe evidence serialization for model consumption.

The assessment model receives canonical observations and compact status data,
not collector payloads.  Raw evidence is an explicit, separately-budgeted
compatibility path for providers that do not yet emit canonical facts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from src.pipeline.fact import Fact, thaw
from src.shared.execution.command_result import redact_sensitive

if TYPE_CHECKING:
    from src.pipeline.assessment_request import AssessmentRequest
    from src.pipeline.evidence_package import EvidencePackage


@dataclass(frozen=True, slots=True)
class EvidenceModelContextBudget:
    """Hard item and byte limits for one assessment-model evidence context."""

    max_bytes: int = 8_192
    max_packages: int = 12
    max_facts: int = 24
    max_failures: int = 8
    max_missing: int = 20
    max_raw_packages: int = 2
    max_raw_items: int = 5
    max_text_chars: int = 300
    allow_raw: bool = True

    def __post_init__(self) -> None:
        positive = (
            self.max_bytes,
            self.max_packages,
            self.max_facts,
            self.max_failures,
            self.max_missing,
            self.max_raw_items,
            self.max_text_chars,
        )
        if (
            any(value < 1 for value in positive)
            or self.max_bytes < 512
            or self.max_raw_packages < 0
        ):
            raise ValueError("Evidence model-context limits must be positive.")


class EvidenceModelContextSerializer:
    """Serialize only the evidence facts needed at the model boundary."""

    def __init__(self, budget: EvidenceModelContextBudget | None = None) -> None:
        self._budget = budget or EvidenceModelContextBudget()

    def serialize(self, request: AssessmentRequest) -> dict[str, object]:
        from src.pipeline.assessment_request import AssessmentRequest

        if not isinstance(request, AssessmentRequest):
            raise TypeError("request must be an AssessmentRequest.")

        facts = _deduplicated_facts(request)
        ordered_facts = sorted(
            facts,
            key=lambda fact: (
                0 if fact.validity.value == "contradictory" else 1,
                0 if fact.usable else 1,
                fact.metric,
                fact.target,
                fact.source,
                fact.id,
            ),
        )
        missing = _bounded_safe_strings(
            (*request.unknowns, *request.missing_evidence),
            self._budget.max_missing,
            self._budget.max_text_chars,
        )
        failures = _bounded_safe_strings(
            request.collection_failures,
            self._budget.max_failures,
            self._budget.max_text_chars,
        )
        context: dict[str, object] = {
            "evidence_status": request.evidence_status or "UNSPECIFIED",
            "evidence_complete": bool(request.evidence_complete),
            "missing": missing,
            "failures": failures,
            "facts": [],
            "packages": [],
            "omitted": {
                "facts": max(len(ordered_facts) - self._budget.max_facts, 0),
                "packages": max(
                    len(request.evidence) - self._budget.max_packages,
                    0,
                ),
                "missing": max(
                    len(tuple(dict.fromkeys((*request.unknowns, *request.missing_evidence))))
                    - len(missing),
                    0,
                ),
                "failures": max(len(request.collection_failures) - len(failures), 0),
                "raw_packages": 0,
            },
        }
        _shrink_base_context(context, self._budget.max_bytes)

        for fact in ordered_facts[: self._budget.max_facts]:
            candidate = _compact_fact(fact)
            if not self._append_within_budget(context, "facts", candidate):
                _increment_omitted(context, "facts")

        raw_count = 0
        for package in request.evidence[: self._budget.max_packages]:
            candidate = _compact_package(package, self._budget.max_text_chars)
            if (
                self._budget.allow_raw
                and request.raw_evidence_required
                and raw_count < self._budget.max_raw_packages
                and package.valid_for_requirements
                and not package.facts
                and package.data not in (None, {}, [], (), "")
            ):
                candidate["raw"] = _safe_raw(
                    package.data,
                    item_limit=self._budget.max_raw_items,
                    text_limit=self._budget.max_text_chars,
                )
                raw_count += 1
            if not self._append_within_budget(context, "packages", candidate):
                if candidate.pop("raw", None) is not None:
                    raw_count -= 1
                if not self._append_within_budget(context, "packages", candidate):
                    _increment_omitted(context, "packages")
                else:
                    _increment_omitted(context, "raw_packages")

        omitted_raw = sum(
            1
            for package in request.evidence
            if package.valid_for_requirements
            and not package.facts
            and package.data not in (None, {}, [], (), "")
        ) - raw_count
        if omitted_raw > 0:
            omitted = context["omitted"]
            assert isinstance(omitted, dict)
            omitted["raw_packages"] = max(
                int(omitted["raw_packages"]), omitted_raw
            )
        return context

    def to_json(self, request: AssessmentRequest) -> str:
        """Return stable compact JSON within ``max_bytes``."""

        return _compact_json(self.serialize(request))

    def _append_within_budget(
        self,
        context: dict[str, object],
        field: str,
        candidate: dict[str, object],
    ) -> bool:
        values = context[field]
        assert isinstance(values, list)
        values.append(candidate)
        if len(_compact_json(context).encode("utf-8")) <= self._budget.max_bytes:
            return True
        values.pop()
        return False


def _deduplicated_facts(request: AssessmentRequest) -> tuple[Fact, ...]:
    by_id: dict[str, Fact] = {}
    for fact in (
        *request.facts,
        *(fact for package in request.evidence for fact in package.facts),
    ):
        by_id.setdefault(fact.id, fact)
    return tuple(by_id.values())


def _compact_fact(fact: Fact) -> dict[str, object]:
    provenance = fact.provenance
    value = fact.value
    if value is None and "observed_value" in fact.dimensions:
        value = fact.dimensions["observed_value"]
    return {
        "id": fact.id,
        "metric": fact.metric,
        "value": _safe_raw(thaw(value), item_limit=5, text_limit=300),
        "unit": fact.unit,
        "observed_at": fact.observed_at.isoformat(),
        "source": fact.source,
        "target": fact.target,
        "validity": fact.validity.value,
        "freshness": fact.freshness.value,
        "confidence": fact.confidence,
        "provenance": {
            "id": provenance.id,
            "source": provenance.source,
            "capability": provenance.capability,
            "target": provenance.target,
            "reference": provenance.source_reference,
        },
    }


def _compact_package(
    package: EvidencePackage,
    text_limit: int,
) -> dict[str, object]:
    failure_codes: list[str] = []
    if package.capability_error is not None:
        failure_codes.append(package.capability_error.code.value)
    return {
        "capability": redact_sensitive(package.capability_name)[:160],
        "evidence": redact_sensitive(package.evidence_name)[:160],
        "status": package.capability_status.value,
        "source": redact_sensitive(package.source or package.source_tool or "")[:80],
        "resource": redact_sensitive(package.resource or "")[:160],
        "stale": bool(package.stale),
        "failure_codes": failure_codes,
        "fact_ids": sorted(fact.id for fact in package.facts),
    }


def _bounded_safe_strings(
    values: tuple[str, ...] | list[str],
    limit: int,
    text_limit: int,
) -> list[str]:
    safe = {
        redact_sensitive(" ".join(str(value).split()))[:text_limit]
        for value in values
        if str(value).strip()
    }
    return sorted(safe)[:limit]


def _safe_raw(value: object, *, item_limit: int, text_limit: int) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        pairs = sorted(value.items(), key=lambda item: str(item[0]))
        for raw_key, original in pairs[:item_limit]:
            key = str(raw_key)
            if any(marker in key.casefold() for marker in _SECRET_KEYS):
                result[key] = "<redacted>"
            else:
                result[key] = _safe_raw(
                    original,
                    item_limit=item_limit,
                    text_limit=text_limit,
                )
        if len(value) > item_limit:
            result["_omitted_items"] = len(value) - item_limit
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        items = (
            sorted(value, key=repr)
            if isinstance(value, (set, frozenset))
            else list(value)
        )
        rendered = [
            _safe_raw(item, item_limit=item_limit, text_limit=text_limit)
            for item in items[:item_limit]
        ]
        if len(items) > item_limit:
            rendered.append({"_omitted_items": len(items) - item_limit})
        return rendered
    if isinstance(value, str):
        return redact_sensitive(value)[:text_limit]
    if isinstance(value, Enum):
        return _safe_raw(value.value, item_limit=item_limit, text_limit=text_limit)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_sensitive(str(value))[:text_limit]


def _increment_omitted(context: dict[str, object], field: str) -> None:
    omitted = context["omitted"]
    assert isinstance(omitted, dict)
    omitted[field] = int(omitted[field]) + 1


def _shrink_base_context(context: dict[str, object], max_bytes: int) -> None:
    for field in ("failures", "missing"):
        values = context[field]
        assert isinstance(values, list)
        while values and len(_compact_json(context).encode("utf-8")) > max_bytes:
            values.pop()
            _increment_omitted(context, field)


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_SECRET_KEYS = (
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
)


__all__ = [
    "EvidenceModelContextBudget",
    "EvidenceModelContextSerializer",
]
