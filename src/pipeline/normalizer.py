from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from src.pipeline.semantic_request import SemanticRequest

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

        semantic = self.normalize(state.user_request)
        update: StateUpdate = {"semantic_request": semantic}
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
                    syn_lower = str(syn).lower().strip()
                    if syn_lower:
                        self._concept_map[syn_lower] = {
                            "concept": concept_name,
                            "category": meta.get("category", ""),
                            "display": meta.get("display", concept_name),
                        }

        actions = data.get("actions", {})
        for action_name, meta in actions.items():
            if not isinstance(meta, dict):
                continue
            synonyms = meta.get("synonyms", [])
            for syn in synonyms:
                syn_lower = str(syn).lower().strip()
                if syn_lower:
                    self._action_map[syn_lower] = {
                        "action": action_name,
                    }

    def normalize(self, user_request: str) -> SemanticRequest:
        """Convert raw user text into a SemanticRequest.

        Args:
            user_request: The raw user input string.

        Returns:
            A SemanticRequest with concept, action, confidence, and
            matched synonyms.  Falls back to concept="machine",
            action="inspect" when nothing matches.
        """
        if not user_request or not user_request.strip():
            return SemanticRequest(
                concept=_DEFAULT_CONCEPT,
                action=_DEFAULT_ACTION,
                confidence=0.0,
                matched_synonyms=[],
            )

        self._ensure_loaded()
        tokens = self._tokenize(user_request.lower())

        concept, concept_syns = self._match_best(tokens, self._concept_map, "concept")
        action, action_syns = self._match_best(tokens, self._action_map, "action")

        if concept is None:
            concept = _DEFAULT_CONCEPT
        if action is None:
            action = _DEFAULT_ACTION

        all_syns = concept_syns + action_syns
        # Confidence: fraction of found synonym groups.
        # 2 groups (concept + action) → 1.0 if both found, 0.5 if one found.
        confidence = (len(concept_syns) > 0) * 0.5 + (len(action_syns) > 0) * 0.5

        target_raw = self._extract_target(user_request)

        return SemanticRequest(
            concept=concept,
            action=action,
            target_raw=target_raw,
            confidence=confidence,
            matched_synonyms=all_syns,
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
        words = text.split()
        tokens: list[str] = []
        skip_count = 0
        for i, word in enumerate(words):
            if skip_count > 0:
                skip_count -= 1
                continue
            found_phrase = False
            # Try 3-word phrase first.
            if i + 2 < len(words):
                phrase3 = f"{word} {words[i + 1]} {words[i + 2]}"
                if phrase3 in Normalizer._PHRASES:
                    tokens.append(phrase3)
                    skip_count = 2
                    found_phrase = True
            # Try 2-word phrase.
            if not found_phrase and i + 1 < len(words):
                phrase2 = f"{word} {words[i + 1]}"
                if phrase2 in Normalizer._PHRASES:
                    tokens.append(phrase2)
                    skip_count = 1
                    found_phrase = True
            # Always also emit the individual cleaned word.
            cleaned = word.strip(",.!?;:'\"()[]{}<>")
            if cleaned:
                tokens.append(cleaned)
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
            r"(?:on|for|at|from|trên|của)\s+([a-z0-9_-]{2,30})",
            re.IGNORECASE,
        )
        match = pattern.search(raw)
        if match:
            return match.group(1).strip()
        return None
