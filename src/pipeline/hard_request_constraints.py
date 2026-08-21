"""Narrow deterministic constraints supplied before semantic planning.

The snapshot records only facts the harness must enforce independently of a
model's interpretation.  It intentionally does not classify the request,
recognize concepts, or select capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.request_semantics import RequestSemanticsClassifier, SourceConstraint
from src.pipeline.safety_policy import sensitive_refusal
from src.pipeline.semantic_mutation_validator import SemanticMutationValidator
from src.pipeline.target_resolver import TargetResolver


@dataclass(frozen=True, slots=True)
class HardTargetReference:
    """A literal target reference and, only when exact, its registry identity."""

    value: str
    registered_target: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("Hard target value must be non-empty text.")
        if self.registered_target is not None and (
            not isinstance(self.registered_target, str) or not self.registered_target
        ):
            raise ValueError("registered_target must be non-empty text or None.")

    def to_dict(self) -> dict[str, str | None]:
        return {"value": self.value, "registered_target": self.registered_target}


@dataclass(frozen=True, slots=True)
class HardRequestConstraints:
    """Typed model-input facts with no inferred request semantics."""

    sensitive_refusal_reason: str | None = None
    mutation_requested: bool = False
    explicit_url: str | None = None
    explicit_target: HardTargetReference | None = None
    source_constraints: tuple[SourceConstraint, ...] = ()
    excluded_sources: tuple[SourceConstraint, ...] = ()
    requires_fresh_evidence: bool = False

    def __post_init__(self) -> None:
        if self.sensitive_refusal_reason is not None and not self.sensitive_refusal_reason.startswith(
            "sensitive:"
        ):
            raise ValueError("sensitive_refusal_reason must be a safety-policy reason.")
        if type(self.mutation_requested) is not bool:
            raise TypeError("mutation_requested must be a bool.")
        for name, value in (("explicit_url", self.explicit_url),):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} must be non-empty text or None.")
        if self.explicit_target is not None and not isinstance(
            self.explicit_target, HardTargetReference
        ):
            raise TypeError("explicit_target must be HardTargetReference or None.")
        for name, values in (
            ("source_constraints", self.source_constraints),
            ("excluded_sources", self.excluded_sources),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(value, SourceConstraint) for value in values
            ):
                raise TypeError(f"{name} must be a tuple of SourceConstraint values.")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must not contain duplicates.")
        if type(self.requires_fresh_evidence) is not bool:
            raise TypeError("requires_fresh_evidence must be a bool.")

    def to_dict(self) -> dict[str, object]:
        """Return the bounded JSON-safe prompt representation."""
        result: dict[str, object] = {
            "sensitive_refusal": self.sensitive_refusal_reason,
            "mutation_requested": self.mutation_requested,
            "fresh_evidence_required": self.requires_fresh_evidence,
        }
        if self.explicit_url is not None:
            result["url"] = self.explicit_url
        if self.explicit_target is not None:
            result["target"] = self.explicit_target.to_dict()
        if self.source_constraints:
            result["sources"] = [item.name.casefold() for item in self.source_constraints]
        if self.excluded_sources:
            result["exclude"] = [item.name.casefold() for item in self.excluded_sources]
        return result


class HardRequestConstraintsBuilder:
    """Build the allowlisted hard snapshot without invoking ``Normalizer``."""

    def __init__(self, target_resolver: TargetResolver | None = None) -> None:
        if target_resolver is not None and not isinstance(target_resolver, TargetResolver):
            raise TypeError("target_resolver must be TargetResolver or None.")
        self._target_resolver = target_resolver
        self._semantics = RequestSemanticsClassifier()

    def build(self, raw_request: str) -> HardRequestConstraints:
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("raw_request must be non-empty text.")

        explicit_url, _url_error = self._semantics._extract_url(raw_request)
        source_constraints, excluded_sources = self._semantics._explicit_source_constraints(
            raw_request.casefold()
        )
        source_constraints = tuple(
            value for value in source_constraints if value is not SourceConstraint.ANY
        )
        freshness_phrase, _freshness_window = self._semantics._freshness(
            raw_request.casefold()
        )

        target: HardTargetReference | None = None
        if self._target_resolver is not None:
            target_value, registered_target = self._target_resolver.extract_hard_constraint_target(
                raw_request
            )
            if target_value is not None:
                target = HardTargetReference(target_value, registered_target)

        return HardRequestConstraints(
            sensitive_refusal_reason=sensitive_refusal(raw_request),
            mutation_requested=_is_explicit_mutation_request(raw_request),
            explicit_url=explicit_url,
            explicit_target=target,
            source_constraints=source_constraints,
            excluded_sources=excluded_sources,
            # The reviewed freshness parser is only exposed as a requirement;
            # it conveys no domain, source, or capability choice.
            requires_fresh_evidence=freshness_phrase is not None,
        )


def _is_explicit_mutation_request(raw_request: str) -> bool:
    """Reuse the existing action guard's reviewed explicit mutation signals."""
    validator = SemanticMutationValidator
    if validator._EXAMPLE_ONLY.search(raw_request) or validator._QUOTED_ONLY.fullmatch(
        raw_request
    ):
        return False
    return validator._EXPLICIT_MUTATION.search(raw_request) is not None


__all__ = [
    "HardRequestConstraints",
    "HardRequestConstraintsBuilder",
    "HardTargetReference",
]
