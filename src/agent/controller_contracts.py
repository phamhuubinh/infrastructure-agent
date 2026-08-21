"""Strict, non-executable contracts for the Agent v2 controller.

These values are exchanged between a model and the deterministic controller.
They describe advisory decisions and compact, already-sanitized observations;
they never carry commands, credentials, tool handles, raw collector output, or
execution budgets.  This module deliberately does not execute an action.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from json import JSONDecodeError
from types import MappingProxyType
from typing import TypeVar

CONTROLLER_WIRE_VERSION = 1
MAX_CONTROLLER_WIRE_BYTES = 8_192
MAX_GOAL_CHARS = 256
MAX_TEXT_CHARS = 512
MAX_RAW_REQUEST_CHARS = 4_096
MAX_ARGUMENTS = 16
MAX_ARGUMENT_DEPTH = 4
MAX_FACTS = 12
MAX_OBSERVATIONS = 16
MAX_PROVENANCE_REFERENCES = 12
MAX_DISCLOSED_CAPABILITIES = 32

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_FORBIDDEN_ACTION_KEYS = frozenset(
    {
        "api_key",
        "budget",
        "callback",
        "command",
        "code",
        "credential",
        "credentials",
        "cmd",
        "endpoint",
        "evidence",
        "executable",
        "function",
        "password",
        "private_key",
        "program",
        "raw_payload",
        "retry",
        "secret",
        "shell",
        "script",
        "token",
    }
)
_DECISION_KEYS = frozenset({"v", "k", "g", "c", "a", "f", "q", "r"})
_ACTION_KEYS = frozenset({"i", "a"})
_OBSERVATION_KEYS = frozenset(
    {"n", "i", "s", "f", "m", "t", "o", "p", "r", "c"}
)
_STATE_KEYS = frozenset(
    {"v", "q", "g", "hr", "hv", "cc", "cd", "o", "rd", "ac", "mc", "t", "ts"}
)

_EnumT = TypeVar("_EnumT", bound=Enum)


class ControllerContractError(ValueError):
    """Raised when an Agent v2 contract is malformed or unsafe."""


class AgentDecisionKind(str, Enum):
    """The only advisory next-step shapes accepted from a controller model."""

    FINAL = "final"
    DISCOVER = "discover"
    ACTION = "action"
    CLARIFY = "clarify"
    REFUSE = "refuse"


class AgentObservationStatus(str, Enum):
    """Safe result states for a validated attempted action."""

    SUCCESS = "success"
    EMPTY_SUCCESS = "empty_success"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    INVALID_ACTION = "invalid_action"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentAction:
    """One capability request, still subject to deterministic validation.

    The identifier is an Orion capability ID, not a tool name or command.
    Arguments are deeply immutable JSON data and reject executable or secret
    shaped keys before they can reach a later binding boundary.
    """

    capability_id: str
    arguments: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        _identifier(self.capability_id, "capability_id")
        frozen = _freeze_json_mapping(
            self.arguments,
            "arguments",
            max_items=MAX_ARGUMENTS,
            forbid_action_keys=True,
        )
        object.__setattr__(self, "arguments", frozen)

    def to_wire(self) -> dict[str, object]:
        return {"i": self.capability_id, "a": _thaw_json(self.arguments)}

    @classmethod
    def from_wire(cls, value: object) -> AgentAction:
        data = _exact_object(value, _ACTION_KEYS, "action")
        return cls(
            capability_id=_identifier(data["i"], "action.i"),
            arguments=_json_mapping(
                data["a"],
                "action.a",
                max_items=MAX_ARGUMENTS,
                forbid_action_keys=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class AgentDecision:
    """One bounded advisory decision with exactly one decision-specific body.

    ``AgentDecision()`` is deliberately a clarification, never an action or
    an implicit local target.  The deterministic harness must still validate
    every non-terminal decision before it has any effect.
    """

    kind: AgentDecisionKind = AgentDecisionKind.CLARIFY
    goal: str = "Clarify the request."
    category: str | None = None
    action: AgentAction | None = None
    final_answer: str | None = None
    clarification_question: str | None = "Please clarify your request."
    refusal_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AgentDecisionKind):
            raise TypeError("kind must be an AgentDecisionKind value.")
        _goal(self.goal)
        if self.category is not None:
            _identifier(self.category, "category")
        for name, value in (
            ("final_answer", self.final_answer),
            ("clarification_question", self.clarification_question),
            ("refusal_reason", self.refusal_reason),
        ):
            _optional_text(value, name, max_length=MAX_TEXT_CHARS)
        if self.action is not None and not isinstance(self.action, AgentAction):
            raise TypeError("action must be an AgentAction or None.")

        bodies = {
            "category": self.category,
            "action": self.action,
            "final_answer": self.final_answer,
            "clarification_question": self.clarification_question,
            "refusal_reason": self.refusal_reason,
        }
        required = {
            AgentDecisionKind.FINAL: "final_answer",
            AgentDecisionKind.DISCOVER: "category",
            AgentDecisionKind.ACTION: "action",
            AgentDecisionKind.CLARIFY: "clarification_question",
            AgentDecisionKind.REFUSE: "refusal_reason",
        }[self.kind]
        present = {name for name, value in bodies.items() if value is not None}
        if present != {required}:
            raise ValueError(
                f"{self.kind.value} decision must contain exactly {required}."
            )

    def to_wire(self) -> dict[str, object]:
        return {
            "v": CONTROLLER_WIRE_VERSION,
            "k": self.kind.value,
            "g": self.goal,
            "c": self.category,
            "a": self.action.to_wire() if self.action is not None else None,
            "f": self.final_answer,
            "q": self.clarification_question,
            "r": self.refusal_reason,
        }

    @classmethod
    def from_wire(cls, value: object) -> AgentDecision:
        data = _exact_object(value, _DECISION_KEYS, "decision")
        _wire_version(data["v"], "decision.v")
        action_value = data["a"]
        return cls(
            kind=_enum(AgentDecisionKind, data["k"], "decision.k"),
            goal=_goal(data["g"]),
            category=_optional_identifier(data["c"], "decision.c"),
            action=(
                AgentAction.from_wire(action_value)
                if action_value is not None
                else None
            ),
            final_answer=_optional_text(data["f"], "decision.f", max_length=MAX_TEXT_CHARS),
            clarification_question=_optional_text(
                data["q"], "decision.q", max_length=MAX_TEXT_CHARS
            ),
            refusal_reason=_optional_text(data["r"], "decision.r", max_length=MAX_TEXT_CHARS),
        )


@dataclass(frozen=True, slots=True)
class AgentObservation:
    """Bounded canonical outcome for one validated action attempt.

    ``facts`` contains compact canonical fact mappings only; raw collector
    payloads are intentionally not representable by this contract.
    """

    action_id: int
    capability_id: str
    status: AgentObservationStatus
    facts: tuple[Mapping[str, object], ...] = ()
    summary: str | None = None
    target_id: str | None = None
    source_id: str | None = None
    provenance_references: tuple[str, ...] = ()
    reason_code: str | None = None
    recoverable: bool = False

    def __post_init__(self) -> None:
        if type(self.action_id) is not int or self.action_id < 1:
            raise ValueError("action_id must be a positive integer.")
        _identifier(self.capability_id, "capability_id")
        if not isinstance(self.status, AgentObservationStatus):
            raise TypeError("status must be an AgentObservationStatus value.")
        _optional_text(self.summary, "summary", max_length=MAX_TEXT_CHARS)
        for name, value in (("target_id", self.target_id), ("source_id", self.source_id)):
            _optional_text(value, name, max_length=MAX_TEXT_CHARS)
        _optional_identifier(self.reason_code, "reason_code")
        if type(self.recoverable) is not bool:
            raise TypeError("recoverable must be a bool.")
        if not isinstance(self.facts, tuple):
            raise TypeError("facts must be a tuple of canonical fact mappings.")
        if len(self.facts) > MAX_FACTS:
            raise ValueError(f"facts may contain at most {MAX_FACTS} items.")
        frozen_facts = tuple(
            _freeze_json_mapping(
                fact,
                f"facts[{index}]",
                max_items=16,
                forbid_action_keys=True,
            )
            for index, fact in enumerate(self.facts)
        )
        object.__setattr__(self, "facts", frozen_facts)
        references = _text_tuple(
            self.provenance_references,
            "provenance_references",
            max_items=MAX_PROVENANCE_REFERENCES,
            max_length=MAX_TEXT_CHARS,
        )
        object.__setattr__(self, "provenance_references", references)

    def to_wire(self) -> dict[str, object]:
        return {
            "n": self.action_id,
            "i": self.capability_id,
            "s": self.status.value,
            "f": [_thaw_json(fact) for fact in self.facts],
            "m": self.summary,
            "t": self.target_id,
            "o": self.source_id,
            "p": list(self.provenance_references),
            "r": self.reason_code,
            "c": self.recoverable,
        }

    def to_trace_dict(self) -> dict[str, object]:
        """Return the same bounded, raw-payload-free observation projection."""

        return self.to_wire()

    @classmethod
    def from_wire(cls, value: object) -> AgentObservation:
        data = _exact_object(value, _OBSERVATION_KEYS, "observation")
        facts = data["f"]
        if not isinstance(facts, list):
            raise ControllerContractError("observation.f must be an array.")
        return cls(
            action_id=_positive_int(data["n"], "observation.n"),
            capability_id=_identifier(data["i"], "observation.i"),
            status=_enum(AgentObservationStatus, data["s"], "observation.s"),
            facts=tuple(
                _json_mapping(
                    item,
                    f"observation.f[{index}]",
                    max_items=16,
                    forbid_action_keys=True,
                )
                for index, item in enumerate(facts)
            ),
            summary=_optional_text(data["m"], "observation.m", max_length=MAX_TEXT_CHARS),
            target_id=_optional_text(data["t"], "observation.t", max_length=MAX_TEXT_CHARS),
            source_id=_optional_text(data["o"], "observation.o", max_length=MAX_TEXT_CHARS),
            provenance_references=_text_tuple(
                data["p"],
                "observation.p",
                max_items=MAX_PROVENANCE_REFERENCES,
                max_length=MAX_TEXT_CHARS,
            ),
            reason_code=_optional_identifier(data["r"], "observation.r"),
            recoverable=_bool(data["c"], "observation.c"),
        )


@dataclass(frozen=True, slots=True)
class AgentRunState:
    """Immutable state for a future bounded controller loop.

    It carries no implicit target, tool, retry policy, budget, or model handle.
    An empty disclosure/observation history therefore grants no localhost or
    tool authority merely by constructing this value.
    """

    raw_request: str
    goal: str | None = None
    hard_constraint_reference: str | None = None
    hard_constraint_snapshot: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )
    disclosed_capability_categories: tuple[str, ...] = ()
    disclosed_capability_detail_ids: tuple[str, ...] = ()
    observations: tuple[AgentObservation, ...] = ()
    round_count: int = 0
    action_count: int = 0
    model_call_count: int = 0
    terminal: bool = False
    terminal_status: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.raw_request, "raw_request", max_length=MAX_RAW_REQUEST_CHARS)
        if self.goal is not None:
            _goal(self.goal)
        _optional_identifier(self.hard_constraint_reference, "hard_constraint_reference")
        object.__setattr__(
            self,
            "hard_constraint_snapshot",
            _freeze_json_mapping(
                self.hard_constraint_snapshot,
                "hard_constraint_snapshot",
                max_items=32,
            ),
        )
        object.__setattr__(
            self,
            "disclosed_capability_categories",
            _identifier_tuple(
                self.disclosed_capability_categories,
                "disclosed_capability_categories",
            ),
        )
        object.__setattr__(
            self,
            "disclosed_capability_detail_ids",
            _identifier_tuple(
                self.disclosed_capability_detail_ids,
                "disclosed_capability_detail_ids",
            ),
        )
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, AgentObservation) for item in self.observations
        ):
            raise TypeError("observations must be a tuple of AgentObservation values.")
        if len(self.observations) > MAX_OBSERVATIONS:
            raise ValueError(f"observations may contain at most {MAX_OBSERVATIONS} items.")
        for name, value in (
            ("round_count", self.round_count),
            ("action_count", self.action_count),
            ("model_call_count", self.model_call_count),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        if type(self.terminal) is not bool:
            raise TypeError("terminal must be a bool.")
        _optional_identifier(self.terminal_status, "terminal_status")
        if self.terminal != (self.terminal_status is not None):
            raise ValueError("terminal and terminal_status must be set together.")

    def to_wire(self) -> dict[str, object]:
        return {
            "v": CONTROLLER_WIRE_VERSION,
            "q": self.raw_request,
            "g": self.goal,
            "hr": self.hard_constraint_reference,
            "hv": _thaw_json(self.hard_constraint_snapshot),
            "cc": list(self.disclosed_capability_categories),
            "cd": list(self.disclosed_capability_detail_ids),
            "o": [item.to_wire() for item in self.observations],
            "rd": self.round_count,
            "ac": self.action_count,
            "mc": self.model_call_count,
            "t": self.terminal,
            "ts": self.terminal_status,
        }

    def to_trace_dict(self) -> dict[str, object]:
        """Project safe state metadata without repeating the raw user request."""

        trace = self.to_wire()
        trace.pop("q")
        return trace

    @classmethod
    def from_wire(cls, value: object) -> AgentRunState:
        data = _exact_object(value, _STATE_KEYS, "run_state")
        _wire_version(data["v"], "run_state.v")
        observations = data["o"]
        if not isinstance(observations, list):
            raise ControllerContractError("run_state.o must be an array.")
        return cls(
            raw_request=_required_text(data["q"], "run_state.q", max_length=MAX_RAW_REQUEST_CHARS),
            goal=(None if data["g"] is None else _goal(data["g"])),
            hard_constraint_reference=_optional_identifier(data["hr"], "run_state.hr"),
            hard_constraint_snapshot=_json_mapping(data["hv"], "run_state.hv", max_items=32),
            disclosed_capability_categories=_identifier_tuple(
                data["cc"], "run_state.cc"
            ),
            disclosed_capability_detail_ids=_identifier_tuple(data["cd"], "run_state.cd"),
            observations=tuple(AgentObservation.from_wire(item) for item in observations),
            round_count=_non_negative_int(data["rd"], "run_state.rd"),
            action_count=_non_negative_int(data["ac"], "run_state.ac"),
            model_call_count=_non_negative_int(data["mc"], "run_state.mc"),
            terminal=_bool(data["t"], "run_state.t"),
            terminal_status=_optional_identifier(data["ts"], "run_state.ts"),
        )


def agent_decision_to_json(decision: AgentDecision) -> str:
    """Serialize one decision to compact deterministic JSON."""

    if not isinstance(decision, AgentDecision):
        raise TypeError("decision must be an AgentDecision.")
    return _compact_json(decision.to_wire())


def agent_decision_from_json(payload: str | bytes) -> AgentDecision:
    """Parse a strict decision payload, rejecting duplicate keys and enums."""

    return AgentDecision.from_wire(_decode_json(payload))


def agent_observation_to_json(observation: AgentObservation) -> str:
    """Serialize one bounded observation to compact deterministic JSON."""

    if not isinstance(observation, AgentObservation):
        raise TypeError("observation must be an AgentObservation.")
    return _compact_json(observation.to_wire())


def agent_observation_from_json(payload: str | bytes) -> AgentObservation:
    """Parse a strict observation payload."""

    return AgentObservation.from_wire(_decode_json(payload))


def agent_run_state_to_json(state: AgentRunState) -> str:
    """Serialize one controller state to compact deterministic JSON."""

    if not isinstance(state, AgentRunState):
        raise TypeError("state must be an AgentRunState.")
    return _compact_json(state.to_wire())


def agent_run_state_from_json(payload: str | bytes) -> AgentRunState:
    """Parse a strict controller-state payload."""

    return AgentRunState.from_wire(_decode_json(payload))


def _exact_object(
    value: object, expected_keys: frozenset[str], field_name: str
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ControllerContractError(f"{field_name} must be an object.")
    actual = set(value)
    unknown = actual - expected_keys
    missing = expected_keys - actual
    if unknown:
        raise ControllerContractError(
            f"{field_name} contains unknown fields: {', '.join(sorted(unknown))}."
        )
    if missing:
        raise ControllerContractError(
            f"{field_name} is missing fields: {', '.join(sorted(missing))}."
        )
    return value


def _enum(enum_type: type[_EnumT], value: object, field_name: str) -> _EnumT:
    if not isinstance(value, str):
        raise ControllerContractError(f"{field_name} must be a string enum value.")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ControllerContractError(
            f"{field_name} has an unknown enum value."
        ) from exc


def _wire_version(value: object, field_name: str) -> None:
    if type(value) is not int or value != CONTROLLER_WIRE_VERSION:
        raise ControllerContractError(
            f"{field_name} must be the integer {CONTROLLER_WIRE_VERSION}."
        )


def _goal(value: object) -> str:
    goal = _required_text(value, "goal", max_length=MAX_GOAL_CHARS)
    sentence_marks = sum(goal.count(mark) for mark in ".!?")
    if sentence_marks > 1:
        raise ValueError("goal must contain at most one sentence.")
    return goal


def _required_text(value: object, field_name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty trimmed text.")
    if len(value) > max_length:
        raise ValueError(f"{field_name} exceeds the compact text limit.")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field_name} must not contain control characters.")
    return value


def _optional_text(value: object, field_name: str, *, max_length: int) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name, max_length=max_length)


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable Orion identifier.")
    return value


def _optional_identifier(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field_name)


def _positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise ControllerContractError(f"{field_name} must be a positive integer.")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ControllerContractError(f"{field_name} must be a non-negative integer.")
    return value


def _bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ControllerContractError(f"{field_name} must be a bool.")
    return value


def _text_tuple(
    value: object,
    field_name: str,
    *,
    max_items: int,
    max_length: int,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        if isinstance(value, list):
            value = tuple(value)
        else:
            raise TypeError(f"{field_name} must be a tuple of text values.")
    if len(value) > max_items:
        raise ValueError(f"{field_name} may contain at most {max_items} items.")
    return tuple(
        _required_text(item, f"{field_name}[{index}]", max_length=max_length)
        for index, item in enumerate(value)
    )


def _identifier_tuple(value: object, field_name: str) -> tuple[str, ...]:
    values = _text_tuple(
        value,
        field_name,
        max_items=MAX_DISCLOSED_CAPABILITIES,
        max_length=80,
    )
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicate identifiers.")
    return tuple(_identifier(item, f"{field_name}[]") for item in values)


def _json_mapping(
    value: object,
    field_name: str,
    *,
    max_items: int,
    forbid_action_keys: bool = False,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ControllerContractError(f"{field_name} must be an object.")
    return _freeze_json_mapping(
        value,
        field_name,
        max_items=max_items,
        forbid_action_keys=forbid_action_keys,
    )


def _freeze_json_mapping(
    value: object,
    field_name: str,
    *,
    max_items: int,
    forbid_action_keys: bool = False,
) -> MappingProxyType:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    if len(value) > max_items:
        raise ValueError(f"{field_name} may contain at most {max_items} items.")
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or key != key.strip():
            raise ValueError(f"{field_name} keys must be non-empty trimmed text.")
        if len(key) > 80 or any(ord(character) < 32 for character in key):
            raise ValueError(f"{field_name} has an invalid key.")
        if forbid_action_keys and _forbidden_action_key(key):
            raise ValueError(f"{field_name} must not contain {key!r}.")
        frozen[key] = _freeze_json_value(
            item,
            f"{field_name}.{key}",
            depth=1,
            forbid_action_keys=forbid_action_keys,
        )
    return MappingProxyType(frozen)


def _freeze_json_value(
    value: object,
    field_name: str,
    *,
    depth: int,
    forbid_action_keys: bool,
) -> object:
    if depth > MAX_ARGUMENT_DEPTH:
        raise ValueError(f"{field_name} exceeds the maximum JSON nesting depth.")
    if value is None or type(value) in {bool, int}:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must be a finite JSON number.")
        return value
    if isinstance(value, str):
        return _required_text(value, field_name, max_length=MAX_TEXT_CHARS)
    if isinstance(value, Mapping):
        return _freeze_json_mapping_nested(
            value,
            field_name,
            depth=depth,
            forbid_action_keys=forbid_action_keys,
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > MAX_ARGUMENTS:
            raise ValueError(f"{field_name} may contain at most {MAX_ARGUMENTS} items.")
        return tuple(
            _freeze_json_value(
                item,
                f"{field_name}[{index}]",
                depth=depth + 1,
                forbid_action_keys=forbid_action_keys,
            )
            for index, item in enumerate(value)
        )
    raise TypeError(f"{field_name} must contain only JSON-safe values.")


def _freeze_json_mapping_nested(
    value: Mapping[object, object],
    field_name: str,
    *,
    depth: int,
    forbid_action_keys: bool,
) -> MappingProxyType:
    if len(value) > MAX_ARGUMENTS:
        raise ValueError(f"{field_name} may contain at most {MAX_ARGUMENTS} items.")
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or key != key.strip():
            raise ValueError(f"{field_name} keys must be non-empty trimmed text.")
        if forbid_action_keys and _forbidden_action_key(key):
            raise ValueError(f"{field_name} must not contain {key!r}.")
        frozen[key] = _freeze_json_value(
            item,
            f"{field_name}.{key}",
            depth=depth + 1,
            forbid_action_keys=forbid_action_keys,
        )
    return MappingProxyType(frozen)


def _normal_key(value: str) -> str:
    return value.casefold().replace("-", "_").replace(" ", "_")


def _forbidden_action_key(value: str) -> bool:
    normalized = _normal_key(value)
    return normalized in _FORBIDDEN_ACTION_KEYS or any(
        part in _FORBIDDEN_ACTION_KEYS for part in normalized.split("_")
    )


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _compact_json(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_CONTROLLER_WIRE_BYTES:
        raise ControllerContractError("Controller payload exceeds the byte limit.")
    return encoded


def _decode_json(payload: str | bytes) -> object:
    if isinstance(payload, bytes):
        if len(payload) > MAX_CONTROLLER_WIRE_BYTES:
            raise ControllerContractError("Controller payload exceeds the byte limit.")
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ControllerContractError("Controller payload is not UTF-8.") from exc
    if not isinstance(payload, str):
        raise ControllerContractError("Controller payload must be text or bytes.")
    if len(payload.encode("utf-8")) > MAX_CONTROLLER_WIRE_BYTES:
        raise ControllerContractError("Controller payload exceeds the byte limit.")
    try:
        return json.loads(payload, object_pairs_hook=_no_duplicate_object)
    except JSONDecodeError as exc:
        raise ControllerContractError("Controller payload is not valid JSON.") from exc


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ControllerContractError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


__all__ = [
    "CONTROLLER_WIRE_VERSION",
    "MAX_ARGUMENTS",
    "MAX_FACTS",
    "MAX_OBSERVATIONS",
    "AgentAction",
    "AgentDecision",
    "AgentDecisionKind",
    "AgentObservation",
    "AgentObservationStatus",
    "AgentRunState",
    "ControllerContractError",
    "agent_decision_from_json",
    "agent_decision_to_json",
    "agent_observation_from_json",
    "agent_observation_to_json",
    "agent_run_state_from_json",
    "agent_run_state_to_json",
]
