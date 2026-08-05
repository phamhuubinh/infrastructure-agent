from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from src.pipeline.answer_type import AnswerTypeClassifier
from src.pipeline.parameter_extractor import ParameterExtractor
from src.pipeline.request_frame import RequestFrame
from src.pipeline.semantic_candidate_retriever import (
    SemanticCandidateRetriever,
    normalize_lexical_text,
)

if TYPE_CHECKING:
    from src.shared.pipeline_state import PipelineState

# ---------------------------------------------------------------------------
# Default action when no action keyword is detected.  "inspect" is the
# safest default — it collects fewer capabilities than "diagnose".
# ---------------------------------------------------------------------------
_DEFAULT_ACTION = "inspect"

# ---------------------------------------------------------------------------
# Default concept when nothing matches.  "machine" triggers the broadest
# assessment (MACHINE_ASSESSMENT in the classic pipeline).
# ---------------------------------------------------------------------------
_DEFAULT_CONCEPT = "machine"


class Normalizer:
    """Convert natural language text into a structured SemanticRequest.

    The Normalizer ONLY understands language patterns (synonyms, phrases).
    It has ZERO knowledge of capabilities, evidence items, tool dispatch,
    or what the execution pipeline will do with the result.

    This is a strict separation: Normalizer = language, CapabilityPlanner = capability mapping.

    Responsibilities:
    - tokenize the user request into lowercase words and phrases
    - match concept and action synonyms from config/concepts.yaml
    - build a SemanticRequest with concept, action, confidence, matched_synonyms
    - extract a raw target string (if any) for later resolution by TargetResolver
    - return a StateUpdate dict for immutable state accumulation
    """

    # ------------------------------------------------------------------
    # Immutable pipeline state interface.
    # ------------------------------------------------------------------

    def normalize_state(self, state: PipelineState) -> dict[str, object]:
        """Return an immutable StateUpdate with the semantic_request for the given state.

        Thin adapter that delegates to normalize() using state.user_request.
        """
        from src.shared.pipeline_state import StateUpdate

        frame = self.normalize(state.user_request)
        update: StateUpdate = {
            "request_frame": frame,
            # Compatibility field: both names point to the same canonical frame.
            "semantic_request": frame,
            "extracted_params": frame.parameters,
            "answer_type": frame.answer_type,
        }
        return update

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the Normalizer.

        Args:
            config_path: Path to concepts.yaml.  Defaults to
                         config/concepts.yaml relative to the repository root.
        """
        if config_path is None:
            # Resolve relative to the source file (src/pipeline/normalizer.py → repo root/config/)
            repo_root = Path(__file__).resolve().parent.parent.parent
            config_path = str(repo_root / "config" / "concepts.yaml")
        self._config_path = config_path
        self._loaded = False
        self._concept_map: dict[str, dict[str, object]] = {}
        self._action_map: dict[str, dict[str, object]] = {}
        self._concept_aliases: dict[str, set[str]] = {}
        self._action_aliases: dict[str, set[str]] = {}
        self._concept_retriever: SemanticCandidateRetriever | None = None
        self._action_retriever: SemanticCandidateRetriever | None = None

    def _ensure_loaded(self) -> None:
        """Lazy-load the concepts YAML config."""
        if self._loaded:
            return
        if not os.path.exists(self._config_path):
            self._loaded = True
            return
        with open(self._config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self._parse_config(data)
        self._loaded = True

    def _parse_config(self, data: dict) -> None:
        """Parse the YAML structure into fast lookup dicts."""
        concepts = data.get("concepts", {})
        for _category, entries in concepts.items():
            if not isinstance(entries, dict):
                continue
            for concept_name, meta in entries.items():
                if not isinstance(meta, dict):
                    continue
                synonyms = meta.get("synonyms", [])
                for syn in synonyms:
                    syn_lower = normalize_lexical_text(str(syn))
                    if syn_lower:
                        self._concept_map[syn_lower] = {
                            "concept": concept_name,
                            "category": meta.get("category", ""),
                            "display": meta.get("display", concept_name),
                        }
                        self._concept_aliases.setdefault(concept_name, set()).add(
                            syn_lower
                        )

        actions = data.get("actions", {})
        for action_name, meta in actions.items():
            if not isinstance(meta, dict):
                continue
            synonyms = meta.get("synonyms", [])
            for syn in synonyms:
                syn_lower = normalize_lexical_text(str(syn))
                if syn_lower:
                    self._action_map[syn_lower] = {
                        "action": action_name,
                    }
                    self._action_aliases.setdefault(action_name, set()).add(
                        syn_lower
                    )

        self._concept_retriever = SemanticCandidateRetriever(self._concept_aliases)
        self._action_retriever = SemanticCandidateRetriever(self._action_aliases)

    def normalize(self, user_request: str) -> RequestFrame:
        """Convert raw user text into the canonical RequestFrame.

        Args:
            user_request: The raw user input string.

        Returns:
            A RequestFrame with concepts, operation, confidence, and
            match evidence. Falls back to concept="machine",
            action="inspect" when nothing matches.
        """
        if not user_request or not user_request.strip():
            params = ParameterExtractor().extract(user_request)
            return RequestFrame(
                raw_request=user_request,
                concepts=(_DEFAULT_CONCEPT,),
                operation=_DEFAULT_ACTION,
                parameters=params,
                answer_type=AnswerTypeClassifier().classify(user_request),
                confidence=0.0,
            )

        self._ensure_loaded()
        normalized_text = normalize_lexical_text(user_request)
        tokens = self._tokenize(normalized_text)

        concept_matches = self._match_all(tokens, self._concept_map, "concept")
        action, action_syns = self._match_best(tokens, self._action_map, "action")

        concept_candidates = (
            self._concept_retriever.retrieve(normalized_text)
            if self._concept_retriever is not None
            else ()
        )
        action_candidates = (
            self._action_retriever.retrieve(normalized_text)
            if self._action_retriever is not None
            else ()
        )
        ambiguity: list[str] = []

        # A strong typo for a specific subsystem can disambiguate a generic
        # exact word such as "version" ("kernl version" -> kernel, not package).
        if (
            len(concept_matches) == 1
            and concept_matches[0][0] == "package"
            and concept_candidates
        ):
            specific_fuzzy = next(
                (
                    candidate
                    for candidate in concept_candidates
                    if candidate.source == "lexical_fuzzy"
                    and candidate.score >= 0.80
                    and self._CONCEPT_PRIORITY.get(candidate.label, 0)
                    > self._CONCEPT_PRIORITY["package"]
                ),
                None,
            )
            if specific_fuzzy is not None:
                concept_matches = [
                    (specific_fuzzy.label, specific_fuzzy.matched_text)
                ]

        if not concept_matches and self._concept_retriever is not None:
            validation = self._concept_retriever.validate(
                concept_candidates,
                threshold=0.72,
                margin_threshold=0.08,
            )
            if validation.accepted and validation.candidate is not None:
                concept_matches = [
                    (validation.candidate.label, validation.candidate.matched_text)
                ]
            elif validation.reason == "ambiguous_margin":
                ambiguity.append("concept")

        if action is None and self._action_retriever is not None:
            validation = self._action_retriever.validate(
                action_candidates,
                threshold=0.70,
                margin_threshold=0.06,
            )
            if validation.accepted and validation.candidate is not None:
                action = validation.candidate.label
                action_syns = [validation.candidate.matched_text]
            elif validation.reason == "ambiguous_margin":
                ambiguity.append("operation")

        # Explicit subsystem concepts are canonical. A generic machine match
        # is retained only when no more specific concept was mentioned.
        has_specific = any(
            self._CONCEPT_PRIORITY.get(concept, 0) >= 3
            for concept, _ in concept_matches
        )
        if has_specific:
            generic_matches = {
                "service": {
                    "service",
                    "services",
                    "running",
                    "dang chay",
                    "trang thai",
                },
                "package": {
                    "version",
                    "phien ban",
                    "installed",
                    "cai dat",
                },
            }
            concept_matches = [
                (concept, synonym)
                for concept, synonym in concept_matches
                if synonym not in generic_matches.get(concept, set())
            ]
        concepts = [concept for concept, _ in concept_matches]
        if len(concepts) > 1 and _DEFAULT_CONCEPT in concepts:
            concepts = [concept for concept in concepts if concept != _DEFAULT_CONCEPT]
            concept_matches = [
                item for item in concept_matches if item[0] != _DEFAULT_CONCEPT
            ]
        if not concepts:
            concepts = [_DEFAULT_CONCEPT]

        if action is None:
            action = _DEFAULT_ACTION

        concept_syns = [synonym for _, synonym in concept_matches]
        all_syns = concept_syns + action_syns
        # Confidence: fraction of found synonym groups.
        # 2 groups (concept + action) → 1.0 if both found, 0.5 if one found.
        confidence = (len(concept_syns) > 0) * 0.5 + (len(action_syns) > 0) * 0.5

        target_raw = self._extract_target(user_request)
        params = ParameterExtractor().extract(user_request)
        answer_type = AnswerTypeClassifier().classify(
            user_request,
            concepts=tuple(concepts),
            operation=action,
        )

        return RequestFrame(
            raw_request=user_request,
            concepts=tuple(concepts),
            operation=action,
            target_raw=target_raw,
            parameters=params,
            answer_type=answer_type,
            timeframe=getattr(params, "time_range", None),
            confidence=confidence,
            ambiguity=tuple(ambiguity),
            lexical_tokens=tuple(tokens),
            matched_synonyms=tuple(all_syns),
            concept_candidates=concept_candidates,
        )

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------
    _PHRASES: frozenset[str] = frozenset(
        {
            "not working",
            "not responding",
            "io wait",
            "load average",
            "ip address",
            "cấu hình",
            "open port",
            "open ports",
            "memory leak",
            "packet loss",
            "kết nối mạng",
            "băng thông",
            "sự cố",
            "vấn đề",
            "nghiêm trọng",
            "ưu tiên",
            "ssh service",
            "time series",
            "running process",
            "dịch vụ",
            "đang chạy",
            "ổ đĩa",
            "ổ cứng",
            "bộ nhớ",
            "bộ xử lý",
            "dung lượng",
            "vi xử lý",
            "trạng thái",
            "phiên bản",
            "cài đặt",
            "ứng dụng",
            "độ trễ",
            "phân tích",
            "cho tôi biết",
            "cho tôi",
            "kiểm tra",
            "máy chủ",
            "tổng quan",
            "what is",
            "what are",
            "how is",
            "how are",
            "what happened",
            "như thế nào",
            "tại sao",
            "vì sao",
            "làm sao",
            "top process",
            "event log",
            "đồ thị",
        }
    )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split text into tokens preserving multi-word phrases.

        Emits both phrase forms and individual words so that
        concept-level synonyms (e.g. "dung lượng" → disk) and
        action-level single-word synonyms (e.g. "check" → inspect)
        can both match from the same input.
        """
        words = [word for word in normalize_lexical_text(text).split() if word]
        tokens: list[str] = list(words)
        for size in (2, 3, 4):
            tokens.extend(
                " ".join(words[index : index + size])
                for index in range(len(words) - size + 1)
            )
        return tokens

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    # Concept priority: domain-specific concepts should win over generic ones.
    # Higher number = higher priority. Used as primary sort, with string
    # length as tiebreaker within the same priority tier.
    _CONCEPT_PRIORITY: dict[str, int] = {
        # Security concepts — most specific, should always win.
        "firewall": 4,
        "ssh": 4,
        "selinux": 4,
        "apparmor": 4,
        # Infrastructure concepts.
        "cpu": 3,
        "memory": 3,
        "disk": 3,
        "network": 3,
        "gpu": 3,
        "hostname": 3,
        "kernel": 3,
        "uptime": 3,
        "load": 3,
        "performance": 3,
        # System concepts.
        "service": 2,
        "process": 2,
        "package": 2,
        "log": 2,
        "container": 2,
        # Monitoring concepts.
        "alerts": 2,
        "dashboards": 2,
        "monitors": 2,
        # Generic — lowest priority.
        "machine": 1,
    }

    _DEFAULT_CONCEPT_PRIORITY: int = 0

    def _match_best(
        self,
        tokens: list[str],
        lookup: dict[str, dict[str, object]],
        field: str,
    ) -> tuple[str | None, list[str]]:
        """Find the best-matching entry from a synonym lookup map.

        Returns (value_for_field, list_of_matched_synonyms).
        Concept matching uses priority first (domain-specific > generic),
        then longest synonym as tiebreaker.
        """
        best_syn: str | None = None
        best_priority = -1
        best_len = 0

        for syn, meta in lookup.items():
            if syn not in tokens:
                continue

            concept_name = str(meta.get(field, ""))
            priority = self._CONCEPT_PRIORITY.get(
                concept_name, self._DEFAULT_CONCEPT_PRIORITY
            )

            # Primary sort: priority. Tiebreaker: longest synonym.
            if priority > best_priority or (
                priority == best_priority and len(syn) > best_len
            ):
                best_syn = syn
                best_priority = priority
                best_len = len(syn)

        if best_syn is None:
            return None, []

        value = str(lookup[best_syn].get(field, ""))
        return value, [best_syn]

    def _match_all(
        self,
        tokens: list[str],
        lookup: dict[str, dict[str, object]],
        field: str,
    ) -> list[tuple[str, str]]:
        """Return one strongest exact synonym for every explicit concept."""
        best: dict[str, str] = {}
        for synonym, metadata in lookup.items():
            if synonym not in tokens:
                continue
            label = str(metadata.get(field, ""))
            current = best.get(label)
            if current is None or len(synonym) > len(current):
                best[label] = synonym
        token_positions = {token: index for index, token in enumerate(tokens)}
        return sorted(
            best.items(),
            key=lambda item: (
                token_positions.get(item[1], len(tokens)),
                -self._CONCEPT_PRIORITY.get(item[0], self._DEFAULT_CONCEPT_PRIORITY),
                item[0],
            ),
        )

    # ------------------------------------------------------------------
    # Target extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_target(raw: str) -> str | None:
        """Extract a raw target name from prepositional patterns.

        Looks for patterns like:
          "on server01", "for zabbix", "at mon01"
        as well as Vietnamese patterns like:
          "trên server01", "của server01"

        Returns None if no target-like word is found.
        """
        # Preposition markers: "on <X>", "for <X>", "at <X>", "from <X>",
        # "trên <X>", "của <X>"
        pattern = re.compile(
            r"\b(?:on|for|at|from|trên|của)\s+([a-z0-9_-]{2,30})",
            re.IGNORECASE,
        )
        match = pattern.search(raw)
        if match:
            candidate = match.group(1).strip()
            if candidate.casefold() in {"server", "host", "machine", "máy"}:
                return None
            return candidate
        return None
