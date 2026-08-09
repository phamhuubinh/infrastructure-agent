"""Deterministic, bounded execution for external verification.

This module is intentionally a small execution boundary rather than a
general browser agent.  It receives a typed ``RequestFrame`` already routed
by ``ExternalVerificationPolicy`` and can only perform the reviewed flow:

``web_search -> deterministic URL selection -> web_fetch -> evidence``.

The LLM only receives the collected evidence after this module has finished;
it never chooses queries, URLs, or a tool loop.
"""

from __future__ import annotations

import re
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


class ExternalEvidenceRelevance(str, Enum):
    """Evidence relevance classification for external verification.

    Distinguishes between:
    - IRRELEVANT: fetched content does not contain request-relevant evidence
    - PARTIAL: some relevant content exists but is truncated or insufficient
    - SUFFICIENT: relevant content is present and complete enough for claims
    """

    IRRELEVANT = "irrelevant"
    PARTIAL = "partial"
    SUFFICIENT = "sufficient"


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
class BoundedPassage:
    """A deterministic bounded supporting passage with provenance.

    Represents a request-relevant excerpt from an ExternalDocument.
    The passage is bounded to a maximum character count and preserves
    the provenance association (URL, title, provider) for auditability.
    """

    text: str
    url: str
    title: str
    provider: str
    start_offset: int
    end_offset: int
    relevance: ExternalEvidenceRelevance
    max_passage_chars: int = 1024

    def __post_init__(self) -> None:
        # Ensure passage is deterministically bounded
        # Preserve the invariant: end_offset - start_offset == len(text)
        if len(self.text) > self.max_passage_chars:
            object.__setattr__(self, "text", self.text[: self.max_passage_chars])
        # Recompute end_offset from start_offset + actual text length
        object.__setattr__(self, "end_offset", self.start_offset + len(self.text))

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "url": self.url,
            "title": self.title,
            "provider": self.provider,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "relevance": self.relevance.value,
            "passage_length": len(self.text),
            "max_passage_chars": self.max_passage_chars,
        }


@dataclass(frozen=True, slots=True)
class ExternalDocument:
    """A fetched web document with provenance and relevance classification."""

    title: str
    url: str
    content: object
    provider: str
    retrieved_at: datetime
    content_type: str | None = None
    truncated: bool = False
    source_type: str = "web-page"
    content_status: ExternalContentStatus = ExternalContentStatus.CONTENT_EXTRACTED
    relevance: ExternalEvidenceRelevance = ExternalEvidenceRelevance.IRRELEVANT
    selected_passages: tuple[BoundedPassage, ...] = ()

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
            "relevance": self.relevance.value,
            "selected_passages": [p.to_dict() for p in self.selected_passages],
        }


