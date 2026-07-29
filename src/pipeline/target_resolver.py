from __future__ import annotations

import difflib
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import yaml

from src.pipeline.investigation_request import InvestigationRequest

if TYPE_CHECKING:
    from src.shared.pipeline_state import PipelineState, StateUpdate


class UnknownTargetError(ValueError):
    """Raised when the user explicitly mentions a target that does not exist."""

    def __init__(
        self,
        raw_target: str,
        available: list[str],
        domain_tool_names: list[str] | None = None,
    ) -> None:
        self.raw_target = raw_target
        self.available = available
        # Filter out domain tool names (grafana, zabbix, etc.) from suggestions.
        # Only suggest actual infrastructure target hosts (localhost, monitor, etc.).
        _dt_set = set(domain_tool_names or [])
        _target_only = sorted(t for t in available if t not in _dt_set)
        if available:
            if _target_only:
                super().__init__(
                    f"Unknown target: '{raw_target}'.\n"
                    f"Did you mean: {', '.join(_target_only)}"
                )
            else:
                super().__init__(
                    f"Unknown target: '{raw_target}'.\n"
                    f"Available: {', '.join(sorted(available))}"
                )
        else:
            super().__init__(f"Unknown target: '{raw_target}'.\nNo targets configured.")


class TargetResolver:
    """Resolve investigation target from user request.

    Responsibilities:
    - read user request, extract target name
    - match against registered targets (from TargetRegistry)
    - use intent-based default when no explicit target is found
    - raise UnknownTargetError when user names a non-existent target
    - return a StateUpdate dict for immutable state accumulation

    Never performs execution or evidence collection.
    """

    # Hardcoded fallback aliases (used when config file is missing).
    _DEFAULT_ALIASES: ClassVar[dict[str, str]] = {
        "server1": "server01",
        "server2": "server02",
        "srv01": "server01",
        "sv01": "server01",
        "monitoring": "zabbix",
        "mon": "zabbix",
        "zabbix_server": "zabbix",
        "zabbix-server": "zabbix",
        "graphana": "grafana",
        "graphan": "grafana",
    }

    _DEFAULT_LOCALHOST_SYNONYMS: ClassVar[list[str]] = [
        "localhost",
        "127.0.0.1",
        "::1",
        "máy này",
        "máy",
        "host này",
        "host hiện tại",
        "server này",
    ]

    _DEFAULT_SKIP_WORDS: ClassVar[frozenset[str]] = frozenset(
        {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "check",
            "show",
            "get",
            "list",
            "find",
            "what",
            "how",
            "why",
            "when",
            "where",
            "in",
            "with",
            "of",
            "to",
            "and",
            "or",
            "but",
            "not",
            "all",
            "cpu",
            "memory",
            "disk",
            "network",
            "storage",
            "system",
            "alert",
            "alerts",
            "problem",
            "problems",
            "service",
            "services",
            "status",
            "health",
            "performance",
            "security",
            "config",
            "orion",
            "database",
            "monitor",
            "monitoring",
            "dashboard",
            "dashboards",
            "host",
            "hosts",
            "process",
            "processes",
            "package",
            "packages",
        }
    )

    _DEFAULT_TARGET_PATTERNS: ClassVar[list[dict[str, str]]] = [
        {"pattern": r"^srv(\d+)$", "replacement": r"server\1"},
        {"pattern": r"^sv(\d+)$", "replacement": r"server0\1"},
        {"pattern": r"^mon(\d+)$", "replacement": "monitor"},
        {"pattern": r"^(\w+)-(\d+)$", "replacement": r"\1\2"},
        {"pattern": r"^(\w+)_(\d+)$", "replacement": r"\1\2"},
    ]

    def __init__(
        self,
        target_registry=None,
        config_path: str | None = None,
    ) -> None:
        from src.tool.target_registry import TargetRegistry

        self._registry: TargetRegistry | None = target_registry
        if config_path is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            config_path = str(repo_root / "config" / "target_aliases.yaml")
        self._config_path = config_path
        self._loaded = False
        self._aliases: dict[str, str] = {}
        self._skip_words: frozenset[str] = frozenset()
        self._localhost_synonyms: list[str] = []
        self._target_patterns: list[dict[str, str]] = []
        # Per-session cache of bad targets (words that previously failed resolution).
        # Prevents repeating the same UnknownTargetError across multiple turns.
        self._bad_targets: set[str] = set()

    def _ensure_loaded(self) -> None:
        """Lazy-load the target aliases YAML config."""
        if self._loaded:
            return
        if os.path.exists(self._config_path):
            with open(self._config_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            self._aliases = dict(data.get("aliases", self._DEFAULT_ALIASES))
            self._skip_words = frozenset(data.get("skip_words", []))
            self._localhost_synonyms = list(
                data.get("localhost_synonyms", self._DEFAULT_LOCALHOST_SYNONYMS)
            )
            self._target_patterns = list(
                data.get("target_patterns", self._DEFAULT_TARGET_PATTERNS)
            )
        else:
            self._aliases = dict(self._DEFAULT_ALIASES)
            self._skip_words = self._DEFAULT_SKIP_WORDS
            self._localhost_synonyms = list(self._DEFAULT_LOCALHOST_SYNONYMS)
            self._target_patterns = list(self._DEFAULT_TARGET_PATTERNS)
        self._loaded = True

    @staticmethod
    def _extract_words(raw: str) -> list[str]:
        return [w.strip(",.!?;:'\"()[]{}<>") for w in raw.split()]

    def normalize_target_name(self, raw_name: str) -> str:
        """Apply pattern-based normalization to a target name.

        Examples:
            sv01 → server01
            srv01 → server01
            mon01 → monitor
            server-01 → server01
        """
        self._ensure_loaded()
        name = raw_name.strip().lower()
        for rule in self._target_patterns:
            pattern = rule.get("pattern", "")
            replacement = rule.get("replacement", "")
            if pattern:
                try:
                    new_name = re.sub(pattern, replacement, name)
                    if new_name != name:
                        return new_name
                except re.error:
                    continue
        return name

    def _is_localhost_synonym(self, word: str) -> bool:
        """Check if a word is a known localhost synonym."""
        self._ensure_loaded()
        return word.lower() in self._localhost_synonyms

    def _find_unrecognized_hostname(self, words: list[str]) -> str | None:
        """Find a word that looks like an unrecognized hostname.

        Used to prevent localhost synonyms from shadowing actual target names
        that appear mid-sentence (e.g., "Kiểm tra CPU trên máy khonghetontai123").
        """
        self._ensure_loaded()
        _hostname_pattern = re.compile(r"^[a-z][a-z0-9._-]*$", re.IGNORECASE)
        _prepositions = frozenset({"on", "for", "at", "from"})
        for word in words:
            if (
                len(word) > 2
                and word not in self._skip_words
                and word not in _prepositions
                and not self._is_localhost_synonym(word)
                and _hostname_pattern.match(word)
                and not word.isalpha()
            ):
                return word
        return None

    # ------------------------------------------------------------------
    # Immutable pipeline state interface.
    # ------------------------------------------------------------------

    def _domain_tool_names(self) -> list[str]:
        """Return the list of domain tool names from the registry."""
        if self._registry is not None:
            return list(self._registry._domain_tools.keys())
        return []

    def resolve_state(self, state: PipelineState) -> StateUpdate:
        """Return an immutable StateUpdate with the resolved target."""
        self._ensure_loaded()
        raw = state.user_request.lower()
        intent = state.intent

        known_names: list[str] = []
        domain_names: list[str] = []
        if self._registry is not None:
            known_names = self._registry.target_names()
            domain_names = list(self._registry._domain_tools.keys())

        words = self._extract_words(raw)

        # Step 0: Check localhost synonyms first.
        for word in words:
            if self._is_localhost_synonym(word):
                update: StateUpdate = {"target": "localhost"}
                return update

        # Step 0.5: Check bad-target cache.
        for word in words:
            if word in self._bad_targets:
                raise UnknownTargetError(word, known_names, domain_names)

        # Step 1: Check aliases.
        for word in words:
            alias_target = self._aliases.get(word)
            if alias_target:
                if alias_target in known_names:
                    update: StateUpdate = {"target": alias_target}
                    return update
                self._bad_targets.add(alias_target)
                raise UnknownTargetError(alias_target, known_names, domain_names)

        # Step 2: Try normalized target names via pattern matching.
        for word in words:
            normalized = self.normalize_target_name(word)
            if normalized != word and normalized in known_names:
                update: StateUpdate = {"target": normalized}
                return update

        # Step 3: Exact substring match.
        for name in sorted(known_names, key=len, reverse=True):
            if name.lower() in raw:
                update: StateUpdate = {"target": name}
                return update

        # Step 4: Fuzzy match for typos.
        best_name: str | None = None
        best_ratio: float = 0.0
        for name in known_names:
            for word in words:
                ratio = difflib.SequenceMatcher(None, name.lower(), word).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_name = name
        if best_name is not None and best_ratio >= 0.6:
            update: StateUpdate = {"target": best_name}
            return update

        # Step 4.5: Detect potential hostnames.
        _prepositions = frozenset({"on", "for", "at", "from"})
        _hostname_pattern = re.compile(r"^[a-z][a-z0-9._-]*$", re.IGNORECASE)
        for word in words:
            if (
                len(word) > 2
                and word not in self._skip_words
                and word not in _prepositions
                and not self._is_localhost_synonym(word)
                and _hostname_pattern.match(word)
                and not word.isalpha()
            ):
                self._bad_targets.add(word)
                raise UnknownTargetError(word, known_names, domain_names)

        # Step 5: Intent + keyword-based defaults.
        if intent is not None and self._registry is not None:
            intent_name = intent.name
            if intent_name == "MONITORING_ASSESSMENT":
                if any(
                    kw in raw
                    for kw in ("dashboard", "panel", "grafana", "biểu đồ", "đồ thị")
                ):
                    if "grafana" in known_names:
                        update: StateUpdate = {"target": "grafana"}
                        return update
                for preferred in ("zabbix", "grafana"):
                    if preferred in known_names:
                        update: StateUpdate = {"target": preferred}
                        return update

        # Step 6: Preposition-based target.
        for i, word in enumerate(words):
            if word in _prepositions and i + 1 < len(words):
                candidate = words[i + 1]
                normalized_candidate = self.normalize_target_name(candidate)
                if (
                    len(candidate) > 2
                    and candidate not in self._skip_words
                    and normalized_candidate not in self._skip_words
                ):
                    if normalized_candidate in known_names:
                        update: StateUpdate = {"target": normalized_candidate}
                        return update
                    self._bad_targets.add(candidate)
                    raise UnknownTargetError(candidate, known_names, domain_names)

        # Step 7: Fallback.
        update: StateUpdate = {"target": "localhost"}
        return update

    def resolve(self, request: InvestigationRequest) -> None:
        """Resolve the target for the given investigation request.

        Scans the request for known target/domain-tool names first.
        If no explicit match, uses intent + keyword-based defaults.

        Args:
            request: InvestigationRequest. Mutates request.target.

        Raises:
            UnknownTargetError: if a word in the request matches an alias but the
                                resolved target does not exist, or if no matching
                                target is found and no default applies.
        """
        self._ensure_loaded()
        raw = request.raw_request.lower()
        intent = request.intent

        known_names: list[str] = []
        domain_names: list[str] = []
        if self._registry is not None:
            known_names = self._registry.target_names()
            domain_names = list(self._registry._domain_tools.keys())

        words = self._extract_words(raw)

        # Step 0: Check localhost synonyms first — but ONLY if no other
        # hostname-looking word appears. Pattern "trên máy X" (where X is
        # an unrecognized hostname) should prioritize X over localhost.
        _has_unrecognized_host = self._find_unrecognized_hostname(words)
        for word in words:
            if self._is_localhost_synonym(word):
                if _has_unrecognized_host:
                    break
                if "localhost" in known_names:
                    request.target = "localhost"
                    return
                request.target = "localhost"
                return

        # Step 0.5: Check bad-target cache — if this word failed before, skip it.
        for word in words:
            if word in self._bad_targets:
                raise UnknownTargetError(word, known_names, domain_names)

        # Step 1: Check aliases (fastest path).
        for word in words:
            alias_target = self._aliases.get(word)
            if alias_target:
                if alias_target in known_names:
                    request.target = alias_target
                    return
                self._bad_targets.add(alias_target)
                raise UnknownTargetError(alias_target, known_names, domain_names)

        # Step 2: Try normalized target names via pattern matching.
        for word in words:
            normalized = self.normalize_target_name(word)
            if normalized != word and normalized in known_names:
                request.target = normalized
                return

        # Step 3: Exact substring match (fast path).
        for name in sorted(known_names, key=len, reverse=True):
            if name.lower() in raw:
                request.target = name
                return

        # Step 4: Fuzzy match for typos (slow path).
        best_name: str | None = None
        best_ratio: float = 0.0
        for name in known_names:
            for word in words:
                ratio = difflib.SequenceMatcher(None, name.lower(), word).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_name = name
        if best_name is not None and best_ratio >= 0.6:
            request.target = best_name
            return

        # Step 4.5: Detect potential hostnames that failed all resolution steps.
        # Words like "serverabcxyz" or "server01" should raise an error, not
        # fall through to localhost. Only flag words that look like technical
        # hostnames (contain digits, hyphens, or dots) — pure alphabetic words
        # like "disks" or "check" are not hostnames.
        _prepositions = frozenset({"on", "for", "at", "from"})
        _hostname_pattern = re.compile(r"^[a-z][a-z0-9._-]*$", re.IGNORECASE)
        for word in words:
            if (
                len(word) > 2
                and word not in self._skip_words
                and word not in _prepositions
                and not self._is_localhost_synonym(word)
                and _hostname_pattern.match(word)
                and not word.isalpha()
            ):
                self._bad_targets.add(word)
                raise UnknownTargetError(word, known_names, domain_names)

        # Step 5: Intent + keyword-based defaults.
        if intent is not None and self._registry is not None:
            intent_name = intent.name

            # Dashboard/panel questions -> prefer grafana
            if intent_name == "MONITORING_ASSESSMENT":
                if any(
                    kw in raw
                    for kw in ("dashboard", "panel", "grafana", "biểu đồ", "đồ thị")
                ):
                    if "grafana" in known_names:
                        request.target = "grafana"
                        return
                # Everything else monitoring -> prefer zabbix
                for preferred in ("zabbix", "grafana"):
                    if preferred in known_names:
                        request.target = preferred
                        return

        # Step 6: Check if user explicitly named a target via preposition.
        # If the request mentions "on <name>" or "for <name>" and that
        # name looks like a hostname, raise UnknownTargetError.
        for i, word in enumerate(words):
            if word in _prepositions and i + 1 < len(words):
                candidate = words[i + 1]
                # Also try normalized form before skipping.
                normalized_candidate = self.normalize_target_name(candidate)
                if (
                    len(candidate) > 2
                    and candidate not in self._skip_words
                    and normalized_candidate not in self._skip_words
                ):
                    # If the normalized form matches a known name, use it.
                    if normalized_candidate in known_names:
                        request.target = normalized_candidate
                        return
                    self._bad_targets.add(candidate)
                    raise UnknownTargetError(candidate, known_names, domain_names)

        # Step 7: Fallback — no explicit target found.
        request.target = "localhost"
