"""Provider-neutral input-context budgets enforced before model calls.

Orion's low-input-token design is expressed here as explicit, enforceable
budget classes instead of a best-effort convention.  Every model call class
has a bounded character limit and a provider-independent token estimate
derived from the same policy used for output budgets.

Enforcement happens at context construction boundaries, before any
provider is invoked:

- mandatory sections (user request, hard constraints, required evidence)
  are never truncated: if they alone exceed the budget, the call is
  rejected deterministically with :class:`InputContextBudgetError`;
- optional sections are included in semantic-relevance order (first
  section = highest priority) and dropped whole — never sliced — as soon
  as adding one would exceed the budget.

No tokenizer or provider SDK is involved: estimates reuse
:func:`ResponseBudgetPolicy.estimated_tokens`, so the same input always
yields the same estimate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from src.pipeline.response_budget import ResponseBudgetPolicy


class InputContextBudgetClass(str, Enum):
    """Model-call class an input-context budget governs."""

    SIMPLE = "simple"
    NORMAL = "normal"
    EVIDENCE_ASSISTED = "evidence_assisted"
    CONTROLLER_FIRST = "controller_first"
    CONTROLLER_DISCOVERY = "controller_discovery"
    CONTROLLER_ACTION = "controller_action"
    CONTROLLER_OBSERVATION = "controller_observation"


class InputContextBudgetError(ValueError):
    """Mandatory input context alone exceeds its class budget.

    Raised deterministically before any model/provider invocation so a
    call whose mandatory content cannot fit is rejected instead of being
    silently truncated.
    """


@dataclass(frozen=True, slots=True)
class InputContextSection:
    """One named, already-structured section of an input context.

    Sections are whole: enforcement never slices ``text``, so structured
    fields (JSON, instructions, evidence) cannot be corrupted mid-field.
    Callers are responsible for any structure-safe per-section limits.
    """

    name: str
    text: str


@dataclass(frozen=True, slots=True)
class EnforcedInputContext:
    """Outcome of enforcing one budget against one candidate context."""

    budget_class: InputContextBudgetClass
    budget_max_chars: int
    mandatory_names: tuple[str, ...]
    optional_included: tuple[str, ...]
    optional_dropped: tuple[str, ...]
    total_chars: int

    @property
    def estimated_input_tokens(self) -> int:
        """Provider-independent token estimate of the enforced context."""
        return ResponseBudgetPolicy.estimated_tokens_from_chars(self.total_chars)

    @property
    def within_budget(self) -> bool:
        return self.total_chars <= self.budget_max_chars


@dataclass(frozen=True, slots=True)
class InputContextBudget:
    """Bounded character limit and provider-independent estimate for a class."""

    budget_class: InputContextBudgetClass
    max_chars: int

    def __post_init__(self) -> None:
        if self.max_chars < 1:
            raise ValueError("max_chars must be positive.")

    @property
    def max_estimated_tokens(self) -> int:
        return ResponseBudgetPolicy.estimated_tokens_from_chars(self.max_chars)

    @staticmethod
    def estimated_tokens(text: str) -> int:
        """Provider-independent token estimate, shared with output budgets."""
        return ResponseBudgetPolicy.estimated_tokens(text)

    def enforce(
        self,
        *,
        mandatory: Sequence[InputContextSection],
        optional: Sequence[InputContextSection] = (),
    ) -> EnforcedInputContext:
        """Keep every mandatory section, then optional ones while they fit.

        ``mandatory`` must fit entirely or the call is rejected.  ``optional``
        must be supplied in semantic-relevance order (highest priority first);
        a section that would exceed the remaining budget is dropped whole,
        together with every lower-priority section after it.
        """

        mandatory_sections = tuple(mandatory)
        optional_sections = tuple(optional)
        mandatory_total = sum(len(section.text) for section in mandatory_sections)
        if mandatory_total > self.max_chars:
            raise InputContextBudgetError(
                f"Mandatory input context for budget class "
                f"'{self.budget_class.value}' is {mandatory_total} characters, "
                f"exceeding the {self.max_chars}-character budget."
            )
        total = mandatory_total
        included: list[str] = []
        dropped: list[str] = []
        for index, section in enumerate(optional_sections):
            if total + len(section.text) <= self.max_chars:
                total += len(section.text)
                included.append(section.name)
            else:
                dropped.extend(item.name for item in optional_sections[index:])
                break
        return EnforcedInputContext(
            budget_class=self.budget_class,
            budget_max_chars=self.max_chars,
            mandatory_names=tuple(section.name for section in mandatory_sections),
            optional_included=tuple(included),
            optional_dropped=tuple(dropped),
            total_chars=total,
        )


class InputContextBudgetPolicy:
    """Predefined provider-neutral budget classes.

    - SIMPLE: first-pass semantic planner calls.  The user request plus the
      planner system prompt and the allowlisted bounded session context fit
      far below ~1k estimated input tokens for ordinary requests, and the
      total is hard-capped so unrelated history/tool/capability growth can
      never enlarge the call.
    - NORMAL: direct response calls with bounded semantic context (no
      evidence).  The rendered chat system constraints plus the user request
      are mandatory; the optional bounded semantic context is dropped whole
      before the budget is exceeded.
    - EVIDENCE_ASSISTED: assessment calls carrying collected evidence.
      Instructions, the user request, hard constraints (safety boundary,
      evidence status, grounding rule), and required evidence are mandatory;
      optional sections (findings, unknowns, collection failures) are
      dropped in reverse semantic-relevance order before overflow.
    """

    SIMPLE = InputContextBudget(InputContextBudgetClass.SIMPLE, max_chars=6_500)
    NORMAL = InputContextBudget(InputContextBudgetClass.NORMAL, max_chars=4_000)
    EVIDENCE_ASSISTED = InputContextBudget(
        InputContextBudgetClass.EVIDENCE_ASSISTED,
        max_chars=16_000,
    )
    # Controller calls disclose one bounded incremental payload at most.  The
    # first decision stays smallest; later stages have separately inspectable
    # ceilings large enough for their already-bounded mandatory payload.
    CONTROLLER_FIRST = InputContextBudget(
        InputContextBudgetClass.CONTROLLER_FIRST, max_chars=6_500
    )
    CONTROLLER_DISCOVERY = InputContextBudget(
        InputContextBudgetClass.CONTROLLER_DISCOVERY, max_chars=11_000
    )
    CONTROLLER_ACTION = InputContextBudget(
        InputContextBudgetClass.CONTROLLER_ACTION, max_chars=9_000
    )
    CONTROLLER_OBSERVATION = InputContextBudget(
        InputContextBudgetClass.CONTROLLER_OBSERVATION, max_chars=14_000
    )

    @classmethod
    def for_class(cls, budget_class: InputContextBudgetClass) -> InputContextBudget:
        return {
            InputContextBudgetClass.SIMPLE: cls.SIMPLE,
            InputContextBudgetClass.NORMAL: cls.NORMAL,
            InputContextBudgetClass.EVIDENCE_ASSISTED: cls.EVIDENCE_ASSISTED,
            InputContextBudgetClass.CONTROLLER_FIRST: cls.CONTROLLER_FIRST,
            InputContextBudgetClass.CONTROLLER_DISCOVERY: cls.CONTROLLER_DISCOVERY,
            InputContextBudgetClass.CONTROLLER_ACTION: cls.CONTROLLER_ACTION,
            InputContextBudgetClass.CONTROLLER_OBSERVATION: cls.CONTROLLER_OBSERVATION,
        }[budget_class]


__all__ = [
    "EnforcedInputContext",
    "InputContextBudget",
    "InputContextBudgetClass",
    "InputContextBudgetError",
    "InputContextBudgetPolicy",
    "InputContextSection",
]