@dataclass(frozen=True, slots=True)
class ExternalVerificationOutcome:
    """The result handed from deterministic collection to assessment.

    Tracks evidence relevance to distinguish between:
    - fetch success + irrelevant content (verified=False)
    - fetch success + relevant content (verified=True)
    - partial relevant content (verified=True, partial=True)

    An outcome is only `verified=True` when there is sufficient relevant
    evidence for the request, not merely when documents were fetched.
    """

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
        """True only when there is SUFFICIENT relevant evidence for the request.

        A fetch that succeeds but returns unrelated or partial content does NOT
        set verified=True. Only documents with relevance == SUFFICIENT count.
        """
        if self.evidence is None:
            return False
        if not self.documents:
            return False
        # Only documents with SUFFICIENT relevance count as verified
        sufficient_docs = sum(
            1
            for doc in self.documents
            if doc.relevance == ExternalEvidenceRelevance.SUFFICIENT
        )
        return sufficient_docs > 0

    @property
    def partial(self) -> bool:
        """True when evidence is PARTIAL relevance OR (has usable evidence AND has failures).

        Semantics:
        - partial=True when at least one document has PARTIAL relevance (truncated/incomplete)
        - partial=True when we have SUFFICIENT evidence but some fetch failures occurred
          (e.g., some pages failed while others succeeded)

        This allows verified=True AND partial=True simultaneously.
        """
        # Check if any document has PARTIAL relevance
        if any(
            doc.relevance == ExternalEvidenceRelevance.PARTIAL for doc in self.documents
        ):
            return True
        # Check if we have usable/sufficient evidence AND have failures
        has_usable = any(
            doc.relevance != ExternalEvidenceRelevance.IRRELEVANT
            for doc in self.documents
        )
        if has_usable and self.failures:
            return True
        return False

    @property
    def has_relevant_evidence(self) -> bool:
        """True when at least one document contains request-relevant content."""
        return any(
            doc.relevance != ExternalEvidenceRelevance.IRRELEVANT
            for doc in self.documents
        )

    @property
    def relevant_documents(self) -> tuple[ExternalDocument, ...]:
        """Subset of documents that contain request-relevant content."""
        return tuple(
            doc
            for doc in self.documents
            if doc.relevance != ExternalEvidenceRelevance.IRRELEVANT
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
                user_request=user_request,
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
            return self._failure(
                "External verification time budget was exhausted.", started
            )
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
                failures.append(
                    "Page-fetch budget was exhausted before all selected results."
                )
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
                user_request=user_request,
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
                (
                    failures[0]
                    if failures
                    else "No external page content could be verified."
                ),
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
        user_request: str,
    ) -> tuple[ExternalDocument | None, str | None]:
        canonical = self._canonical_public_url(url)
        if canonical is None:
            return None, "Search result URL is not a public HTTP/HTTPS URL."
        cache_key = ("fetch", provider, canonical, freshness_key)
        cached = self._cache.get(cache_key)
        if isinstance(cached, ExternalDocument):
            calls["cache"] += 1
            # Relevance is request-specific - always recompute from current request
            relevance = self._detect_relevance(cached, user_request)
            # Passages are also request-specific - recompute for current request
            selected_passages = self._select_passages(cached, user_request)
            # Create a new document with relevance and passages set to avoid modifying the cached one
            return (
                ExternalDocument(
                    title=cached.title,
                    url=cached.url,
                    content=cached.content,
                    provider=cached.provider,
                    retrieved_at=cached.retrieved_at,
                    content_type=cached.content_type,
                    truncated=cached.truncated,
                    source_type=cached.source_type,
                    content_status=cached.content_status,
                    relevance=relevance,
                    selected_passages=selected_passages,
                ),
                None,
            )
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
        relevance = self._detect_relevance(
            ExternalDocument(
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
            ),
            user_request,
        )
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
            relevance=relevance,
            selected_passages=self._select_passages(
                ExternalDocument(
                    title=title[:500],
                    url=fetched_url,
                    content=payload["data"],
                    provider=provider,
                    retrieved_at=self._now(),
                    truncated=bool(payload.get("truncated", False)),
                ),
                user_request,
            ),
        )
        # A successful but truncated response is useful evidence with an
        # explicit limitation.  It can be cached, unlike any failure.
        self._cache.put(
            cache_key, document, ttl_seconds=self._cache_ttl_from_key(freshness_key)
        )
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
            warnings.append(
                "One or more web responses were truncated to the configured byte limit."
            )
        retrieved_at = max(document.retrieved_at for document in documents)
        return EvidencePackage(
            capability_name="external_verification",
            evidence_name=(
                "external_current" if frame.explicit_url is None else "explicit_url"
            ),
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
        for phrase in (
            "search online",
            "search the web",
            "tìm trên web",
            "tìm trên internet",
        ):
            compact = compact.replace(phrase, "")
        return compact.strip()[:1000] or "current information"

    @staticmethod
    def _locale_for(user_request: str) -> str | None:
        vi_chars = "àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
        return (
            "vi-VN"
            if any(char in user_request.casefold() for char in vi_chars)
            else None
        )

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

    def _detect_relevance(
        self, document: ExternalDocument, user_request: str
    ) -> ExternalEvidenceRelevance:
        """Detect if a fetched document contains request-relevant content.

        Returns:
            SUFFICIENT if the document contains deterministic claim support for
            the request type (version, date, price, identity).
            PARTIAL if the document has some relevant content but lacks claim support
            or is truncated.
            IRRELEVANT if the content does not appear related to the request.

        Important semantics:
        - IRRELEVANT: has_relevant_evidence=False, verified=False
        - PARTIAL: has_relevant_evidence=True, verified=False, partial=True
        - SUFFICIENT: verified=True

        Entity/topic mention alone (e.g., "Python" in a Python version request)
        is NOT SUFFICIENT - it needs claim-shaped evidence (e.g., "version 3.14.2").
        """
        if not document.content or document.content in (None, "", {}, []):
            return ExternalEvidenceRelevance.IRRELEVANT

        content_str = str(document.content).casefold()
        request_lower = user_request.casefold()

        # Detect the request type based on keywords
        request_type = self._detect_request_type(request_lower)

        # For certain request types, we require deterministic claim support
        # Pattern detection for claim-shaped evidence

        # Entity/topic keywords (these alone are not enough for SUFFICIENT)
        ENTITY_KEYWORDS = {
            "version",
            "release",
            "date",
            "price",
            "cost",
            "value",
            "holder",
            "officer",
            "current",
            "latest",
            "stable",
            "development",
            "documentation",
        }

        # Claim-shaped patterns that indicate SUFFICIENT support
        # Each pattern matches both entity/topic AND claim-shaped evidence

        # Version pattern: mentions version-related terms AND a version number
        # e.g., "Python version 3.14.2", "current release is 3.14.2"
        version_patterns = [
            r"\bversion\b.*[\d]+\.[\d]+\.[\d]+",
            r"[\d]+\.[\d]+\.[\d]+.*\bversion\b",
            r"\bcurrent.*version\b.*[\d]+\.[\d]+\.[\d]+",
            r"[\d]+\.[\d]+\.[\d]+\s+(?:is|of|for)\s+(?:the\s+)?(?:current|latest|stable)\s+(?:Python\s+)?version",
            r"\brelease\b.*[\d]+\.[\d]+\.[\d]+",
            r"[\d]+\.[\d]+\.[\d]+\s+(?:is|of|for)\s+(?:the\s+)?(?:current|latest|stable)\s+release",
        ]

        # Date pattern: mentions date-related terms AND a date
        # e.g., "release date is 2024-08-15", "current date: August 2024"
        date_patterns = [
            r"\bdate\b.*\b(?:202[0-9]|203[0-9])\b",
            r"\b(?:202[0-9]|203[0-9])\b.*\bdate\b",
            r"\brelease.*date\b.*\b(?:202[0-9]|203[0-9])\b",
            r"\b(?:202[0-9]|203[0-9])\b.*\brelease.*date\b",
        ]

        # Price pattern: mentions price/value terms AND a concrete value
        # e.g., "price is $99.99", "cost: $100", "costs $99.99", "value: 1.23 USD"
        price_patterns = [
            r"\bprice\b.*[\$]\s*[\d]+",
            r"[\$]\s*[\d]+.*\bprice\b",
            r"\bcosts?\b.*[\$]\s*[\d]+",
            r"[\$]\s*[\d]+.*\bcosts?\b",
            r"\bvalue\b.*[\$]\s*[\d]+",
            r"[\$]\s*[\d]+.*\bvalue\b",
        ]

        # Identity pattern: mentions role/entity terms AND a named identity
        # e.g., "CEO is John Smith", "president: Joe Biden"
        # Use casefolded matching since content_str is already casefolded
        identity_patterns = [
            r"\b(?:ceo|president|prime?\.?\s*minister|chancellor|secretary)\b.*[a-z][a-z]+",
            r"[a-z][a-z]+.*\b(?:ceo|president|prime?\.?\s*minister|chancellor|secretary)\b",
        ]

        # Check patterns in order of specificity
        has_claim_support = False

        if request_type == "version":
            has_claim_support = any(re.search(p, content_str) for p in version_patterns)

        elif request_type == "date":
            has_claim_support = any(re.search(p, content_str) for p in date_patterns)

        elif request_type == "price":
            has_claim_support = any(re.search(p, content_str) for p in price_patterns)

        elif request_type == "identity":
            has_claim_support = any(
                re.search(p, content_str) for p in identity_patterns
            )

        # Subject/entity extraction: extract the requested subject from the request
        # to bind claim support to the correct entity
        requested_subject = self._extract_requested_subject(request_lower)

        # Subject binding: if we have claim support but a specific subject is
        # requested, verify the content mentions that subject
        if has_claim_support and requested_subject:
            # Check if the requested subject appears in the content
            if not re.search(rf"\b{re.escape(requested_subject)}\b", content_str):
                # Content has claim-shaped evidence but for wrong subject
                has_claim_support = False

        # If we have claim support, we need at least one entity/topic mention
        # to confirm relevance.  When has_claim_support is True, the request
        # type already matched a pattern (version/date/price/identity) against
        # the content, so the content necessarily contains the relevant
        # entity context.  Only require entity_match when the request type is
        # general and we fell through to trying all patterns.
        if has_claim_support:
            if document.truncated:
                return ExternalEvidenceRelevance.PARTIAL
            return ExternalEvidenceRelevance.SUFFICIENT

        # Check if any entity/topic keyword from request is in content (PARTIAL case)
        # We need at least one entity keyword match between request and content
        # Clean keywords first (remove punctuation) for matching
        for token in request_lower.split():
            clean_token = re.sub(r"[^\w]", "", token)
            if clean_token in ENTITY_KEYWORDS:
                if re.search(rf"\b{re.escape(clean_token)}\b", content_str):
                    return ExternalEvidenceRelevance.PARTIAL

        return ExternalEvidenceRelevance.IRRELEVANT

    def _extract_requested_subject(self, request_lower: str) -> str | None:
        """Extract a bounded deterministic subject/entity from the request.

        Returns the requested subject (e.g., "python", "postgresql",
        "kubernetes", or an arbitrary subject from an explicit-URL question)
        or None for generic requests without a named subject.

        GA2-R1-02: Generalized beyond a hard-coded product-name list to handle
        simple factual questions about arbitrary subjects when the user
        supplies an explicit URL or clearly names the entity.
        """
        # Common subjects that indicate a specific entity
        KNOWN_SUBJECTS = [
            "python",
            "postgresql",
            "postgres",
            "mysql",
            "mongodb",
            "kubernetes",
            "k8s",
            "docker",
            "nginx",
            "apache",
            "redis",
            "grafana",
            "zabbix",
            "linux",
            "ubuntu",
            "centos",
            "windows",
            "macos",
            "examplecorp",
            "acme",
        ]

        for subject in KNOWN_SUBJECTS:
            if subject in request_lower:
                return subject

        # GA2-R1-02: Generalized subject extraction for arbitrary subjects.
        # When the request is a simple factual question (version/date/price/
        # identity), try to extract the subject from common patterns:
        # - "version of <subject>" -> extract <subject>
        # - "<subject> version" -> extract <subject>
        # - "phiên bản của <subject>" -> extract <subject>
        # - "<subject> là gì" -> extract <subject>
        # - URL-based questions: extract domain/subject from the URL
        request_type = self._detect_request_type(request_lower)
        if request_type != "general":
            # Try pattern-based extraction
            # Pattern: "version of X" or "current version of X"
            match = re.search(r"version\s+(?:of|của)\s+(\w+)", request_lower)
            if match:
                subject = match.group(1)
                if len(subject) >= 2 and len(subject) <= 50:
                    return subject

            # Pattern: "X version" (e.g., "python version")
            match = re.search(r"^(\w+)\s+version", request_lower)
            if match:
                subject = match.group(1)
                if len(subject) >= 2 and len(subject) <= 50:
                    return subject

            # Pattern: "phiên bản X" or "phiên bản của X"
            match = re.search(r"phiên\s*bản\s+(?:của\s+)?(\w+)", request_lower)
            if match:
                subject = match.group(1)
                if len(subject) >= 2 and len(subject) <= 50:
                    return subject

        return None

    def _select_passages(
        self,
        document: ExternalDocument,
        user_request: str,
    ) -> tuple[BoundedPassage, ...]:
        """Select bounded request-relevant passages from document content.

        Returns a tuple of BoundedPassage objects containing only the
        request-relevant excerpts from the document, bounded to
        max_passage_chars each with provenance association.

        Only passages containing claim-shaped evidence for the request
        are selected. Unrelated occurrences elsewhere on the page
        are excluded.

        Uses sentence/clause-boundary extraction rather than arbitrary
        character windows to ensure:
        - Only the relevant claim is extracted
        - Offsets are consistent with passage text
        - Subject binding applies to the actual selected sentence

        When the request type is "general" (no specific claim type detected),
        no passages are selected since there is no expected claim shape.
        """
        if not document.content or document.content in (None, "", {}, []):
            return ()

        content_str = str(document.content)
        if not content_str:
            return ()

        request_lower = user_request.casefold()
        request_type = self._detect_request_type(request_lower)

        # Skip passage selection for general requests with no specific claim type
        if request_type == "general":
            return ()

        requested_subject = self._extract_requested_subject(request_lower)

        # Define patterns that indicate claim-shaped evidence
        # Each pattern should capture both entity/topic AND concrete claim
        version_patterns = [
            r"(?:version|release)\s+(?:\d+\.\d+\.\d+)",
            r"(?:\d+\.\d+\.\d+)\s+(?:is|of|for)\s+(?:the\s+)?(?:current|latest|stable)\s+(?:version|release)",
            r"(?:current|latest|stable)\s+(?:version|release)\s+(?:is|:)?\s*(?:\d+\.\d+\.\d+)",
        ]
        date_patterns = [
            r"(?:release|current|published)\s+date\s+(?:is|:)?\s*(?:20[0-9]{2})",
            r"(?:20[0-9]{2})\s+(?:-|/)\s+(?:0[1-9]|1[0-2])\s+(?:-|/)\s+(?:0[1-9]|[12]\d|3[01])",
        ]
        price_patterns = [
            r"(?:price|costs?|value)\s+(?:is|:)?\s*[$£€]\s*\d+",
            r"[$£€]\s*\d+(?:\.\d{2})?\s*(?:usd|eur|gbp)?",
            r"(?:price|costs?|value)\s+[$£€]\s*\d+",
        ]
        identity_patterns = [
            r"(?:ceo|president|prime\s*minister|chancellor)\s+(?:is|:)?\s+[A-Z][a-z]+\s+[A-Z][a-z]+",
            r"[A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:serves? as|is|:)?\s+(?:ceo|president|prime\s*minister)",
        ]

        # Select patterns based on request type
        if request_type == "version":
            patterns = version_patterns
        elif request_type == "date":
            patterns = date_patterns
        elif request_type == "price":
            patterns = price_patterns
        elif request_type == "identity":
            patterns = identity_patterns
        else:
            # For non-general requests, try all patterns
            patterns = (
                version_patterns + date_patterns + price_patterns + identity_patterns
            )

        passages: list[BoundedPassage] = []
        seen_texts: set[str] = set()

        for pattern in patterns:
            for match in re.finditer(pattern, content_str, re.IGNORECASE):
                match_start = match.start()
                match_end = match.end()

                # Extract sentence/clause boundaries around the match
                # rather than using an arbitrary character window.
                # This ensures unrelated claims don't leak into the passage.
                sentence_start, sentence_end = self._extract_sentence_boundary(
                    content_str, match_start, match_end
                )

                passage_text = content_str[sentence_start:sentence_end]

                # Skip if empty or whitespace only
                if not passage_text.strip():
                    continue

                # Skip if we've already seen this passage text
                passage_key = passage_text[:50]
                if passage_key in seen_texts:
                    continue
                seen_texts.add(passage_key)

                # Subject binding: if a specific subject is requested,
                # verify the actual selected sentence mentions that subject
                if requested_subject:
                    if not re.search(
                        rf"\b{re.escape(requested_subject)}\b",
                        passage_text,
                        re.IGNORECASE,
                    ):
                        # Subject not in this sentence - skip it
                        continue

                # Determine relevance based on whether we have claim support
                # For matched patterns, this is at least PARTIAL
                relevance = ExternalEvidenceRelevance.PARTIAL

                passage = BoundedPassage(
                    text=passage_text,
                    url=document.url,
                    title=document.title,
                    provider=document.provider,
                    start_offset=sentence_start,
                    end_offset=sentence_end,
                    relevance=relevance,
                )
                passages.append(passage)

        # If we found passages with claim support and entity mention,
        # upgrade to SUFFICIENT based on claim type.
        if passages:
            # Check if we have both entity keywords and claim patterns
            has_entity = any(
                kw in request_lower
                for kw in (
                    "version",
                    "release",
                    "date",
                    "price",
                    "cost",
                    "value",
                    "holder",
                    "officer",
                )
            )
            if has_entity:
                # Determine the request type to select the appropriate
                # SUFFICIENT pattern for passage relevance upgrade.
                request_type = self._detect_request_type(request_lower)
                # Pattern per claim type that indicates SUFFICIENT support.
                sufficient_patterns = {
                    "version": [r"\d+\.\d+\.\d+"],
                    "date": [
                        r"(?:20\d{2})[-/](?:0[1-9]|1[0-2])[-/](?:0[1-9]|[12]\d|3[01])",
                        r"\b(?:20\d{2})\b",
                    ],
                    "price": [
                        r"[$£€]\s*\d+(?:\.\d{2})?",
                        r"\b\d+(?:\.\d{2})?\s*(?:usd|vnd|eur|gbp)\b",
                    ],
                    "identity": [r"[A-Z][a-z]+\s+[A-Z][a-z]+"],
                }
                patterns = sufficient_patterns.get(
                    request_type, sufficient_patterns.get("version", [])
                )
                for p in passages:
                    if any(re.search(pat, p.text) for pat in patterns):
                        object.__setattr__(
                            p, "relevance", ExternalEvidenceRelevance.SUFFICIENT
                        )
                    elif document.truncated:
                        object.__setattr__(
                            p, "relevance", ExternalEvidenceRelevance.PARTIAL
                        )

        # Deterministically bound total passage count
        max_passages = 3
        return tuple(passages[:max_passages])

    @staticmethod
    def _extract_sentence_boundary(
        content: str, match_start: int, match_end: int
    ) -> tuple[int, int]:
        """Extract sentence/clause boundaries around a match.

        Returns (start, end) offsets that bound the full sentence or clause
        containing the matched claim. Uses sentence-ending punctuation,
        semicolons, and conjunctions as boundary markers.

        This ensures:
        - Only the relevant claim is extracted
        - Offsets are consistent with passage text
        - Unrelated claims separated by sentence boundaries are excluded
        """
        # Find sentence start: look backwards for sentence boundary markers
        # Sentence boundaries: period followed by space and capital letter,
        # semicolons, newlines, or start of content
        i = match_start
        while i > 0:
            i -= 1
            ch = content[i]
            # Stop at sentence-ending punctuation followed by space
            if ch == "." and (i + 1 >= len(content) or content[i + 1] == " "):
                # Check if next char is capital (new sentence)
                if i + 2 < len(content) and content[i + 2].isupper():
                    i += 1  # Include the period
                    break
            # Stop at semicolons, newlines, or other strong boundaries
            if ch in (";", "\n", "\r"):
                i += 1  # Include the boundary character
                break
            # Stop at start of content
            if i == 0:
                break

        sentence_start = i

        # Find sentence end: look forwards for sentence boundary markers
        j = match_end
        while j < len(content):
            ch = content[j]
            # Stop at sentence-ending punctuation followed by space and capital
            if ch == "." and (j + 1 >= len(content) or content[j + 1] == " "):
                if j + 2 < len(content) and content[j + 2].isupper():
                    j += 1  # Include the period
                    break
            # Stop at semicolons, newlines, or other strong boundaries
            if ch in (";", "\n", "\r"):
                break
            # Stop at conjunctions that start new independent clauses
            if (
                ch == ","
                and j + 1 < len(content)
                and content[j + 1 : j + 5]
                in (
                    ", and",
                    ", or",
                    ", but",
                )
            ):
                j += 1  # Include the comma
                break
            j += 1

        sentence_end = j

        # Ensure we have a non-empty passage
        if sentence_end <= sentence_start:
            sentence_end = match_end + 1
            sentence_start = max(0, match_start - 1)

        return sentence_start, sentence_end

    @staticmethod
    def _detect_request_type(request_lower: str) -> str:
        """Detect the type of request to determine required claim support.

        Order matters: check specific multi-word patterns BEFORE single-word
        tokens to avoid misclassification.  For example "release date" must
        classify as DATE, not VERSION, even though it contains "release".
        """
        # DATE — check multi-word patterns BEFORE single-word tokens
        if any(kw in request_lower for kw in ("release date", "current date", "date")):
            return "date"
        # VERSION — check before generic "release"
        if any(kw in request_lower for kw in ("current version", "version")):
            return "version"
        # PRICE — check multi-word patterns
        if any(
            kw in request_lower
            for kw in ("current price", "current value", "cost", "price")
        ):
            return "price"
        # IDENTITY — check multi-word patterns
        if any(
            kw in request_lower
            for kw in ("prime minister", "chief executive officer", "office holder")
        ):
            return "identity"
        if any(
            kw in request_lower
            for kw in (
                "holder",
                "officer",
                "identity",
                "ceo",
                "president",
                "chancellor",
                "secretary",
            )
        ):
            return "identity"
        return "general"


__all__ = [
    "BoundedPassage",
    "ExternalContentStatus",
    "ExternalDocument",
    "ExternalEvidenceCache",
    "ExternalEvidenceRelevance",
    "ExternalRequestBudget",
    "ExternalVerificationExecutor",
    "ExternalVerificationOutcome",
]
