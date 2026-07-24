from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SemanticRequest:
    """Structured representation of a user request produced by the Normalizer.

    The Normalizer converts natural language text into this structured form.
    It only understands language patterns — it has no knowledge of capabilities
    or what evidence items exist.

    Attributes:
        concept: The infrastructure concept (e.g. "cpu", "memory", "disk").
        action: The user's intended action (e.g. "inspect", "diagnose").
        target_raw: The raw target string extracted from the request, if any.
                    None means no explicit target was mentioned.
        target: The resolved/normalized target name. Set later by TargetResolver.
                None means the target has not been resolved yet.
        confidence: Confidence score 0.0–1.0 from the normalization process.
                    1.0 = multiple synonyms matched across concept+action.
                    0.0 = no match at all (fallback).
        matched_synonyms: The specific synonyms that triggered the concept+action
                          classification.
    """

    concept: str
    action: str
    target_raw: str | None = None
    target: str | None = None
    confidence: float = 0.0
    matched_synonyms: list[str] = field(default_factory=list)
