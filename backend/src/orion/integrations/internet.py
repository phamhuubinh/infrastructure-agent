"""Optional, bounded Internet integration with safe arbitrary URL fetching."""

from __future__ import annotations

import ipaddress
import json
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

MAX_SEARCH_RESULTS = 8
MAX_SEARCH_SNIPPET_CHARS = 1_000
MAX_FETCH_TEXT_CHARS = 12_000
MAX_RESPONSE_BYTES = 512_000
MAX_REDIRECTS = 3
REQUEST_TIMEOUT_SECONDS = 10.0


class InternetClientError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class InternetStatus:
    status: str
    provider: str | None = None
    endpoint: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class InternetSearchResult:
    url: str
    title: str | None
    snippet: str | None
    retrieved_at: datetime


@dataclass(frozen=True)
class InternetFetch:
    url: str
    title: str | None
    text: str
    retrieved_at: datetime


class InternetClient(Protocol):
    def status(self) -> InternetStatus: ...

    def search(self, query: str, limit: int) -> tuple[InternetSearchResult, ...]: ...

    def fetch(self, url: str) -> InternetFetch: ...


class UnavailableInternetClient:
    """Keeps the tool contract available while local Orion remains fully usable."""

    def status(self) -> InternetStatus:
        return InternetStatus(
            status="unavailable",
            message=(
                "Internet search is not configured. Set ORION_INTERNET_SEARCH_URL to enable it."
            ),
        )

    def search(self, query: str, limit: int) -> tuple[InternetSearchResult, ...]:
        raise InternetClientError(
            "unavailable", self.status().message or "Internet is unavailable."
        )

    def fetch(self, url: str) -> InternetFetch:
        raise InternetClientError(
            "unavailable", self.status().message or "Internet is unavailable."
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
        self._parts.append(data)

    @property
    def text(self) -> str:
        return _bounded_text(" ".join(self._parts), MAX_FETCH_TEXT_CHARS)

    @property
    def title(self) -> str | None:
        return _bounded_text(" ".join(self._title_parts), 500) or None


Resolver = Callable[[str, int], Sequence[str]]


class SearxngInternetClient:
    """A small SearXNG-compatible client; its configured endpoint is admin trusted.

    Search is intentionally separate from arbitrary fetch URLs: administrators may
    point search at a local service, while model-provided fetch targets must be public.
    """

    def __init__(
        self,
        search_url: str,
        *,
        resolver: Resolver | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._search_url = search_url
        self._resolver = resolver or _resolve_host
        self._transport = transport

    def status(self) -> InternetStatus:
        return InternetStatus(
            status="configured",
            provider="searxng",
            endpoint=_display_endpoint(self._search_url),
        )

    def search(self, query: str, limit: int) -> tuple[InternetSearchResult, ...]:
        try:
            with self._http_client() as client:
                with client.stream(
                    "GET",
                    self._search_url,
                    params={"q": query, "format": "json"},
                ) as response:
                    self._raise_for_search_status(response)
                    payload = _read_json_response(response)
        except InternetClientError:
            raise
        except httpx.TimeoutException as error:
            raise InternetClientError("timeout", "Internet search timed out.", True) from error
        except httpx.RequestError as error:
            raise InternetClientError(
                "connection_error", "Internet search connection failed.", True
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise InternetClientError(
                "invalid_response", "Internet search returned an invalid response."
            )
        retrieved_at = datetime.now(UTC)
        results: list[InternetSearchResult] = []
        for raw in payload["results"]:
            if not isinstance(raw, dict):
                continue
            url = raw.get("url")
            if not isinstance(url, str) or not url:
                continue
            title = _bounded_text(str(raw.get("title", "")), 500) or None
            snippet = (
                _bounded_text(
                    str(raw.get("content", raw.get("snippet", ""))), MAX_SEARCH_SNIPPET_CHARS
                )
                or None
            )
            results.append(
                InternetSearchResult(
                    url=url, title=title, snippet=snippet, retrieved_at=retrieved_at
                )
            )
            if len(results) == min(limit, MAX_SEARCH_RESULTS):
                break
        return tuple(results)

    def fetch(self, url: str) -> InternetFetch:
        current_url = self._validate_fetch_url(url)
        try:
            with self._http_client() as client:
                for redirect_count in range(MAX_REDIRECTS + 1):
                    with client.stream("GET", current_url) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise InternetClientError(
                                    "invalid_response", "Redirect response had no location."
                                )
                            if redirect_count == MAX_REDIRECTS:
                                raise InternetClientError(
                                    "too_many_redirects", "Too many redirects while fetching URL."
                                )
                            current_url = self._validate_fetch_url(urljoin(current_url, location))
                            continue
                        self._raise_for_fetch_status(response)
                        content_type = (
                            response.headers.get("content-type", "").split(";", 1)[0].lower()
                        )
                        if not _is_textual_content_type(content_type):
                            raise InternetClientError(
                                "unsupported_content",
                                "Fetched URL did not return supported textual content.",
                            )
                        body = _read_bounded_body(response)
                        text, title = _normalise_text(body, content_type)
                        if not text:
                            raise InternetClientError(
                                "unsupported_content", "Fetched URL contained no usable text."
                            )
                        return InternetFetch(
                            url=current_url,
                            title=title,
                            text=text,
                            retrieved_at=datetime.now(UTC),
                        )
                raise AssertionError("redirect loop should return or raise")
        except InternetClientError:
            raise
        except httpx.TimeoutException as error:
            raise InternetClientError("timeout", "Internet fetch timed out.", True) from error
        except httpx.RequestError as error:
            raise InternetClientError(
                "connection_error", "Internet fetch connection failed.", True
            ) from error

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            follow_redirects=False,
            transport=self._transport,
        )

    def _validate_fetch_url(self, raw_url: str) -> str:
        try:
            parsed = urlsplit(raw_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as error:
            raise InternetClientError("unsafe_url", "Fetch URL is malformed or unsafe.") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or "%" in host
        ):
            raise InternetClientError("unsafe_url", "Fetch URL is malformed or unsafe.")
        try:
            addresses = self._resolver(host, port)
        except (OSError, ValueError) as error:
            raise InternetClientError(
                "connection_error", "Could not resolve fetch URL.", True
            ) from error
        if not addresses or any(not _is_public_address(address) for address in addresses):
            raise InternetClientError(
                "unsafe_url", "Fetch URL resolves to a non-public network address."
            )
        return parsed.geturl()

    @staticmethod
    def _raise_for_search_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise InternetClientError(
                "upstream_error",
                "Internet search provider returned an error.",
                response.status_code >= 500,
            )

    @staticmethod
    def _raise_for_fetch_status(response: httpx.Response) -> None:
        if response.status_code == 404:
            raise InternetClientError("not_found", "Fetched URL was not found.")
        if response.status_code >= 400:
            raise InternetClientError(
                "upstream_error", "Fetched URL returned an error.", response.status_code >= 500
            )


def _resolve_host(host: str, port: int) -> Sequence[str]:
    return tuple(
        sorted(
            {str(entry[4][0]) for entry in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        )
    )


def _is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def _display_endpoint(raw_url: str) -> str:
    """Expose only safe endpoint identity in Settings/health, never URL credentials."""
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "configured"
    host = parsed.hostname
    if host is None:
        return "configured"
    try:
        port = parsed.port
    except ValueError:
        return "configured"
    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if port is None else f"{display_host}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _read_bounded_body(response: httpx.Response) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise InternetClientError("response_too_large", "Internet response is too large.")
        except ValueError as error:
            raise InternetClientError(
                "invalid_response", "Internet response had an invalid content length."
            ) from error
    chunks: list[bytes] = []
    seen = 0
    for chunk in response.iter_bytes():
        seen += len(chunk)
        if seen > MAX_RESPONSE_BYTES:
            raise InternetClientError("response_too_large", "Internet response is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


def _read_json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = json.loads(_read_bounded_body(response))
    except UnicodeDecodeError as error:
        raise InternetClientError(
            "invalid_response", "Internet search response was not text."
        ) from error
    except json.JSONDecodeError as error:
        raise InternetClientError(
            "invalid_response", "Internet search response was not valid JSON."
        ) from error
    if not isinstance(payload, dict):
        raise InternetClientError(
            "invalid_response", "Internet search returned an invalid response."
        )
    return payload


def _is_textual_content_type(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type in {
        "application/json",
        "application/xml",
        "application/xhtml+xml",
    }


def _normalise_text(body: bytes, content_type: str) -> tuple[str, str | None]:
    text = body.decode("utf-8", errors="replace")
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _TextExtractor()
        parser.feed(text)
        return parser.text, parser.title
    return _bounded_text(text, MAX_FETCH_TEXT_CHARS), None


def _bounded_text(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]
