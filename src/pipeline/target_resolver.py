from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import yaml

from src.pipeline.alias_store import AliasStore
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_frame import RequestFrame
from src.pipeline.semantic_candidate_retriever import normalize_lexical_text

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


class AmbiguousTargetError(ValueError):
    """Raised when multiple validated target candidates are too close."""

    def __init__(self, raw_target: str, candidates: tuple[str, ...]) -> None:
        self.raw_target = raw_target
        self.candidates = candidates[:3]
        super().__init__(
            f"Ambiguous target: '{raw_target}'. Candidates: "
            f"{', '.join(self.candidates)}"
        )


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    target: str
    score: float
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.target,
            "score": round(self.score, 4),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class TargetResolution:
    target: str
    score: float
    candidates: tuple[TargetCandidate, ...]
    ambiguity_margin: float | None
    request_frame: RequestFrame


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
        *,
        fuzzy_threshold: float = 0.78,
        ambiguity_margin: float = 0.10,
        alias_store: AliasStore | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
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
        self._alias_store = alias_store
        self._fuzzy_threshold = fuzzy_threshold
        self._ambiguity_margin = ambiguity_margin
        self._session_id = session_id
        self._user_id = user_id
        self._project_id = project_id
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
            if self._alias_store is None:
                self._alias_store = AliasStore.from_config(self._aliases)
            self._skip_words = frozenset(data.get("skip_words", []))
            self._localhost_synonyms = list(
                data.get("localhost_synonyms", self._DEFAULT_LOCALHOST_SYNONYMS)
            )
            self._target_patterns = list(
                data.get("target_patterns", self._DEFAULT_TARGET_PATTERNS)
            )
        else:
            self._aliases = dict(self._DEFAULT_ALIASES)
            if self._alias_store is None:
                self._alias_store = AliasStore.from_config(self._aliases)
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

    def _known_targets(self) -> tuple[list[str], list[str]]:
        if self._registry is None:
            return [], []
        return (
            self._registry.target_names(),
            list(self._registry._domain_tools.keys()),
        )

    def _explicit_target_candidate(
        self,
        frame: RequestFrame,
        known_names: list[str],
    ) -> str | None:
        """Extract only explicit target mentions from the canonical frame."""
        if frame.target_raw:
            return frame.target_raw.casefold()

        raw = normalize_lexical_text(frame.raw_request)
        words = self._extract_words(raw)
        known_by_normalized = {
            normalize_lexical_text(name): name for name in known_names
        }

        # Exact registered names are stronger than any fuzzy or default route.
        for word in words:
            if word in known_by_normalized:
                return word

        # Local aliases may be multi-word phrases ("máy này" -> "may nay").
        for synonym in self._localhost_synonyms:
            normalized = normalize_lexical_text(synonym)
            if normalized and re.search(rf"\b{re.escape(normalized)}\b", raw):
                # A more specific explicit hostname after "trên máy" wins.
                host_after_machine = re.search(
                    r"\b(?:on|for|at|from|tren|cua)\s+"
                    r"(?:may|server|host)\s+([a-z0-9._-]+)\b",
                    raw,
                )
                if host_after_machine and host_after_machine.group(1) not in {
                    "nay",
                    "hien",
                    "ho",
                    "cai",
                    "giup",
                }:
                    return host_after_machine.group(1)
                return "localhost"

        if self._alias_store is not None:
            for word in words:
                if self._alias_store.resolve(
                    word,
                    session_id=self._session_id,
                    user_id=self._user_id,
                    project_id=self._project_id,
                ):
                    return word

        preposition = re.search(
            r"\b(?:on|for|at|from|tren|cua)\s+([a-z0-9._-]+)\b",
            raw,
        )
        if preposition:
            candidate = preposition.group(1)
            if candidate not in self._skip_words and candidate not in {
                "server",
                "host",
                "may",
            }:
                return candidate

        # Technical hostname tokens must never be silently replaced by localhost.
        for word in words:
            if (
                len(word) > 2
                and word not in self._skip_words
                and re.fullmatch(r"[a-z][a-z0-9._-]*", word)
                and not word.isalpha()
            ):
                return word

        stripped = raw.strip()
        if " " not in stripped and re.fullmatch(r"[a-z0-9][a-z0-9._-]*", stripped):
            return stripped
        return None

    def _resolve_explicit(
        self,
        raw_target: str,
        known_names: list[str],
        domain_names: list[str],
    ) -> tuple[str, float, tuple[TargetCandidate, ...], float | None]:
        candidate = normalize_lexical_text(raw_target)
        if candidate in self._bad_targets:
            raise UnknownTargetError(raw_target, known_names, domain_names)

        if candidate == "localhost" or self._is_localhost_synonym(candidate):
            result = TargetCandidate("localhost", 1.0, "localhost_alias")
            return "localhost", 1.0, (result,), 1.0

        known_by_normalized = {
            normalize_lexical_text(name): name for name in known_names
        }
        if candidate in known_by_normalized:
            target = known_by_normalized[candidate]
            result = TargetCandidate(target, 1.0, "exact")
            return target, 1.0, (result,), 1.0

        if self._alias_store is not None:
            alias = self._alias_store.resolve(
                candidate,
                session_id=self._session_id,
                user_id=self._user_id,
                project_id=self._project_id,
            )
            if alias is not None:
                if alias.target not in known_names:
                    self._bad_targets.add(candidate)
                    raise UnknownTargetError(raw_target, known_names, domain_names)
                result = TargetCandidate(alias.target, 1.0, "scoped_alias")
                return alias.target, 1.0, (result,), 1.0

        normalized = self.normalize_target_name(candidate)
        if normalized in known_by_normalized:
            target = known_by_normalized[normalized]
            result = TargetCandidate(target, 0.99, "name_pattern")
            return target, 0.99, (result,), 0.99

        ranked = tuple(
            sorted(
                (
                    TargetCandidate(
                        target=name,
                        score=difflib.SequenceMatcher(
                            None, candidate, normalize_lexical_text(name)
                        ).ratio(),
                        source="lexical_fuzzy",
                    )
                    for name in known_names
                ),
                key=lambda item: (-item.score, item.target),
            )
        )
        top = ranked[0] if ranked else None
        second = ranked[1] if len(ranked) > 1 else None
        margin = (
            top.score - second.score
            if top is not None and second is not None
            else (top.score if top is not None else None)
        )
        if top is not None and top.score >= self._fuzzy_threshold:
            if second is not None and margin is not None and margin < self._ambiguity_margin:
                raise AmbiguousTargetError(
                    raw_target, tuple(item.target for item in ranked[:3])
                )
            return top.target, top.score, ranked[:3], margin

        self._bad_targets.add(candidate)
        raise UnknownTargetError(raw_target, known_names, domain_names)

    def resolve_frame(
        self,
        frame: RequestFrame,
        *,
        intent: object | None = None,
    ) -> TargetResolution:
        """Resolve a target with exact/alias precedence and threshold+margin guard."""
        self._ensure_loaded()
        known_names, domain_names = self._known_targets()
        explicit = self._explicit_target_candidate(frame, known_names)
        if explicit is not None:
            target, score, candidates, margin = self._resolve_explicit(
                explicit, known_names, domain_names
            )
            enriched = frame.evolve(
                target_raw=frame.target_raw or explicit,
                target_resolved=target,
                target_candidates=candidates,
            )
            return TargetResolution(target, score, candidates, margin, enriched)

        intent_name = getattr(intent, "name", "")
        if intent_name == "MONITORING_ASSESSMENT":
            raw = normalize_lexical_text(frame.raw_request)
            preferred_names = (
                ("grafana", "zabbix")
                if any(term in raw for term in ("dashboard", "panel", "bieu do", "do thi"))
                else ("zabbix", "grafana")
            )
            for preferred in preferred_names:
                if preferred in known_names:
                    result = TargetCandidate(preferred, 0.9, "intent_default")
                    enriched = frame.evolve(
                        target_resolved=preferred,
                        target_candidates=(result,),
                    )
                    return TargetResolution(preferred, 0.9, (result,), 0.9, enriched)

        result = TargetCandidate("localhost", 0.8, "implicit_default")
        enriched = frame.evolve(
            target_resolved="localhost",
            target_candidates=(result,),
        )
        return TargetResolution("localhost", 0.8, (result,), 0.8, enriched)

    # ------------------------------------------------------------------
    # Immutable pipeline state interface.
    # ------------------------------------------------------------------

    def resolve_state(self, state: PipelineState) -> StateUpdate:
        """Return an immutable StateUpdate with the resolved target."""
        frame = state.request_frame
        if not isinstance(frame, RequestFrame):
            from src.pipeline.normalizer import Normalizer

            frame = Normalizer().normalize(state.user_request)
        resolution = self.resolve_frame(frame, intent=state.intent)
        return {
            "request_frame": resolution.request_frame,
            "semantic_request": resolution.request_frame,
            "target": resolution.target,
            "target_candidates": resolution.candidates,
            "target_score": resolution.score,
            "target_margin": resolution.ambiguity_margin,
        }


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
        frame = request.request_frame
        if not isinstance(frame, RequestFrame):
            from src.pipeline.normalizer import Normalizer

            frame = Normalizer().normalize(request.raw_request)
        resolution = self.resolve_frame(frame, intent=request.intent)
        request.target = resolution.target
        request.set_request_frame(resolution.request_frame)
        request.target_candidates = resolution.candidates
        request.target_score = resolution.score
        request.target_margin = resolution.ambiguity_margin
