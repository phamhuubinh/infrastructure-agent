"""Deterministic, bounded execution for external verification.

This module is intentionally a small execution boundary rather than a
general browser agent.  It receives a typed ``RequestFrame`` already routed
by ``ExternalVerificationPolicy`` and can only perform the reviewed flow:

``web_search -> deterministic URL selection -> web_fetch -> evidence``.

The LLM only receives the collected evidence after this module has finished;
it never chooses queries, URLs, or a tool loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance
from src.pipeline.request_frame import RequestFrame
from src.shared.execution.tool_result import ToolResult

if TYPE_CHECKING:
    from src.tool.knowledge_tool import KnowledgeTool


class ExternalContentStatus(str, Enum):
    """Network and extracted-content state are intentionally distinct."""

    FETCH_SUCCESS = "FETCH_SUCCESS"
    CONTENT_EXTRACTED = "CONTENT_EXTRACTED"
    CONTENT_EMPTY = "CONTENT_EMPTY"
    CONTENT_UNSUPPORTED = "CONTENT_UNSUPPORTED"
    CONTENT_TRUNCATED = "CONTENT_TRUNCATED"
    CONTENT_BLOCKED = "CONTENT_BLOCKED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


@dataclass(frozen=True, slots=True)
class ExternalRequestBudget:
    """Hard per-request limits for the Internet verification route."""

    max_search_calls: int = 1
    max_page_fetches: int = 3
    max_total_bytes: int = 1_048_576
    max_elapsed_seconds: float = 25.0
    max_search_results: int = 5
    timeout_seconds: int = 15

    def __post_init__(self) -> None:
        if self.max_search_calls < 0 or self.max_page_fetches < 0:
            raise ValueError("External request call budgets cannot be negative.")
        if self.max_total_bytes < 1:
            raise ValueError("External byte budget must be positive.")
        if self.max_elapsed_seconds <= 0:
            raise ValueError("External elapsed-time budget must be positive.")


@dataclass(slots=True)
class _CacheEntry:
    value: object
    expires_at: float


class ExternalEvidenceCache:
    """Process-local, short-lived cache for successful web observations only."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._entries: dict[tuple[str, ...], _CacheEntry] = {}

    def get(self, key: tuple[str, ...]) -> object | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._clock():
            self._entries.pop(key, None)
            return None
        return entry.value

    def put(self, key: tuple[str, ...], value: object, *, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        self._entries[key] = _CacheEntry(
            value=value,
            expires_at=self._clock() + ttl_seconds,
        )


@dataclass(frozen=True, slots=True)
class ExternalDocument:
    title: str
    url: str
    content: object
    provider: str
    retrieved_at: datetime
    content_type: str | None = None
    truncated: bool = False
    source_type: str = "web-page"
    content_status: ExternalContentStatus = ExternalContentStatus.CONTENT_EXTRACTED

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "provider": self.provider,
            "retrieved_at": self.retrieved_at.isoformat(),
            "content_type": self.content_type,
            "truncated": self.truncated,
            "source_type": self.source_type,
            "content_status": self.content_status.value,
        }


@dataclass(frozen=True, slots=True)
class ExternalVerificationOutcome:
    """The result handed from deterministic collection to assessment."""

    evidence: EvidencePackage | None = None
    documents: tuple[ExternalDocument, ...] = ()
    failures: tuple[str, ...] = ()
    search_calls: int = 0
    fetch_calls: int = 0
    cache_hits: int = 0
    total_bytes: int = 0
    elapsed_ms: float = 0.0

    @property
    def verified(self) -> bool:
        return self.evidence is not None and bool(self.documents)

    @property
    def partial(self) -> bool:
        return self.verified and (
            bool(self.failures)
            or any(
                document.content_status is ExternalContentStatus.CONTENT_TRUNCATED
                for document in self.documents
            )
        )


