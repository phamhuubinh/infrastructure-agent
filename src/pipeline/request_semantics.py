"""Deterministic request semantics for the general-agent routing boundary.

This module deliberately classifies *what kind of information* a request
needs.  It does not select a capability, perform a network call, or decide
which evidence source is available.  Keeping that boundary pure makes the
decision auditable and prevents a model from turning a freshness hint into an
unbounded tool call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from urllib.parse import urlsplit


class RequestDomain(Enum):
    """The user-facing domain of a request, independent of its topic."""

    GENERAL = auto()
    ENVIRONMENT = auto()
    EXTERNAL_INFORMATION = auto()
    CONTENT_GENERATION = auto()
    ACTION = auto()


class InformationScope(Enum):
    """Where the requested information must come from."""

    STABLE_KNOWLEDGE = auto()
    LIVE_ENVIRONMENT = auto()
    CURRENT_EXTERNAL = auto()
    EXPLICIT_URL = auto()


class ExternalNeed(Enum):
    """Whether external verification is semantically required."""

    NONE = auto()
    REQUIRED = auto()
    EXPLICIT = auto()
    URL = auto()


class SourceConstraint(Enum):
    """Named source boundaries recognized before capability planning."""

    ANY = auto()
    LINUX = auto()
    SSH = auto()
    GRAFANA = auto()
    ZABBIX = auto()
    INTERNET = auto()
    URL_ONLY = auto()
    NO_INTERNET = auto()


class ExecutionIntent(Enum):
    """Separate requested content from an attempted environment action."""

    EXPLAIN = auto()
    GENERATE_CONTENT = auto()
    INSPECT_READ_ONLY = auto()
    MUTATE_ENVIRONMENT = auto()


@dataclass(frozen=True, slots=True)
class RequestSemantics:
    """Typed, serializable result of deterministic semantic classification."""

    domain: RequestDomain
    information_scope: InformationScope
    external_need: ExternalNeed
    source_constraints: tuple[SourceConstraint, ...] = (SourceConstraint.ANY,)
    excluded_sources: tuple[SourceConstraint, ...] = ()
    explicit_url: str | None = None
    url_error: str | None = None
    execution_intent: ExecutionIntent = ExecutionIntent.EXPLAIN
    freshness_phrase: str | None = None
    freshness_window: str | None = None


class RequestSemanticsClassifier:
    """Classify request semantics through reviewed VI/EN lexical signals.

    This is intentionally conservative: a request becomes current-external
    only when it has a clear freshness or explicit-verification signal.  A
    phrase such as ``hostname hiện tại`` remains an environment request rather
    than an Internet request.
    """

    _URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
    _URL_PREFIX = re.compile(r"https?://", re.IGNORECASE)
    _TRAILING_URL_PUNCTUATION = ".,;:!?)]}›»"

    _FRESHNESS_PATTERNS: tuple[tuple[str, str], ...] = (
        ("mới nhất", "latest"),
        ("newest", "latest"),
        ("most recent", "latest"),
        ("hiện tại", "current"),
        ("bây giờ", "current"),
        ("ngay bây giờ", "current"),
        ("currently", "current"),
        ("current", "current"),
        ("today", "today"),
        ("hôm nay", "today"),
        ("tonight", "today"),
        ("latest", "latest"),
        ("stable release", "latest"),
        ("release mới", "latest"),
    )
    _FRESHNESS_WINDOWS: dict[str, str] = {
        "today": "same_day",
        "current": "short_lived",
        "latest": "release_current",
    }
    _EXPLICIT_VERIFICATION_MARKERS = (
        "search online",
        "search the web",
        "check online",
        "verify online",
        "verify on the internet",
        "tìm trên web",
        "tìm kiếm trên web",
        "tìm trên internet",
        "kiểm tra trên internet",
        "kiểm chứng trên internet",
        "tra cứu trực tuyến",
        "theo tài liệu mới nhất",
    )
    _EXTERNAL_CURRENT_MARKERS = (
        "giá",
        "price",
        "tỷ giá",
        "exchange rate",
        "thời tiết",
        "weather",
        "tin mới",
        "news",
        "ceo",
        "release",
        "lts",
        "stable",
        "phiên bản",
        "version",
        "lịch",
        "schedule",
        "score",
        "cổ phiếu",
        "stock",
        "bitcoin",
    )
    _LOCAL_ENVIRONMENT_MARKERS = (
        "máy này",
        "máy hiện tại",
        "server này",
        "server hiện tại",
        "this machine",
        "this server",
        "local machine",
        "localhost",
        "target ",
        "trên máy",
        "on host",
        "on server",
    )
    _LOCAL_CURRENT_CONCEPTS = frozenset(
        {
            "cpu",
            "memory",
            "disk",
            "network",
            "hostname",
            "kernel",
            "uptime",
            "load",
            "service",
            "process",
            "container",
            "firewall",
            "ssh",
        }
    )
    _CONCEPTUAL_PATTERNS = (
        " là gì",
        " nghĩa là gì",
        " định nghĩa",
        "giải thích",
        "dùng để làm gì",
        "khác nhau",
        "sự khác biệt",
        "what is",
        "what are",
        "what does",
        "how does",
        "difference between",
        "define ",
    )
    _GENERATION_MARKERS = (
        "viết",
        "tạo",
        "soạn",
        "write",
        "generate",
        "create",
        "example",
        "ví dụ",
        "mẫu",
        "template",
        "hướng dẫn",
        "how to",
        "không chạy",
        "không thực thi",
        "do not run",
        "don't run",
        "without applying",
        "only write",
        "chỉ tạo nội dung",
    )
    _MUTATION_MARKERS = (
        "restart",
        "start service",
        "stop service",
        "disable",
        "enable",
        "delete",
        "remove",
        "kill ",
        "reboot",
        "shutdown",
        "apply ",
        "chạy lệnh",
        "khởi động lại",
        "tắt firewall",
        "xóa",
        "xoá",
        "vô hiệu hóa",
        "áp dụng",
    )
    _DESCRIPTIVE_ACTION_PATTERNS = (
        "last reboot",
        "lần reboot gần nhất",
        "kể từ lần reboot",
        "when .* restarted",
        "đã restart khi nào",
        "how to restart",
        "cách restart",
    )

    def classify(
        self,
        raw_request: str,
        *,
        concepts: tuple[str, ...] = (),
        target_raw: str | None = None,
    ) -> RequestSemantics:
        lower = raw_request.casefold()
        explicit_url, url_error = self._extract_url(raw_request)
        source_constraints, excluded_sources = self._source_constraints(lower)
        execution_intent = self._execution_intent(lower)
        freshness_phrase, freshness_window = self._freshness(lower)

        if explicit_url is not None or url_error is not None:
            return RequestSemantics(
                domain=RequestDomain.EXTERNAL_INFORMATION,
                information_scope=InformationScope.EXPLICIT_URL,
                external_need=ExternalNeed.URL,
                source_constraints=(SourceConstraint.URL_ONLY,),
                excluded_sources=excluded_sources,
                explicit_url=explicit_url,
                url_error=url_error,
                execution_intent=execution_intent,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        if execution_intent is ExecutionIntent.MUTATE_ENVIRONMENT:
            return RequestSemantics(
                domain=RequestDomain.ACTION,
                information_scope=InformationScope.LIVE_ENVIRONMENT,
                external_need=ExternalNeed.NONE,
                source_constraints=source_constraints,
                excluded_sources=excluded_sources,
                execution_intent=execution_intent,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        if execution_intent is ExecutionIntent.GENERATE_CONTENT:
            return RequestSemantics(
                domain=RequestDomain.CONTENT_GENERATION,
                information_scope=InformationScope.STABLE_KNOWLEDGE,
                external_need=ExternalNeed.NONE,
                source_constraints=source_constraints,
                excluded_sources=excluded_sources,
                execution_intent=execution_intent,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        if execution_intent is ExecutionIntent.INSPECT_READ_ONLY:
            return RequestSemantics(
                domain=RequestDomain.ENVIRONMENT,
                information_scope=InformationScope.LIVE_ENVIRONMENT,
                external_need=ExternalNeed.NONE,
                source_constraints=source_constraints,
                excluded_sources=excluded_sources,
                execution_intent=execution_intent,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        explicit_external = any(
            marker in lower for marker in self._EXPLICIT_VERIFICATION_MARKERS
        ) or SourceConstraint.INTERNET in source_constraints
        local_current = self._is_local_current(
            lower,
            concepts=concepts,
            target_raw=target_raw,
            freshness_phrase=freshness_phrase,
        )
        external_current = freshness_phrase is not None and not local_current and (
            any(marker in lower for marker in self._EXTERNAL_CURRENT_MARKERS)
            or freshness_phrase in {"latest", "today"}
        )
        if explicit_external or external_current:
            return RequestSemantics(
                domain=RequestDomain.EXTERNAL_INFORMATION,
                information_scope=InformationScope.CURRENT_EXTERNAL,
                external_need=(
                    ExternalNeed.EXPLICIT if explicit_external else ExternalNeed.REQUIRED
                ),
                source_constraints=source_constraints,
                excluded_sources=excluded_sources,
                execution_intent=ExecutionIntent.EXPLAIN,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        if local_current:
            return RequestSemantics(
                domain=RequestDomain.ENVIRONMENT,
                information_scope=InformationScope.LIVE_ENVIRONMENT,
                external_need=ExternalNeed.NONE,
                source_constraints=source_constraints,
                excluded_sources=excluded_sources,
                execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        if self._is_conceptual(lower, freshness_phrase=freshness_phrase):
            return RequestSemantics(
                domain=RequestDomain.GENERAL,
                information_scope=InformationScope.STABLE_KNOWLEDGE,
                external_need=ExternalNeed.NONE,
                source_constraints=source_constraints,
                excluded_sources=excluded_sources,
                execution_intent=ExecutionIntent.EXPLAIN,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        if self._looks_like_environment_request(lower, concepts, target_raw):
            return RequestSemantics(
                domain=RequestDomain.ENVIRONMENT,
                information_scope=InformationScope.LIVE_ENVIRONMENT,
                external_need=ExternalNeed.NONE,
                source_constraints=source_constraints,
                excluded_sources=excluded_sources,
                execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
                freshness_phrase=freshness_phrase,
                freshness_window=freshness_window,
            )

        # Preserve the pre-existing fail-closed ambiguity behavior for unknown
        # requests.  General-chat expansion is opt-in via explicit conceptual,
        # conversational, or content-generation signals above; otherwise the
        # normal intent resolver can still request clarification.
        return RequestSemantics(
            domain=RequestDomain.ENVIRONMENT,
            information_scope=InformationScope.LIVE_ENVIRONMENT,
            external_need=ExternalNeed.NONE,
            source_constraints=source_constraints,
            excluded_sources=excluded_sources,
            execution_intent=ExecutionIntent.EXPLAIN,
            freshness_phrase=freshness_phrase,
            freshness_window=freshness_window,
        )

    def _extract_url(self, raw_request: str) -> tuple[str | None, str | None]:
        match = self._URL.search(raw_request)
        if match is None:
            if self._URL_PREFIX.search(raw_request):
                return None, "Malformed HTTP/HTTPS URL."
            return None, None
        candidate = match.group(0).rstrip(self._TRAILING_URL_PUNCTUATION)
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            return None, "Malformed HTTP/HTTPS URL."
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None, "Malformed HTTP/HTTPS URL."
        return candidate, None

    def _source_constraints(
        self, lower: str
    ) -> tuple[tuple[SourceConstraint, ...], tuple[SourceConstraint, ...]]:
        allowed: list[SourceConstraint] = []
        excluded: list[SourceConstraint] = []

        mappings: tuple[tuple[SourceConstraint, tuple[str, ...]], ...] = (
            (SourceConstraint.GRAFANA, ("grafana only", "chỉ dùng grafana", "chỉ qua grafana")),
            (SourceConstraint.ZABBIX, ("zabbix only", "chỉ dùng zabbix", "chỉ qua zabbix")),
            (SourceConstraint.SSH, ("ssh only", "chỉ qua ssh", "chỉ dùng ssh")),
            (SourceConstraint.LINUX, ("linux only", "chỉ dùng linux", "chỉ qua linux")),
            (SourceConstraint.INTERNET, ("internet only", "web only", "chỉ dùng internet", "chỉ dùng web")),
        )
        for source, phrases in mappings:
            if any(phrase in lower for phrase in phrases):
                allowed.append(source)

        if "không dùng internet" in lower or "no internet" in lower:
            allowed.append(SourceConstraint.NO_INTERNET)
        negative_mappings: tuple[tuple[SourceConstraint, tuple[str, ...]], ...] = (
            (SourceConstraint.GRAFANA, ("không dùng grafana", "no grafana")),
            (SourceConstraint.ZABBIX, ("không dùng zabbix", "no zabbix")),
            (SourceConstraint.SSH, ("không dùng ssh", "no ssh")),
            (SourceConstraint.LINUX, ("không dùng linux", "no linux")),
            (SourceConstraint.INTERNET, ("không dùng internet", "no internet", "không dùng web", "no web")),
        )
        for source, phrases in negative_mappings:
            if any(phrase in lower for phrase in phrases):
                excluded.append(source)

        # A named Grafana/Zabbix comparison is a reviewed multi-source allow-set,
        # not a request to fall back to an arbitrary third source.
        comparison = ("so sánh", "compare", " versus ", " vs ")
        if any(marker in lower for marker in comparison):
            mentioned = [
                source
                for source, word in (
                    (SourceConstraint.GRAFANA, "grafana"),
                    (SourceConstraint.ZABBIX, "zabbix"),
                    (SourceConstraint.SSH, "ssh"),
                    (SourceConstraint.LINUX, "linux"),
                )
                if word in lower
            ]
            if len(mentioned) >= 2:
                allowed.extend(mentioned)

        return (
            tuple(dict.fromkeys(allowed)) or (SourceConstraint.ANY,),
            tuple(dict.fromkeys(excluded)),
        )

    def _execution_intent(self, lower: str) -> ExecutionIntent:
        if any(marker in lower for marker in self._GENERATION_MARKERS):
            return ExecutionIntent.GENERATE_CONTENT
        if any(re.search(pattern, lower) for pattern in self._DESCRIPTIVE_ACTION_PATTERNS):
            return ExecutionIntent.INSPECT_READ_ONLY
        if any(marker in lower for marker in self._MUTATION_MARKERS):
            return ExecutionIntent.MUTATE_ENVIRONMENT
        return ExecutionIntent.EXPLAIN

    def _freshness(self, lower: str) -> tuple[str | None, str | None]:
        for phrase, kind in self._FRESHNESS_PATTERNS:
            if phrase in lower:
                return phrase, self._FRESHNESS_WINDOWS[kind]
        return None, None

    def _is_local_current(
        self,
        lower: str,
        *,
        concepts: tuple[str, ...],
        target_raw: str | None,
        freshness_phrase: str | None,
    ) -> bool:
        if freshness_phrase is None:
            return False
        # The legacy target extractor intentionally recognizes ``của X`` for
        # infrastructure phrases.  For "CEO hiện tại của Microsoft", however,
        # X is the subject of an external fact, not an environment target.
        if any(marker in lower for marker in self._EXTERNAL_CURRENT_MARKERS):
            return False
        if target_raw or any(marker in lower for marker in self._LOCAL_ENVIRONMENT_MARKERS):
            return True
        if any(marker in lower for marker in ("latest", "mới nhất", "stable", "release")):
            return False
        return bool(set(concepts) & self._LOCAL_CURRENT_CONCEPTS)

    def _is_conceptual(self, lower: str, *, freshness_phrase: str | None) -> bool:
        # "Hostname hiện tại là gì?" asks for a live value.  It shares a
        # definition-shaped suffix with "Hostname là gì?", so currentness
        # wins before the conceptual fallback.
        if freshness_phrase is not None:
            return False
        return any(marker in lower for marker in self._CONCEPTUAL_PATTERNS)

    def _looks_like_environment_request(
        self,
        lower: str,
        concepts: tuple[str, ...],
        target_raw: str | None,
    ) -> bool:
        if target_raw:
            return True
        if any(marker in lower for marker in self._LOCAL_ENVIRONMENT_MARKERS):
            return True
        return bool(set(concepts) & self._LOCAL_CURRENT_CONCEPTS) or any(
            marker in lower
            for marker in (
                "kiểm tra",
                "xem ",
                "trạng thái",
                "đang dùng",
                "đang chạy",
                "đang listen",
                "check ",
                "show ",
                "running ",
                "listen",
                "usage",
                "health",
            )
        ) and bool(set(concepts) & self._LOCAL_CURRENT_CONCEPTS)
