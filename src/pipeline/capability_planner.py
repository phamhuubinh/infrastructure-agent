from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

import yaml

from src.pipeline.semantic_request import SemanticRequest


class CapabilityPlanner:
    """Map (concept, action) → list of capability names.

    The CapabilityPlanner ONLY knows about capability mappings — it has
    ZERO knowledge of natural language, synonyms, or how the user's
    request was tokenized.

    This is a strict separation: Normalizer = language, CapabilityPlanner = capability mapping.

    Responsibilities:
    - load capability plans from config/capability_plans.yaml
    - map a (concept, action) pair to a list of capability names
    - provide a fallback when no plan exists for the given (concept, action)

    Never performs execution or tool calls.
    """

    # Default capabilities when no plan exists for the requested pair.
    _FALLBACK_CAPABILITIES: ClassVar[list[str]] = [
        "system_information",
        "cpu",
        "memory",
        "storage",
        "network",
    ]

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the CapabilityPlanner.

        Args:
            config_path: Path to capability_plans.yaml.  Defaults to
                         config/capability_plans.yaml relative to the repo root.
        """
        if config_path is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            config_path = str(repo_root / "config" / "capability_plans.yaml")
        self._config_path = config_path
        self._loaded = False
        self._plans: dict[str, dict[str, list[str]]] = {}

    def _ensure_loaded(self) -> None:
        """Lazy-load the capability plans YAML config."""
        if self._loaded:
            return
        if not os.path.exists(self._config_path):
            self._loaded = True
            return
        with open(self._config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self._plans = data.get("plans", {})
        self._loaded = True

    def plan(self, semantic: SemanticRequest) -> list[str]:
        """Return the list of capability names for a given concept+action.

        Args:
            semantic: The SemanticRequest from the Normalizer.

        Returns:
            A list of capability name strings.  Falls back to
            _FALLBACK_CAPABILITIES when no plan is defined for the
            (concept, action) pair.
        """
        self._ensure_loaded()

        concept = semantic.concept
        action = semantic.action

        concept_plans = self._plans.get(concept)
        if concept_plans is None:
            # Try machine as a secondary fallback before the hardcoded list.
            concept_plans = self._plans.get("machine")

        if concept_plans is not None:
            capabilities = concept_plans.get(action)
            if capabilities is not None:
                return list(capabilities)

        # Fallback: try the "inspect" action for this concept.
        if concept_plans is not None:
            capabilities = concept_plans.get("inspect")
            if capabilities is not None:
                return list(capabilities)

        return list(self._FALLBACK_CAPABILITIES)