class ExternalVerificationExecutor:
    """Run an audited external evidence plan through ``KnowledgeTool`` only."""

    def __init__(
        self,
        knowledge_tool: KnowledgeTool | None,
        *,
        budget: ExternalRequestBudget | None = None,
        cache: ExternalEvidenceCache | None = None,
        now: Callable[[], datetime] | None = None,
        clock: Callable[[], float] | None = None,
        enabled: bool = True,
    ) -> None:
        self._knowledge_tool = knowledge_tool
        self._budget = budget or ExternalRequestBudget()
        self._cache = cache or ExternalEvidenceCache(clock=clock)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._clock = clock or time.monotonic
        self._enabled = enabled

    def collect(
        self,
        frame: RequestFrame,
        user_request: str,
    ) -> ExternalVerificationOutcome:
        """Collect external evidence, never falling back to model knowledge."""

        started = self._clock()
        if not self._enabled:
            return self._failure(
                "External verification is disabled by rollout configuration.",
                started,
            )
        if frame.url_error:
            return self._failure(frame.url_error, started)
        if not self._internet_allowed(frame):
            return self._failure(
                "External verification conflicts with the no-Internet source constraint.",
                started,
            )
        source = self._internet_source()
        if source is None:
            return self._failure(
                "Internet source is not configured; no external evidence was collected.",
                started,
            )

        calls = {"search": 0, "fetch": 0, "cache": 0, "bytes": 0}
        failures: list[str] = []
        documents: list[ExternalDocument] = []

        if frame.explicit_url:
            document, error = self._fetch_document(
                source=source,
                title="User-provided URL",
                url=frame.explicit_url,
                provider="direct-url",
                freshness_key=self._freshness_key(frame),
                started=started,
                calls=calls,
            )
            if document is not None:
                documents.append(document)
            elif error:
                failures.append(error)
            return self._outcome(
                frame=frame,
                query=None,
                provider="direct-url",
                documents=documents,
                failures=failures,
                started=started,
                calls=calls,
            )

        if self._expired(started):
            return self._failure("External verification time budget was exhausted.", started)
        if self._budget.max_search_calls < 1:
            return self._failure("External search-call budget is zero.", started)

        query = self._query_for(frame, user_request)
        locale = self._locale_for(user_request)
        search_key = (
            "search",
            source,
            self._provider_identity(source),
            query,
            locale or "",
            self._freshness_key(frame),
        )
        search_payload = self._cache.get(search_key)
        if isinstance(search_payload, dict):
            calls["cache"] += 1
        else:
            calls["search"] += 1
            result = self._execute(
                source,
                "web_search",
                query=query,
                locale=locale,
                max_results=self._budget.max_search_results,
                timeout=self._budget.timeout_seconds,
            )
            if not result.success or not isinstance(result.data, dict):
                return self._failure(
                    result.error or "External search failed.",
                    started,
                    calls=calls,
                )
            search_payload = result.data
            # Only complete provider responses are cacheable.  Error/partial
            # results must not be revived as valid current evidence.
            if search_payload.get("status") == "ok":
                self._cache.put(
                    search_key,
                    search_payload,
                    ttl_seconds=self._cache_ttl(frame),
                )

        provider = str(search_payload.get("provider") or "unknown-provider")
        selected = self._select_results(search_payload)
        if not selected:
            return self._failure(
                "External search returned no public result URLs to fetch.",
                started,
                calls=calls,
            )
        for item in selected:
            if calls["fetch"] >= self._budget.max_page_fetches:
                failures.append("Page-fetch budget was exhausted before all selected results.")
                break
            if self._expired(started):
                failures.append("External verification time budget was exhausted.")
                break
            document, error = self._fetch_document(
                source=source,
                title=str(item["title"]),
                url=str(item["url"]),
                provider=provider,
                freshness_key=self._freshness_key(frame),
                started=started,
                calls=calls,
            )
            if document is not None:
                documents.append(document)
            elif error:
                failures.append(error)

        return self._outcome(
            frame=frame,
            query=query,
            provider=provider,
            documents=documents,
            failures=failures,
            started=started,
            calls=calls,
        )

    def _outcome(
        self,
        *,
        frame: RequestFrame,
        query: str | None,
        provider: str,
        documents: list[ExternalDocument],
        failures: list[str],
        started: float,
        calls: dict[str, int],
    ) -> ExternalVerificationOutcome:
        if not documents:
            return self._failure(
                failures[0] if failures else "No external page content could be verified.",
                started,
                calls=calls,
            )
        evidence = self._build_evidence(
            frame=frame,
            query=query,
            provider=provider,
            documents=documents,
            failures=failures,
        )
        return ExternalVerificationOutcome(
            evidence=evidence,
            documents=tuple(documents),
            failures=tuple(failures),
            search_calls=calls["search"],
            fetch_calls=calls["fetch"],
            cache_hits=calls["cache"],
            total_bytes=calls["bytes"],
            elapsed_ms=(self._clock() - started) * 1000,
        )

    def _failure(
        self,
        reason: str,
        started: float,
        *,
        calls: dict[str, int] | None = None,
    ) -> ExternalVerificationOutcome:
        values = calls or {"search": 0, "fetch": 0, "cache": 0, "bytes": 0}
        return ExternalVerificationOutcome(
            failures=(reason,),
            search_calls=values["search"],
            fetch_calls=values["fetch"],
            cache_hits=values["cache"],
            total_bytes=values["bytes"],
            elapsed_ms=(self._clock() - started) * 1000,
        )

    def _internet_allowed(self, frame: RequestFrame) -> bool:
        names = {constraint.name for constraint in frame.source_constraints}
        excluded = {constraint.name for constraint in frame.excluded_sources}
        return "NO_INTERNET" not in names and "INTERNET" not in excluded

    def _internet_source(self) -> str | None:
        if self._knowledge_tool is None:
            return None
        try:
            names = self._knowledge_tool.source_names()
            return next(
                (
                    name
                    for name in names
                    if self._knowledge_tool.source_kind(name) == "internet"
                ),
                None,
            )
        except (AttributeError, KeyError):
            return None

    def _provider_identity(self, source: str) -> str:
        if self._knowledge_tool is None:
            return "unconfigured"
        try:
            return self._knowledge_tool.source_provider_identity(source)
        except (AttributeError, KeyError):
            return source

    def _execute(self, source: str, resource: str, **arguments: object) -> ToolResult:
        if self._knowledge_tool is None:
            raise RuntimeError("Internet source is not configured.")
        return self._knowledge_tool.execute(
            {"source": source, "resource": resource, **arguments}
        )

    def _fetch_document(
        self,
        *,
        source: str,
        title: str,
        url: str,
        provider: str,
        freshness_key: str,
        started: float,
        calls: dict[str, int],
    ) -> tuple[ExternalDocument | None, str | None]:
        canonical = self._canonical_public_url(url)
        if canonical is None:
            return None, "Search result URL is not a public HTTP/HTTPS URL."
        cache_key = ("fetch", provider, canonical, freshness_key)
        cached = self._cache.get(cache_key)
        if isinstance(cached, ExternalDocument):
            calls["cache"] += 1
            return cached, None
        remaining = self._budget.max_total_bytes - calls["bytes"]
        if remaining <= 0:
            return None, "External byte budget was exhausted."
        if self._expired(started):
            return None, "External verification time budget was exhausted."
        calls["fetch"] += 1
        result = self._execute(
            source,
            "web_fetch",
            url=canonical,
            timeout=self._budget.timeout_seconds,
            max_bytes=min(remaining, 512 * 1024),
        )
        if not result.success or not isinstance(result.data, dict):
            return None, result.error or f"Could not fetch {canonical}."
        payload = result.data
        if payload.get("error") or payload.get("data") is None:
            return None, str(payload.get("error") or f"Could not fetch {canonical}.")
        raw_status = str(payload.get("content_status") or "")
        try:
            content_status = ExternalContentStatus(raw_status)
        except ValueError:
            # Third-party capability implementations may predate the typed
            # field.  Their payload is accepted only after the same explicit
            # content check used for native InternetTool responses.
            content = payload.get("data")
            content_status = (
                ExternalContentStatus.CONTENT_EMPTY
                if content in (None, "", {}, [])
                else (
                    ExternalContentStatus.CONTENT_TRUNCATED
                    if bool(payload.get("truncated", False))
                    else ExternalContentStatus.CONTENT_EXTRACTED
                )
            )
        if content_status in {
            ExternalContentStatus.CONTENT_EMPTY,
            ExternalContentStatus.CONTENT_UNSUPPORTED,
            ExternalContentStatus.CONTENT_BLOCKED,
            ExternalContentStatus.EXTRACTION_FAILED,
        }:
            return None, (
                f"Fetched {canonical} but usable page content is unavailable "
                f"({content_status.value})."
            )
        content_length = payload.get("content_length", 0)
        if isinstance(content_length, int):
            calls["bytes"] += max(content_length, 0)
        fetched_url = payload.get("url")
        if not isinstance(fetched_url, str):
            fetched_url = canonical
        document = ExternalDocument(
            title=title[:500],
            url=fetched_url,
            content=payload["data"],
            provider=provider,
            retrieved_at=self._now(),
            content_type=(
                str(payload["content_type"])[:200]
                if payload.get("content_type") is not None
                else None
            ),
            truncated=bool(payload.get("truncated", False)),
            content_status=content_status,
        )
        # A successful but truncated response is useful evidence with an
        # explicit limitation.  It can be cached, unlike any failure.
        self._cache.put(cache_key, document, ttl_seconds=self._cache_ttl_from_key(freshness_key))
        return document, None

    @staticmethod
    def _canonical_public_url(url: str) -> str | None:
        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        host = parsed.hostname.casefold()
        netloc = host if port is None else f"{host}:{port}"
        path = parsed.path or "/"
        return urlunsplit((parsed.scheme, netloc, path, parsed.query, ""))

    def _select_results(self, payload: dict[str, object]) -> tuple[dict[str, str], ...]:
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            return ()
        unique_urls: set[str] = set()
        seen_domains: set[str] = set()
        diverse: list[dict[str, str]] = []
        remaining: list[dict[str, str]] = []
        for raw in raw_results[: self._budget.max_search_results]:
            if not isinstance(raw, dict):
                continue
            raw_url = raw.get("url")
            if not isinstance(raw_url, str):
                continue
            canonical = self._canonical_public_url(raw_url)
            if canonical is None or canonical in unique_urls:
                continue
            unique_urls.add(canonical)
            title = str(raw.get("title") or canonical)
            candidate = {"title": title, "url": canonical}
            domain = urlsplit(canonical).hostname or ""
            if domain not in seen_domains:
                seen_domains.add(domain)
                diverse.append(candidate)
            else:
                remaining.append(candidate)
        selected = diverse + remaining
        return tuple(selected[: self._budget.max_page_fetches])

    def _build_evidence(
        self,
        *,
        frame: RequestFrame,
        query: str | None,
        provider: str,
        documents: list[ExternalDocument],
        failures: list[str],
    ) -> EvidencePackage:
        facts: list[Fact] = []
        for document in documents:
            target = urlsplit(document.url).hostname or "internet"
            provenance = Provenance(
                source="internet",
                capability="web_fetch",
                target=target,
                observed_at=document.retrieved_at,
                source_reference=document.url,
                parameters=(("provider", document.provider), ("query", query or "")),
            )
            facts.append(
                Fact(
                    subject="external_document",
                    metric="external.document.retrieved",
                    value=document.url,
                    unit="url",
                    observed_at=document.retrieved_at,
                    collected_at=document.retrieved_at,
                    source="internet",
                    target=target,
                    validity=FactValidity.VALID,
                    freshness=FactFreshness.FRESH,
                    confidence=1.0,
                    provenance=provenance,
                    dimensions={
                        "provider": document.provider,
                        "content_type": document.content_type or "",
                        "truncated": document.truncated,
                        "content_status": document.content_status.value,
                    },
                )
            )
        has_truncation = any(document.truncated for document in documents)
        warnings = list(failures)
        if has_truncation:
            warnings.append("One or more web responses were truncated to the configured byte limit.")
        retrieved_at = max(document.retrieved_at for document in documents)
        return EvidencePackage(
            capability_name="external_verification",
            evidence_name="external_current" if frame.explicit_url is None else "explicit_url",
            data={
                "query": query,
                "provider": provider,
                "retrieved_at": retrieved_at.isoformat(),
                "documents": [document.to_dict() for document in documents],
            },
            source_tool="internet",
            source="internet",
            resource="web_fetch",
            parameters=(("query", query or ""), ("provider", provider)),
            warnings=tuple(warnings),
            collection_failures=tuple(failures),
            facts=tuple(facts),
        )

    @staticmethod
    def _query_for(frame: RequestFrame, user_request: str) -> str:
        # The original request is the auditable search query; do not ask a
        # model to rewrite it.  Keep a strict bound before it reaches a
        # provider and remove explicit source directives that add no facts.
        compact = " ".join(user_request.split())
        for phrase in ("search online", "search the web", "tìm trên web", "tìm trên internet"):
            compact = compact.replace(phrase, "")
        return compact.strip()[:1000] or "current information"

    @staticmethod
    def _locale_for(user_request: str) -> str | None:
        vi_chars = "àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
        return "vi-VN" if any(char in user_request.casefold() for char in vi_chars) else None

    @staticmethod
    def _freshness_key(frame: RequestFrame) -> str:
        return frame.freshness_window or "explicit"

    def _cache_ttl(self, frame: RequestFrame) -> float:
        return self._cache_ttl_from_key(self._freshness_key(frame))

    @staticmethod
    def _cache_ttl_from_key(key: str) -> float:
        return {
            "same_day": 300.0,
            "short_lived": 300.0,
            "release_current": 3600.0,
            "explicit": 300.0,
        }.get(key, 300.0)

    def _expired(self, started: float) -> bool:
        return (self._clock() - started) >= self._budget.max_elapsed_seconds


__all__ = [
    "ExternalContentStatus",
    "ExternalDocument",
    "ExternalEvidenceCache",
    "ExternalRequestBudget",
    "ExternalVerificationExecutor",
    "ExternalVerificationOutcome",
]
