"""Optional, bounded Internet integration with safe arbitrary URL fetching."""

from __future__ import annotations

import ipaddress
import json
import socket
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from types import TracebackType
from typing import Any, Protocol
from urllib.parse import parse_qs, urljoin, urlsplit

import httpcore
import httpx

from orion.security import safe_endpoint

MAX_SEARCH_RESULTS = 8
MAX_SEARCH_SNIPPET_CHARS = 1_000
MAX_FETCH_TEXT_CHARS = 12_000
MAX_RESPONSE_BYTES = 512_000
MAX_REDIRECTS = 3
REQUEST_TIMEOUT_SECONDS = 10.0
HEALTH_TIMEOUT_SECONDS = 3.0
MAX_HEALTH_RESPONSE_BYTES = 32_000
DUCKDUCKGO_SEARCH_URL = "https://html.duckduckgo.com/html/"


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
            status="unconfigured",
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


class _DuckDuckGoResultParser(HTMLParser):
    """Extract the small public result subset Orion exposes to the model."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._results: list[tuple[str, str, str]] = []
        self._depth = 0
        self._ad = False
        self._url: str | None = None
        self._title: list[str] = []
        self._snippet: list[str] = []
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if self._depth:
            self._depth += 1
        elif tag == "div" and "result" in classes:
            self._depth = 1
            self._ad = "result--ad" in classes
            self._url = None
            self._title = []
            self._snippet = []
        if not self._depth or self._ad:
            return
        if tag == "a" and "result__a" in classes:
            self._url = attributes.get("href")
            self._capture = "title"
        elif "result__snippet" in classes:
            self._capture = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if self._capture and tag in {"a", "div", "span"}:
            self._capture = None
        if not self._depth:
            return
        self._depth -= 1
        if self._depth == 0 and not self._ad and self._url:
            self._results.append((self._url, " ".join(self._title), " ".join(self._snippet)))

    def handle_data(self, data: str) -> None:
        if self._capture == "title":
            self._title.append(data)
        elif self._capture == "snippet":
            self._snippet.append(data)

    @property
    def results(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(self._results)


Resolver = Callable[[str, int], Sequence[str]]


@dataclass(frozen=True)
class _ValidatedFetchTarget:
    """A URL plus the exact public address selected by Orion's resolver."""

    url: str
    host: str
    port: int
    address: str


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    """Dial one prevalidated address while HTTP Core retains the original origin.

    HTTP Core receives the hostname in its request origin, so it constructs Host and
    TLS SNI from that hostname. Only the TCP dial is substituted with the public
    address that Orion just resolved and validated.
    """

    def __init__(self, address: str, delegate: httpcore.NetworkBackend | None = None) -> None:
        self._address = address
        self._delegate = delegate or httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        return self._delegate.connect_tcp(
            self._address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        return self._delegate.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    def sleep(self, seconds: float) -> None:
        self._delegate.sleep(seconds)


class _PinnedHTTPTransport(httpx.BaseTransport):
    """Small HTTPX transport backed by a TCP-address-pinned HTTP Core pool."""

    def __init__(
        self, address: str, network_backend: httpcore.NetworkBackend | None = None
    ) -> None:
        self._pool = httpcore.ConnectionPool(
            max_connections=1,
            max_keepalive_connections=0,
            network_backend=_PinnedNetworkBackend(address, network_backend),
        )

    def __enter__(self) -> _PinnedHTTPTransport:
        self._pool.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        try:
            self._pool.__exit__(exc_type, exc_value, traceback)
        except httpcore.TimeoutException as error:
            raise httpx.TimeoutException(str(error)) from error
        except httpcore.NetworkError as error:
            raise httpx.NetworkError(str(error)) from error
        except httpcore.ProtocolError as error:
            raise httpx.ProtocolError(str(error)) from error

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, httpx.SyncByteStream)
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            core_response = self._pool.handle_request(core_request)
        except httpcore.ConnectTimeout as error:
            raise httpx.ConnectTimeout(str(error), request=request) from error
        except httpcore.ReadTimeout as error:
            raise httpx.ReadTimeout(str(error), request=request) from error
        except httpcore.WriteTimeout as error:
            raise httpx.WriteTimeout(str(error), request=request) from error
        except httpcore.PoolTimeout as error:
            raise httpx.PoolTimeout(str(error), request=request) from error
        except httpcore.ConnectError as error:
            raise httpx.ConnectError(str(error), request=request) from error
        except httpcore.ReadError as error:
            raise httpx.ReadError(str(error), request=request) from error
        except httpcore.WriteError as error:
            raise httpx.WriteError(str(error), request=request) from error
        except httpcore.ProxyError as error:
            raise httpx.ProxyError(str(error), request=request) from error
        except httpcore.UnsupportedProtocol as error:
            raise httpx.UnsupportedProtocol(str(error), request=request) from error
        except httpcore.ProtocolError as error:
            raise httpx.ProtocolError(str(error), request=request) from error
        assert isinstance(core_response.stream, Iterable)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=_CoreStream(core_response.stream),
            extensions=core_response.extensions,
        )


