"""Canonical model/harness contracts for Orion Agent Runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

PROTOCOL_VERSION = 2

MAX_GOAL_CHARS = 1024
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
        raise ContractError(
            f"{field_name} must be a non-empty string{suffix}."
        )

    if len(value) > max_chars:
        raise ContractError(
            f"{field_name} exceeds maximum length of {max_chars}."
        )

    return value


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
            f"{name} fields do not match contract: "
            + ", ".join(detail)
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
                raise ContractError(
                    "JSON object keys must be non-empty strings."
                )

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

    raise ContractError(
        "Contract values must contain JSON-compatible data only."
    )


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _thaw_json(item)
            for key, item in value.items()
        }

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
        return {
            "capability_id": self.capability_id,
            "target_ref": self.target_ref,
            "source_ref": self.source_ref,
            "arguments": _thaw_json(self.arguments),
            "activity_text": self.activity_text,
        }

    @classmethod
    def from_wire(cls, value: object) -> AgentAction:
        data = _exact_object(
            value,
            {
                "capability_id",
                "target_ref",
                "source_ref",
                "arguments",
                "activity_text",
            },
            "action",
        )

        return cls(
            capability_id=_require_text(
                data["capability_id"],
                "action.capability_id",
                max_chars=MAX_CAPABILITY_ID_CHARS,
            ),
            target_ref=_require_text(
                data["target_ref"],
                "action.target_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            source_ref=_require_text(
                data["source_ref"],
                "action.source_ref",
                max_chars=MAX_REFERENCE_CHARS,
                nullable=True,
            ),
            arguments=_require_mapping(
                data["arguments"],
                "action.arguments",
            ),
            activity_text=_require_text(
                data["activity_text"],
                "action.activity_text",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class AgentDecision:
    kind: DecisionKind
    goal: str
    category: str | None = None
    action: AgentAction | None = None
    answer: str | None = None
    question: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DecisionKind):
            raise ContractError("decision.kind must be DecisionKind.")

        _require_text(
            self.goal,
            "decision.goal",
            max_chars=MAX_GOAL_CHARS,
        )

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

        for kind, (field_name, value) in bodies.items():
            if kind is self.kind:
                continue
            if value is not None:
                raise ContractError(
                    f"{self.kind.value} decision must contain exactly {required_field}."
                )

        if self.kind is DecisionKind.ACTION:
            if not isinstance(self.action, AgentAction):
                raise ContractError(
                    "action decision requires AgentAction."
                )
        else:
            value = getattr(self, required_field)
            _require_text(
                value,
                f"decision.{required_field}",
                max_chars=MAX_TEXT_CHARS,
            )

    def to_wire(self) -> dict[str, object]:
        return {
            "version": PROTOCOL_VERSION,
            "kind": self.kind.value,
            "goal": self.goal,
            "category": self.category,
            "action": (
                self.action.to_wire()
                if self.action is not None
                else None
            ),
            "answer": self.answer,
            "question": self.question,
            "reason": self.reason,
        }

    @classmethod
    def from_wire(cls, value: object) -> AgentDecision:
        data = _exact_object(
            value,
            {
                "version",
                "kind",
                "goal",
                "category",
                "action",
                "answer",
                "question",
                "reason",
            },
            "decision",
        )

        if data["version"] != PROTOCOL_VERSION:
            raise ContractError(
                f"Unsupported protocol version: {data['version']!r}."
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

        action_value = data["action"]
        action = (
            None
            if action_value is None
            else AgentAction.from_wire(action_value)
        )

        return cls(
            kind=kind,
            goal=_require_text(
                data["goal"],
                "decision.goal",
                max_chars=MAX_GOAL_CHARS,
            ),
            category=_require_text(
                data["category"],
                "decision.category",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            action=action,
            answer=_require_text(
                data["answer"],
                "decision.answer",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            question=_require_text(
                data["question"],
                "decision.question",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
            reason=_require_text(
                data["reason"],
                "decision.reason",
                max_chars=MAX_TEXT_CHARS,
                nullable=True,
            ),
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
            raise ContractError(
                "observation.action_id must be a positive integer."
            )

        _require_text(
            self.capability_id,
            "observation.capability_id",
            max_chars=MAX_CAPABILITY_ID_CHARS,
        )

        if not isinstance(self.status, ObservationStatus):
            raise ContractError(
                "observation.status must be ObservationStatus."
            )

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
            raise ContractError(
                "observation.recoverable must be boolean."
            )

        if not isinstance(self.facts, tuple):
            raise ContractError(
                "observation.facts must be a tuple."
            )

        frozen_facts: list[Mapping[str, object]] = []

        for fact in self.facts:
            if not isinstance(fact, Mapping):
                raise ContractError(
                    "Each observation fact must be an object."
                )

            frozen = _freeze_json(fact)
            if not isinstance(frozen, Mapping):
                raise ContractError(
                    "Each observation fact must be an object."
                )

            frozen_facts.append(frozen)

        if not isinstance(self.provenance, Mapping):
            raise ContractError(
                "observation.provenance must be an object."
            )

        frozen_provenance = _freeze_json(self.provenance)
        if not isinstance(frozen_provenance, Mapping):
            raise ContractError(
                "observation.provenance must be an object."
            )

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
            "facts": [
                _thaw_json(fact)
                for fact in self.facts
            ],
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
            raise ContractError(
                "observation.action_id must be a positive integer."
            )

        status_value = data["status"]
        if not isinstance(status_value, str):
            raise ContractError(
                "observation.status must be a string."
            )

        try:
            status = ObservationStatus(status_value)
        except ValueError as exc:
            raise ContractError(
                "observation.status contains an unknown enum value."
            ) from exc

        facts_value = data["facts"]
        if not isinstance(facts_value, (list, tuple)):
            raise ContractError(
                "observation.facts must be an array."
            )

        facts: list[Mapping[str, object]] = []
        for fact in facts_value:
            if not isinstance(fact, Mapping):
                raise ContractError(
                    "Each observation fact must be an object."
                )
            facts.append(dict(fact))

        recoverable = data["recoverable"]
        if not isinstance(recoverable, bool):
            raise ContractError(
                "observation.recoverable must be boolean."
            )

        return cls(
            action_id=action_id,
            capability_id=_require_text(
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
            raise ContractError(
                f"Duplicate JSON field: {key!r}."
            )
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
            raise ContractError(
                "Decision bytes must be UTF-8."
            ) from exc

    if not isinstance(value, str):
        raise ContractError(
            "Decision payload must be JSON text."
        )

    try:
        decoded = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractError(
            "Decision payload is not valid JSON."
        ) from exc

    return AgentDecision.from_wire(decoded)
