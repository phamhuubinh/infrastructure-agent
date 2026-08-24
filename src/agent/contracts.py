"""Canonical model/harness contracts for Orion Agent Runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

PROTOCOL_VERSION = 3

MAX_TEXT_CHARS = 8192
MAX_REFERENCE_CHARS = 256
MAX_CAPABILITY_ID_CHARS = 128
MAX_JSON_DEPTH = 16
MAX_JSON_ITEMS = 2048
MAX_JSON_STRING_CHARS = 32768

_FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "cmd",
        "command",
        "credential",
        "credentials",
        "password",
        "private_key",
        "secret",
        "shell",
        "token",
    }
)


class ContractError(ValueError):
    """Canonical agent contract is invalid."""


class DecisionKind(str, Enum):
    FINAL = "final"
    DISCOVER = "discover"
    ACTION = "action"
    CLARIFY = "clarify"
    REFUSE = "refuse"


class FinalClaimKind(str, Enum):
    OBSERVATION = "observation"
    DETERMINISTIC_RESULT = "deterministic_result"


class ObservationStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


def _require_text(
    value: object,
    field_name: str,
    *,
    max_chars: int,
    nullable: bool = False,
) -> str | None:
    if value is None and nullable:
        return None

    if not isinstance(value, str) or not value.strip():
        suffix = " or null" if nullable else ""
        raise ContractError(f"{field_name} must be a non-empty string{suffix}.")

    if len(value) > max_chars:
        raise ContractError(f"{field_name} exceeds maximum length of {max_chars}.")

    return value


def _require_non_null_text(
    value: object,
    field_name: str,
    *,
    max_chars: int,
) -> str:
    result = _require_text(value, field_name, max_chars=max_chars)
    if result is None:
        raise ContractError(f"{field_name} must be a non-empty string.")
    return result


def _exact_object(
    value: object,
    expected_keys: set[str],
    name: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object.")

    keys = set(value)

    if keys != expected_keys:
        missing = sorted(expected_keys - keys)
        unexpected = sorted(keys - expected_keys)
        detail: list[str] = []

        if missing:
            detail.append(f"missing={missing}")
        if unexpected:
            detail.append(f"unexpected={unexpected}")

        raise ContractError(
            f"{name} fields do not match contract: " + ", ".join(detail)
        )

    return dict(value)


def _normalize_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _freeze_json(
    value: object,
    *,
    depth: int = 0,
    reject_sensitive_keys: bool = False,
) -> object:
    if depth > MAX_JSON_DEPTH:
        raise ContractError("JSON value exceeds maximum nesting depth.")

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) > MAX_JSON_STRING_CHARS:
            raise ContractError("JSON string exceeds maximum length.")
        return value

    if isinstance(value, Mapping):
        if len(value) > MAX_JSON_ITEMS:
            raise ContractError("JSON object exceeds maximum item count.")

        result: dict[str, object] = {}

        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ContractError("JSON object keys must be non-empty strings.")

            if (
                reject_sensitive_keys
                and _normalize_key(key) in _FORBIDDEN_ARGUMENT_KEYS
            ):
                raise ContractError(
                    f"Action arguments must not contain forbidden key: {key!r}."
                )

            result[key] = _freeze_json(
                item,
                depth=depth + 1,
                reject_sensitive_keys=reject_sensitive_keys,
            )

        return MappingProxyType(result)

    if isinstance(value, (list, tuple)):
        if len(value) > MAX_JSON_ITEMS:
            raise ContractError("JSON array exceeds maximum item count.")

        return tuple(
            _freeze_json(
                item,
                depth=depth + 1,
                reject_sensitive_keys=reject_sensitive_keys,
            )
            for item in value
        )

    raise ContractError("Contract values must contain JSON-compatible data only.")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]

    return value


@dataclass(frozen=True, slots=True)
class AgentAction:
    capability_id: str
    target_ref: str | None = None
    source_ref: str | None = None
    arguments: Mapping[str, object] = field(default_factory=dict)
    activity_text: str | None = None

    def __post_init__(self) -> None:
        _require_text(
            self.capability_id,
            "action.capability_id",
            max_chars=MAX_CAPABILITY_ID_CHARS,
        )
        _require_text(
            self.target_ref,
            "action.target_ref",
            max_chars=MAX_REFERENCE_CHARS,
            nullable=True,
        )
        _require_text(
            self.source_ref,
            "action.source_ref",
            max_chars=MAX_REFERENCE_CHARS,
            nullable=True,
        )
        _require_text(
            self.activity_text,
            "action.activity_text",
            max_chars=MAX_TEXT_CHARS,
            nullable=True,
        )

        if not isinstance(self.arguments, Mapping):
            raise ContractError("action.arguments must be an object.")

        frozen = _freeze_json(
            self.arguments,
            reject_sensitive_keys=True,
        )
        object.__setattr__(self, "arguments", frozen)

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "capability_id": self.capability_id,
            "arguments": _thaw_json(self.arguments),
        }
        if self.target_ref is not None:
            wire["target_ref"] = self.target_ref
        if self.source_ref is not None:
            wire["source_ref"] = self.source_ref
        if self.activity_text is not None:
            wire["activity_text"] = self.activity_text
        return wire

    @classmethod
    def from_wire(cls, value: object) -> AgentAction:
        if not isinstance(value, Mapping):
            raise ContractError("action must be an object.")
        data = dict(value)
        allowed = {
            "capability_id",
            "target_ref",
            "source_ref",
            "arguments",
            "activity_text",
        }
        if set(data) - allowed or not {"capability_id", "arguments"} <= set(data):
            raise ContractError("action fields do not match contract.")

        return cls(
            capability_id=_require_non_null_text(
                data["capability_id"],
                "action.capability_id",
                max_chars=MAX_CAPABILITY_ID_CHARS,
            ),
            target_ref=_require_text(
                data.get("target_ref"),
                "action.target_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            source_ref=_require_text(
                data.get("source_ref"),
                "action.source_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            arguments=_require_mapping(
                data["arguments"],
                "action.arguments",
            ),
            activity_text=_require_text(
                data.get("activity_text"),
                "action.activity_text",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class FinalClaim:
    """One bounded objective assertion a FINAL derives from evidence.

    Answer prose is model-owned language.  These references make the
    execution/status/identity portion deterministic without attempting to
    interpret that prose in a post-router.
    """

    kind: FinalClaimKind
    action_id: int
    capability_id: str
    target_ref: str | None = None
    source_ref: str | None = None
    require_fresh: bool = False
    result: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FinalClaimKind):
            raise ContractError("final claim kind is invalid.")
        if type(self.action_id) is not int or self.action_id < 1:
            raise ContractError("final claim action_id must be positive.")
        _require_text(
            self.capability_id,
            "final claim capability_id",
            max_chars=MAX_CAPABILITY_ID_CHARS,
        )
        _require_text(
            self.target_ref,
            "final claim target_ref",
            max_chars=MAX_REFERENCE_CHARS,
            nullable=True,
        )
        _require_text(
            self.source_ref,
            "final claim source_ref",
            max_chars=MAX_REFERENCE_CHARS,
            nullable=True,
        )
        if not isinstance(self.require_fresh, bool):
            raise ContractError("final claim require_fresh must be boolean.")
        if self.kind is FinalClaimKind.OBSERVATION:
            if self.result is not None:
                raise ContractError("observation final claims must not contain result.")
        elif not isinstance(self.result, Mapping) or not self.result:
            raise ContractError(
                "deterministic_result final claims require a non-empty result object."
            )
        if self.result is not None:
            frozen_result = _freeze_json(self.result)
            if not isinstance(frozen_result, Mapping):
                raise ContractError("final claim result must be an object.")
            object.__setattr__(self, "result", frozen_result)

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "kind": self.kind.value,
            "action_id": self.action_id,
            "capability_id": self.capability_id,
        }
        if self.target_ref is not None:
            wire["target_ref"] = self.target_ref
        if self.source_ref is not None:
            wire["source_ref"] = self.source_ref
        if self.require_fresh:
            wire["require_fresh"] = True
        if self.result is not None:
            wire["result"] = _thaw_json(self.result)
        return wire

    @classmethod
    def from_wire(cls, value: object) -> FinalClaim:
        if not isinstance(value, Mapping):
            raise ContractError("final claim must be an object.")
        data = dict(value)
        allowed = {
            "kind", "action_id", "capability_id", "target_ref", "source_ref",
            "require_fresh", "result",
        }
        if set(data) - allowed or not {"kind", "action_id", "capability_id"} <= set(data):
            raise ContractError("final claim fields do not match contract.")
        try:
            kind = FinalClaimKind(data["kind"])
        except (TypeError, ValueError) as exc:
            raise ContractError("final claim kind is invalid.") from exc
        action_id = data["action_id"]
        if type(action_id) is not int or action_id < 1:
            raise ContractError("final claim action_id must be positive.")
        require_fresh = data.get("require_fresh", False)
        if not isinstance(require_fresh, bool):
            raise ContractError("final claim require_fresh must be boolean.")
        result = data.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise ContractError("final claim result must be an object or null.")
        return cls(
            kind=kind,
            action_id=action_id,
            capability_id=_require_non_null_text(
                data["capability_id"],
                "final claim capability_id",
                max_chars=MAX_CAPABILITY_ID_CHARS,
            ),
            target_ref=_require_text(
                data.get("target_ref"),
                "final claim target_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            source_ref=_require_text(
                data.get("source_ref"),
                "final claim source_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            require_fresh=require_fresh,
            result=dict(result) if result is not None else None,
        )


@dataclass(frozen=True, slots=True)
class AgentDecision:
    kind: DecisionKind
    # Retained only as a non-wire convenience for in-process callers. The v3
    # canonical model contract never requests or accepts this field.
    goal: str | None = field(default=None, compare=False)
    category: str | None = None
    action: AgentAction | None = None
    answer: str | None = None
    question: str | None = None
    reason: str | None = None
    claims: tuple[FinalClaim, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DecisionKind):
            raise ContractError("decision.kind must be DecisionKind.")

        bodies = {
            DecisionKind.FINAL: ("answer", self.answer),
            DecisionKind.DISCOVER: ("category", self.category),
            DecisionKind.ACTION: ("action", self.action),
            DecisionKind.CLARIFY: ("question", self.question),
            DecisionKind.REFUSE: ("reason", self.reason),
        }

        required_field, required_value = bodies[self.kind]

        if required_value is None:
            raise ContractError(
                f"{self.kind.value} decision requires {required_field}."
            )

        for kind, (_field_name, value) in bodies.items():
            if kind is self.kind:
                continue
            if value is not None:
                raise ContractError(
                    f"{self.kind.value} decision must contain exactly {required_field}."
                )

        if self.kind is DecisionKind.ACTION:
            if not isinstance(self.action, AgentAction):
                raise ContractError("action decision requires AgentAction.")
        else:
            value = getattr(self, required_field)
            _require_text(
                value,
                f"decision.{required_field}",
                max_chars=MAX_TEXT_CHARS,
            )
        if not isinstance(self.claims, tuple) or any(
            not isinstance(claim, FinalClaim) for claim in self.claims
        ):
            raise ContractError("decision.claims must be FinalClaim values.")
        if self.kind is not DecisionKind.FINAL and self.claims:
            raise ContractError("Only FINAL decisions may contain claims.")

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "version": PROTOCOL_VERSION,
            "kind": self.kind.value,
        }
        if self.kind is DecisionKind.FINAL:
            wire["answer"] = self.answer
            if self.claims:
                wire["claims"] = [claim.to_wire() for claim in self.claims]
        elif self.kind is DecisionKind.DISCOVER:
            wire["category"] = self.category
        elif self.kind is DecisionKind.ACTION:
            wire["action"] = self.action.to_wire() if self.action is not None else None
        elif self.kind is DecisionKind.CLARIFY:
            wire["question"] = self.question
        else:
            wire["reason"] = self.reason
        return wire

    @classmethod
    def from_wire(cls, value: object) -> AgentDecision:
        if not isinstance(value, Mapping):
            raise ContractError("decision must be an object.")
        data = dict(value)

        if data.get("version") != PROTOCOL_VERSION:
            raise ContractError(
                f"Unsupported protocol version: {data.get('version')!r}."
            )

        kind_value = data["kind"]
        if not isinstance(kind_value, str):
            raise ContractError("decision.kind must be a string.")

        try:
            kind = DecisionKind(kind_value)
        except ValueError as exc:
            raise ContractError(
                "decision.kind contains an unknown enum value."
            ) from exc

        required_by_kind = {
            DecisionKind.FINAL: {"version", "kind", "answer"},
            DecisionKind.DISCOVER: {"version", "kind", "category"},
            DecisionKind.ACTION: {"version", "kind", "action"},
            DecisionKind.CLARIFY: {"version", "kind", "question"},
            DecisionKind.REFUSE: {"version", "kind", "reason"},
        }
        allowed = set(required_by_kind[kind])
        if kind is DecisionKind.FINAL:
            allowed.add("claims")
        if not required_by_kind[kind] <= set(data) or set(data) - allowed:
            raise ContractError("decision fields do not match contract.")

        action_value = data.get("action")
        action = None if action_value is None else AgentAction.from_wire(action_value)
        claims_value = data.get("claims", [])
        if not isinstance(claims_value, list):
            raise ContractError("decision.claims must be an array.")

        return cls(
            kind=kind,
            category=_require_text(
                data.get("category"),
                "decision.category",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            action=action,
            answer=_require_text(
                data.get("answer"),
                "decision.answer",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            question=_require_text(
                data.get("question"),
                "decision.question",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            reason=_require_text(
                data.get("reason"),
                "decision.reason",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            claims=tuple(FinalClaim.from_wire(value) for value in claims_value),
        )


@dataclass(frozen=True, slots=True)
class AgentObservation:
    action_id: int
    capability_id: str
    status: ObservationStatus
    facts: tuple[Mapping[str, object], ...] = ()
    summary: str | None = None
    target_ref: str | None = None
    source_ref: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)
    reason: str | None = None
    recoverable: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.action_id, int)
            or isinstance(self.action_id, bool)
            or self.action_id < 1
        ):
            raise ContractError("observation.action_id must be a positive integer.")

        _require_text(
            self.capability_id,
            "observation.capability_id",
            max_chars=MAX_CAPABILITY_ID_CHARS,
        )

        if not isinstance(self.status, ObservationStatus):
            raise ContractError("observation.status must be ObservationStatus.")

        _require_text(
            self.summary,
            "observation.summary",
            max_chars=MAX_TEXT_CHARS,
            nullable=True,
        )
        _require_text(
            self.target_ref,
            "observation.target_ref",
            max_chars=MAX_REFERENCE_CHARS,
            nullable=True,
        )
        _require_text(
            self.source_ref,
            "observation.source_ref",
            max_chars=MAX_REFERENCE_CHARS,
            nullable=True,
        )
        _require_text(
            self.reason,
            "observation.reason",
            max_chars=MAX_TEXT_CHARS,
            nullable=True,
        )

        if not isinstance(self.recoverable, bool):
            raise ContractError("observation.recoverable must be boolean.")

        if not isinstance(self.facts, tuple):
            raise ContractError("observation.facts must be a tuple.")

        frozen_facts: list[Mapping[str, object]] = []

        for fact in self.facts:
            if not isinstance(fact, Mapping):
                raise ContractError("Each observation fact must be an object.")

            frozen = _freeze_json(fact)
            if not isinstance(frozen, Mapping):
                raise ContractError("Each observation fact must be an object.")

            frozen_facts.append(frozen)

        if not isinstance(self.provenance, Mapping):
            raise ContractError("observation.provenance must be an object.")

        frozen_provenance = _freeze_json(self.provenance)
        if not isinstance(frozen_provenance, Mapping):
            raise ContractError("observation.provenance must be an object.")

        object.__setattr__(
            self,
            "facts",
            tuple(frozen_facts),
        )
        object.__setattr__(
            self,
            "provenance",
            frozen_provenance,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "capability_id": self.capability_id,
            "status": self.status.value,
            "target_ref": self.target_ref,
            "source_ref": self.source_ref,
            "summary": self.summary,
            "facts": [_thaw_json(fact) for fact in self.facts],
            "provenance": _thaw_json(self.provenance),
            "reason": self.reason,
            "recoverable": self.recoverable,
        }

    @classmethod
    def from_wire(cls, value: object) -> AgentObservation:
        data = _exact_object(
            value,
            {
                "action_id",
                "capability_id",
                "status",
                "target_ref",
                "source_ref",
                "summary",
                "facts",
                "provenance",
                "reason",
                "recoverable",
            },
            "observation",
        )

        action_id = data["action_id"]
        if (
            not isinstance(action_id, int)
            or isinstance(action_id, bool)
            or action_id < 1
        ):
            raise ContractError("observation.action_id must be a positive integer.")

        status_value = data["status"]
        if not isinstance(status_value, str):
            raise ContractError("observation.status must be a string.")

        try:
            status = ObservationStatus(status_value)
        except ValueError as exc:
            raise ContractError(
                "observation.status contains an unknown enum value."
            ) from exc

        facts_value = data["facts"]
        if not isinstance(facts_value, (list, tuple)):
            raise ContractError("observation.facts must be an array.")

        facts: list[Mapping[str, object]] = []
        for fact in facts_value:
            if not isinstance(fact, Mapping):
                raise ContractError("Each observation fact must be an object.")
            facts.append(dict(fact))

        recoverable = data["recoverable"]
        if not isinstance(recoverable, bool):
            raise ContractError("observation.recoverable must be boolean.")

        return cls(
            action_id=action_id,
            capability_id=_require_non_null_text(
                data["capability_id"],
                "observation.capability_id",
                max_chars=MAX_CAPABILITY_ID_CHARS,
            ),
            status=status,
            target_ref=_require_text(
                data["target_ref"],
                "observation.target_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            source_ref=_require_text(
                data["source_ref"],
                "observation.source_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            summary=_require_text(
                data["summary"],
                "observation.summary",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            facts=tuple(facts),
            provenance=_require_mapping(
                data["provenance"],
                "observation.provenance",
            ),
            reason=_require_text(
                data["reason"],
                "observation.reason",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            recoverable=recoverable,
        )


def _require_mapping(
    value: object,
    field_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field_name} must be an object.")
    return dict(value)


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ContractError(f"Duplicate JSON field: {key!r}.")
        result[key] = value

    return result


def decision_to_json(decision: AgentDecision) -> str:
    if not isinstance(decision, AgentDecision):
        raise TypeError("decision must be AgentDecision.")

    return json.dumps(
        decision.to_wire(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def decision_from_json(value: str | bytes) -> AgentDecision:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("Decision bytes must be UTF-8.") from exc

    if not isinstance(value, str):
        raise ContractError("Decision payload must be JSON text.")

    try:
        decoded = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractError("Decision payload is not valid JSON.") from exc

    return AgentDecision.from_wire(decoded)