class _CoreStream(httpx.SyncByteStream):
    """Public HTTPX stream adapter for HTTP Core's iterable response body."""

    def __init__(self, stream: Iterable[bytes]) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        yield from self._stream

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if callable(close):
            close()


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
        try:
            self._probe()
        except InternetClientError:
            return InternetStatus(
                status="unhealthy",
                provider="searxng",
                endpoint=_display_endpoint(self._search_url),
                message="Configured Internet search integration is currently unavailable.",
            )
        return InternetStatus(
            status="healthy",
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
        target = self._validate_fetch_url(url)
        try:
            for redirect_count in range(MAX_REDIRECTS + 1):
                # Each hop gets a fresh one-connection transport, so its validated
                # address is also exactly the address dialed for that hop.
                with self._fetch_http_client(target) as client:
                    with client.stream("GET", target.url) as response:
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
                            target = self._validate_fetch_url(urljoin(target.url, location))
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
                            url=target.url,
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

    def _http_client(self, timeout: float = REQUEST_TIMEOUT_SECONDS) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            transport=self._transport,
            trust_env=False,
        )

    def _fetch_http_client(self, target: _ValidatedFetchTarget) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            follow_redirects=False,
            transport=self._transport or _PinnedHTTPTransport(target.address),
            trust_env=False,
        )

    def _validate_fetch_url(self, raw_url: str) -> _ValidatedFetchTarget:
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
        return _ValidatedFetchTarget(
            url=parsed.geturl(), host=host, port=port, address=str(addresses[0])
        )

    def _probe(self) -> None:
        """Bounded provider probe used only for integration health reporting."""
        try:
            with self._http_client(HEALTH_TIMEOUT_SECONDS) as client:
                with client.stream(
                    "GET",
                    self._search_url,
                    params={"q": "orion-healthcheck", "format": "json"},
                ) as response:
                    self._raise_for_search_status(response)
                    payload = _read_json_response(response, MAX_HEALTH_RESPONSE_BYTES)
        except InternetClientError:
            raise
        except httpx.TimeoutException as error:
            raise InternetClientError(
                "timeout", "Internet health probe timed out.", True
            ) from error
        except httpx.RequestError as error:
            raise InternetClientError(
                "connection_error", "Internet health probe connection failed.", True
            ) from error
        if not isinstance(payload.get("results"), list):
            raise InternetClientError(
                "invalid_response", "Internet health probe returned invalid data."
            )

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


class DuckDuckGoInternetClient(SearxngInternetClient):
    """Built-in bounded DuckDuckGo HTML search with the existing secure fetch path."""

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(DUCKDUCKGO_SEARCH_URL, resolver=resolver, transport=transport)

    def status(self) -> InternetStatus:
        try:
            self._probe()
        except InternetClientError:
            return InternetStatus(
                status="unhealthy",
                provider="duckduckgo",
                message="Tìm kiếm Internet hiện không khả dụng.",
            )
        return InternetStatus(
            status="healthy",
            provider="duckduckgo",
            message="Sẵn sàng để Orion tìm kiếm Internet tự động khi cần.",
        )

    def search(self, query: str, limit: int) -> tuple[InternetSearchResult, ...]:
        try:
            with self._http_client() as client:
                with client.stream("GET", DUCKDUCKGO_SEARCH_URL, params={"q": query}) as response:
                    self._raise_for_search_status(response)
                    body = _read_bounded_body(response)
        except InternetClientError:
            raise
        except httpx.TimeoutException as error:
            raise InternetClientError("timeout", "Internet search timed out.", True) from error
        except httpx.RequestError as error:
            raise InternetClientError(
                "connection_error", "Internet search connection failed.", True
            ) from error
        try:
            parser = _DuckDuckGoResultParser()
            parser.feed(body.decode("utf-8", errors="replace"))
            parser.close()
        except (ValueError, UnicodeError) as error:
            raise InternetClientError(
                "invalid_response", "Internet search returned an invalid response."
            ) from error
        retrieved_at = datetime.now(UTC)
        results: list[InternetSearchResult] = []
        for raw_url, raw_title, raw_snippet in parser.results:
            url = _duckduckgo_destination(raw_url)
            if url is None:
                continue
            results.append(
                InternetSearchResult(
                    url=url,
                    title=_bounded_text(raw_title, 500) or None,
                    snippet=_bounded_text(raw_snippet, MAX_SEARCH_SNIPPET_CHARS) or None,
                    retrieved_at=retrieved_at,
                )
            )
            if len(results) == min(limit, MAX_SEARCH_RESULTS):
                break
        return tuple(results)

    def _probe(self) -> None:
        self.search("orion-healthcheck", 1)


def _duckduckgo_destination(raw_url: str) -> str | None:
    """Return a canonical public HTTP(S) result, never a DuckDuckGo tracking URL."""
    try:
        parsed = urlsplit(urljoin(DUCKDUCKGO_SEARCH_URL, raw_url))
    except ValueError:
        return None
    if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com"}:
        destination = parse_qs(parsed.query).get("uddg", [])
        if len(destination) != 1:
            return None
        return _duckduckgo_destination(destination[0])
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return parsed.geturl()


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
    return safe_endpoint(raw_url)


def _read_bounded_body(response: httpx.Response, max_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise InternetClientError("response_too_large", "Internet response is too large.")
        except ValueError as error:
            raise InternetClientError(
                "invalid_response", "Internet response had an invalid content length."
            ) from error
    chunks: list[bytes] = []
    seen = 0
    for chunk in response.iter_bytes():
        seen += len(chunk)
        if seen > max_bytes:
            raise InternetClientError("response_too_large", "Internet response is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


def _read_json_response(
    response: httpx.Response, max_bytes: int = MAX_RESPONSE_BYTES
) -> dict[str, Any]:
    try:
        payload = json.loads(_read_bounded_body(response, max_bytes))
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
