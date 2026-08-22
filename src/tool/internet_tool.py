from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib import parse as urllib_parse

from src.shared.capability import Capability, ParameterSpec
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityResult, CapabilityStatus
from src.tool.errors import source_api_error
from src.tool.tool import Tool

_MAX_RESPONSE_BYTES = 512 * 1024  # 512 KB
_MAX_EXTRACTED_TEXT_CHARS = 12_000
_DEFAULT_TIMEOUT = 15
_VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Provider-neutral result metadata.

    A result snippet is deliberately only discovery metadata.  The external
    verification planner fetches a selected public URL before treating its
    content as evidence.
    """

    title: str
    url: str
    snippet: str = ""
    rank: int = 0
    provider: str = ""
    retrieved_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "rank": self.rank,
            "provider": self.provider,
            "retrieved_at": (
                self.retrieved_at.astimezone(timezone.utc).isoformat()
                if self.retrieved_at is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """A typed, credential-free search response for deterministic planning."""

    query: str
    results: tuple[SearchResult, ...] = ()
    status: str = "ok"
    provider: str = ""
    retrieved_at: datetime | None = None
    failure: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "results": [result.to_dict() for result in self.results],
            "status": self.status,
            "provider": self.provider,
            "retrieved_at": (
                self.retrieved_at.astimezone(timezone.utc).isoformat()
                if self.retrieved_at is not None
                else None
            ),
            "failure": self.failure,
        }


class SearchProvider(Protocol):
    """Minimal provider boundary; no agent code depends on a search vendor."""

    @property
    def name(self) -> str: ...

    def search(
        self,
        query: str,
        *,
        locale: str | None = None,
        max_results: int = 5,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> SearchResponse: ...


class HttpJsonSearchProvider:
    """Small configurable adapter for a JSON search endpoint.

    The endpoint is expected to return an object containing a list under
    ``results_field`` (default ``results``).  Each result may use common
    ``url``/``link``, ``title``/``name``, and ``snippet``/``description``
    fields.  This keeps vendor mapping at the configuration edge rather than
    spreading provider-specific logic through the agent.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str | None = None,
        provider_name: str = "http-json",
        query_parameter: str = "q",
        locale_parameter: str = "locale",
        results_field: str = "results",
    ) -> None:
        self._endpoint = endpoint.strip()
        self._api_key = api_key.strip() if api_key else None
        self._name = provider_name.strip() or "http-json"
        self._query_parameter = query_parameter.strip() or "q"
        self._locale_parameter = locale_parameter.strip() or "locale"
        self._results_field = results_field.strip() or "results"

    @property
    def name(self) -> str:
        return self._name

    def search(
        self,
        query: str,
        *,
        locale: str | None = None,
        max_results: int = 5,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> SearchResponse:
        if not self._endpoint:
            return SearchResponse(
                query=query,
                status="unavailable",
                provider=self.name,
                retrieved_at=datetime.now(timezone.utc),
                failure="Search endpoint is not configured.",
            )

        parsed = urllib_parse.urlsplit(self._endpoint)
        existing = urllib_parse.parse_qsl(parsed.query, keep_blank_values=True)
        query_args = [
            (key, value)
            for key, value in existing
            if key
            not in {
                self._query_parameter,
                self._locale_parameter,
                "limit",
            }
        ]
        query_args.append((self._query_parameter, query))
        query_args.append(("limit", str(max(1, min(int(max_results), 10)))))
        if locale:
            query_args.append((self._locale_parameter, locale))
        request_url = urllib_parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urllib_parse.urlencode(query_args),
                "",
            )
        )
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = _fetch_url(request_url, timeout=timeout, headers=headers)
        retrieved_at = datetime.now(timezone.utc)
        if payload.get("error"):
            return SearchResponse(
                query=query,
                status="failed",
                provider=self.name,
                retrieved_at=retrieved_at,
                failure=str(payload["error"]),
            )
        raw_data = payload.get("data")
        if not isinstance(raw_data, dict):
            return SearchResponse(
                query=query,
                status="failed",
                provider=self.name,
                retrieved_at=retrieved_at,
                failure="Search provider returned a non-object JSON payload.",
            )
        raw_results = raw_data.get(self._results_field)
        if not isinstance(raw_results, list):
            return SearchResponse(
                query=query,
                status="failed",
                provider=self.name,
                retrieved_at=retrieved_at,
                failure=f"Search provider response lacks list field '{self._results_field}'.",
            )
        results: list[SearchResult] = []
        for item in raw_results[: max(1, min(int(max_results), 10))]:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("link")
            if not isinstance(url, str) or not url.strip():
                continue
            title = item.get("title") or item.get("name") or url
            snippet = item.get("snippet") or item.get("description") or ""
            results.append(
                SearchResult(
                    title=str(title)[:500],
                    url=url.strip(),
                    snippet=str(snippet)[:2000],
                    rank=len(results) + 1,
                    provider=self.name,
                    retrieved_at=retrieved_at,
                )
            )
        return SearchResponse(
            query=query,
            results=tuple(results),
            status="ok",
            provider=self.name,
            retrieved_at=retrieved_at,
        )


def _is_private_address(host: str) -> bool:
    """Return whether an address is unsafe for an outbound Internet request."""

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    # is_global excludes loopback, RFC 1918, link-local, unspecified,
    # multicast, documentation, carrier-grade NAT, and other reserved ranges.
    return not addr.is_global


def _resolve_host(hostname: str) -> str | None:
    """Return the first unsafe DNS answer, kept for diagnostics and tests."""

    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, OSError):
        return None
    seen: set[str] = set()
    for info in infos:
        ip_str = info[4][0]
        if not isinstance(ip_str, str):
            continue
        if ip_str not in seen:
            seen.add(ip_str)
            if _is_private_address(ip_str):
                return ip_str
    return None


@dataclass(frozen=True, slots=True)
class _PinnedAddress:
    """A DNS answer retained for the socket connection that follows."""

    family: int
    protocol: int
    sockaddr: tuple[object, ...]
    ip: str


@dataclass(frozen=True, slots=True)
class _ValidatedURL:
    url: str
    scheme: str
    hostname: str
    port: int
    request_target: str
    host_header: str
    addresses: tuple[_PinnedAddress, ...]


def _resolve_public_addresses(hostname: str, port: int) -> tuple[_PinnedAddress, ...]:
    """Resolve all addresses and reject a hostname with an unsafe answer."""

    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise ValueError(f"Unable to resolve hostname '{hostname}'.") from exc

    addresses: list[_PinnedAddress] = []
    seen: set[tuple[int, tuple[object, ...]]] = set()
    for family, _socktype, protocol, _canonname, sockaddr in infos:
        if not sockaddr or not isinstance(sockaddr[0], str):
            raise ValueError(f"Unable to resolve hostname '{hostname}'.")
        ip = sockaddr[0]
        if _is_private_address(ip):
            raise ValueError(f"Access to private address '{ip}' is not allowed.")
        key = (family, tuple(sockaddr))
        if key not in seen:
            seen.add(key)
            addresses.append(
                _PinnedAddress(
                    family=family,
                    protocol=protocol,
                    sockaddr=tuple(sockaddr),
                    ip=ip,
                )
            )

    if not addresses:
        raise ValueError(f"Unable to resolve hostname '{hostname}'.")
    return tuple(addresses)


def _validate_external_url(url: str) -> _ValidatedURL:
    """Validate one request hop and resolve it before opening a socket."""

    try:
        parsed = urllib_parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL.") from exc

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Unsupported scheme: '{parsed.scheme}'. Only http and https are allowed."
        )
    if not parsed.hostname:
        raise ValueError("URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs with embedded credentials are not allowed.")

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Invalid URL hostname.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid URL port.")
    effective_port = port or (443 if parsed.scheme == "https" else 80)
    addresses = _resolve_public_addresses(hostname, effective_port)

    path = parsed.path or "/"
    request_target = f"{path}?{parsed.query}" if parsed.query else path
    host_header = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and port != (443 if parsed.scheme == "https" else 80):
        host_header = f"{host_header}:{port}"

    return _ValidatedURL(
        url=url,
        scheme=parsed.scheme,
        hostname=hostname,
        port=effective_port,
        request_target=request_target,
        host_header=host_header,
        addresses=addresses,
    )


def _connect_to_pinned_address(
    address: _PinnedAddress, timeout: float | None
) -> socket.socket:
    """Connect to a numeric, validated address without another DNS lookup."""

    sock = socket.socket(address.family, socket.SOCK_STREAM, address.protocol)
    try:
        sock.settimeout(timeout)
        sock.connect(address.sockaddr)
    except OSError:
        sock.close()
        raise
    return sock


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, validated: _ValidatedURL, timeout: int) -> None:
        super().__init__(validated.hostname, validated.port, timeout=timeout)
        self._address = validated.addresses[0]

    def connect(self) -> None:
        self.sock = _connect_to_pinned_address(self._address, self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, validated: _ValidatedURL, timeout: int) -> None:
        self._ssl_context = ssl.create_default_context()
        super().__init__(
            validated.hostname,
            validated.port,
            timeout=timeout,
            context=self._ssl_context,
        )
        self._address = validated.addresses[0]

    def connect(self) -> None:
        sock = _connect_to_pinned_address(self._address, self.timeout)
        try:
            self.sock = self._ssl_context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _open_pinned_request(
    validated: _ValidatedURL,
    headers: dict[str, str],
    timeout: int,
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    connection: http.client.HTTPConnection
    if validated.scheme == "https":
        connection = _PinnedHTTPSConnection(validated, timeout)
    else:
        connection = _PinnedHTTPConnection(validated, timeout)

    try:
        connection.request("GET", validated.request_target, headers=headers)
        return connection, connection.getresponse()
    except Exception:
        connection.close()
        raise


class _HTMLStripper(HTMLParser):
    """Deterministic readable-content extractor; it never summarizes text."""

    def __init__(self) -> None:
        super().__init__()
        self._preferred: list[str] = []
        self._fallback: list[str] = []
        self._skip_tags: list[str] = []
        self._preferred_depth = 0
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if self._skip_tags:
            if tag not in _VOID_HTML_TAGS:
                self._skip_tags.append(tag)
            return
        attributes = {
            name.casefold(): (value or "").casefold() for name, value in attrs
        }
        chrome = " ".join(attributes.get(name, "") for name in ("id", "class", "role"))
        if tag in {
            "script",
            "style",
            "noscript",
            "header",
            "nav",
            "footer",
            "aside",
            "form",
        } or any(
            marker in chrome
            for marker in (
                "header",
                "nav",
                "menu",
                "sidebar",
                "footer",
                "cookie",
                "banner",
            )
        ):
            if tag not in _VOID_HTML_TAGS:
                self._skip_tags.append(tag)
            return
        if tag in {"main", "article"}:
            self._preferred_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
            self._append("\n")
        elif tag in {"td", "th"}:
            self._append(" | ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._skip_tags:
            if tag == self._skip_tags[-1]:
                self._skip_tags.pop()
            return
        if tag in {"main", "article"}:
            self._preferred_depth = max(0, self._preferred_depth - 1)
        if tag == "title":
            self._in_title = False
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_tags:
            return
        stripped = data.strip()
        if not stripped:
            return
        if self._in_title:
            self.title = (self.title + " " + stripped).strip()[:500]
        self._append(stripped + " ")

    def _append(self, value: str) -> None:
        self._fallback.append(value)
        if self._preferred_depth:
            self._preferred.append(value)

    def get_text(self) -> str:
        raw = "".join(self._preferred or self._fallback)
        raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _fetch_url(
    url: str,
    timeout: int = _DEFAULT_TIMEOUT,
    max_bytes: int = _MAX_RESPONSE_BYTES,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    req_headers = {
        "User-Agent": "OrionInfraTool/1.0",
        "Accept": "text/html,application/json,*/*",
    }
    if headers:
        req_headers.update(headers)

    try:
        current_url = url
        redirects = 0
        while True:
            validated = _validate_external_url(current_url)
            # Keep Host bound to the validated hostname rather than accepting a
            # caller-supplied value that could make a public IP route internally.
            request_headers = {
                key: value
                for key, value in req_headers.items()
                if key.lower() != "host"
            }
            request_headers["Host"] = validated.host_header
            connection, resp = _open_pinned_request(
                validated,
                request_headers,
                timeout,
            )
            try:
                status = resp.status
                location = resp.getheader("Location")
                if status in _REDIRECT_STATUSES and location:
                    if redirects >= _MAX_REDIRECTS:
                        return {
                            "url": current_url,
                            "status": status,
                            "error": f"Too many redirects (max {_MAX_REDIRECTS}).",
                            "data": None,
                        }
                    current_url = urllib_parse.urljoin(current_url, location)
                    redirects += 1
                    continue

                if status >= 400:
                    return {
                        "url": current_url,
                        "status": status,
                        "error": f"HTTP {status}: {resp.reason}",
                        "data": None,
                    }

                raw = resp.read(max_bytes + 1)
                truncated = len(raw) > max_bytes
                if truncated:
                    raw = raw[:max_bytes]

                content_type = resp.headers.get("Content-Type", "")
                try:
                    body = raw.decode("utf-8", errors="replace")
                except (LookupError, UnicodeDecodeError):
                    body = raw.decode("latin-1", errors="replace")

                result: dict[str, object] = {
                    "url": current_url,
                    "status": status,
                    "fetch_status": "FETCH_SUCCESS",
                    "content_type": content_type,
                    "content_length": len(raw),
                    "truncated": truncated,
                    "headers": dict(resp.headers),
                }

                normalized_type = content_type.casefold().split(";", 1)[0].strip()
                is_json = "json" in normalized_type
                is_text = (
                    is_json
                    or normalized_type.startswith("text/")
                    or normalized_type in {"application/xml", "application/xhtml+xml"}
                    or normalized_type.endswith("+xml")
                    # Some public pages omit Content-Type.  We still expose
                    # a bounded text extraction, but tag it so the evidence
                    # layer can require actual non-empty content.
                    or not normalized_type
                )

                if not is_text:
                    result["data"] = None
                    result["content_status"] = "CONTENT_UNSUPPORTED"
                    return result

                if is_json:
                    try:
                        result["data"] = json.loads(body)
                    except (json.JSONDecodeError, TypeError):
                        result["data"] = body[:10000]
                        result["parse_error"] = "Response is not valid JSON"
                else:
                    stripped = _HTMLStripper()
                    try:
                        stripped.feed(body)
                        text = stripped.get_text()
                    except (ValueError, TypeError):
                        text = body[:10000]
                    extraction_truncated = len(text) > _MAX_EXTRACTED_TEXT_CHARS
                    result["data"] = text[:_MAX_EXTRACTED_TEXT_CHARS]
                    if stripped.title:
                        result["title"] = stripped.title
                    truncated = truncated or extraction_truncated
                    result["truncated"] = truncated

                extracted = result.get("data")
                if (
                    extracted is None
                    or extracted == ""
                    or extracted == {}
                    or extracted == []
                ):
                    result["content_status"] = "CONTENT_EMPTY"
                elif truncated:
                    result["content_status"] = "CONTENT_TRUNCATED"
                else:
                    result["content_status"] = "CONTENT_EXTRACTED"

                return result
            finally:
                connection.close()
    except (OSError, ValueError, http.client.HTTPException, ssl.SSLError) as exc:
        return {
            "url": url,
            "status": None,
            "error": str(exc),
            "data": None,
        }


def _web_fetch(
    url: str = "",
    timeout: int = _DEFAULT_TIMEOUT,
    max_bytes: int = _MAX_RESPONSE_BYTES,
) -> dict[str, object]:
    if not url:
        return {"error": "Missing url parameter."}

    bounded_bytes = max(1, min(int(max_bytes), _MAX_RESPONSE_BYTES))
    if bounded_bytes == _MAX_RESPONSE_BYTES:
        # Keep the long-standing call shape for the default path; it also
        # avoids treating an omitted limit as an explicit caller override.
        return _fetch_url(url, timeout=timeout)
    return _fetch_url(url, timeout=timeout, max_bytes=bounded_bytes)


def _web_search(
    provider: SearchProvider | None = None,
    query: str = "",
    locale: str | None = None,
    max_results: int = 5,
    timeout: int = _DEFAULT_TIMEOUT,
) -> CapabilityResult:
    """Run exactly one bounded search through the configured provider."""

    normalized_query = query.strip()
    if not normalized_query:
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error="Missing query parameter.",
        )
    if len(normalized_query) > 1000:
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error="Search query exceeds the 1000-character limit.",
        )
    if provider is None:
        return CapabilityResult(
            status=CapabilityStatus.UNSUPPORTED,
            error=(
                "Search provider is not configured. Configure search_endpoint "
                "for the Internet tool before requesting web_search."
            ),
        )
    try:
        response = provider.search(
            normalized_query,
            locale=locale,
            max_results=max(1, min(int(max_results), 10)),
            timeout=max(1, min(int(timeout), 60)),
        )
    except (OSError, ValueError, TypeError) as exc:
        return CapabilityResult(
            status=CapabilityStatus.COLLECTION_FAILED,
            error=f"Search provider '{provider.name}' failed: {exc}",
        )
    if not isinstance(response, SearchResponse):
        return CapabilityResult(
            status=CapabilityStatus.COLLECTION_FAILED,
            error=f"Search provider '{provider.name}' returned a malformed response.",
        )
    if response.failure:
        return CapabilityResult(
            status=CapabilityStatus.COLLECTION_FAILED,
            data=response.to_dict(),
            error=response.failure,
        )
    return CapabilityResult.from_data(response.to_dict())


_CAPABILITIES: dict[str, Capability] = {
    "web_search": Capability(
        name="web_search",
        handler=_web_search,
        category="network",
        intents=("investigate", "discovery"),
        related=("web_fetch",),
        covers=("web-search", "internet"),
        description="Search the public web through a configured bounded provider",
        supported_targets=("internet",),
        parameters=("query", "locale", "max_results", "timeout"),
        parameter_specs=(ParameterSpec("query", required=True),),
        estimated_cost=0.2,
    ),
    "web_fetch": Capability(
        name="web_fetch",
        handler=_web_fetch,
        category="network",
        intents=("investigate", "discovery"),
        related=(),
        covers=("web-content", "internet", "url-fetch"),
        description="Fetch a URL from the internet and return its content as text or parsed JSON",
        supported_targets=("internet",),
        parameters=("url", "timeout", "max_bytes"),
        parameter_specs=(ParameterSpec("url", required=True),),
        estimated_cost=0.2,
    ),
}


class InternetTool(Tool):
    def __init__(
        self,
        *,
        search_endpoint: str = "",
        search_api_key: str | None = None,
        search_provider: str = "http-json",
        search_query_parameter: str = "q",
        search_locale_parameter: str = "locale",
        search_results_field: str = "results",
        timeout: int = _DEFAULT_TIMEOUT,
        provider: SearchProvider | None = None,
    ) -> None:
        """Create an Internet tool.

        Tests and integrations may inject a ``SearchProvider`` directly.  In
        production, a provider-neutral HTTP JSON adapter is only created when
        a search endpoint is configured; the absent configuration remains a
        typed, fail-closed capability failure rather than a stale-model
        fallback.
        """

        self._timeout = max(1, min(int(timeout), 60))
        self._search_provider = provider
        if self._search_provider is None and search_endpoint.strip():
            self._search_provider = HttpJsonSearchProvider(
                endpoint=search_endpoint,
                api_key=search_api_key,
                provider_name=search_provider,
                query_parameter=search_query_parameter,
                locale_parameter=search_locale_parameter,
                results_field=search_results_field,
            )

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        try:
            action = arguments.get("action")
            if action == "web_search":
                return self._dispatch(
                    _CAPABILITIES,
                    arguments,
                    "InternetTool",
                    provider=self._search_provider,
                )
            if action == "web_fetch" and "timeout" not in arguments:
                arguments = {**arguments, "timeout": self._timeout}
            return self._dispatch(
                _CAPABILITIES,
                arguments,
                "InternetTool",
            )
        except (ValueError, TypeError, RuntimeError, OSError) as exc:
            message = f"InternetTool error: {exc}"
            return ToolResult(
                success=False,
                error=message,
                capability_error=source_api_error(message),
            )

    @property
    def search_provider_name(self) -> str:
        """Credential-free identity used by external-evidence cache keys."""

        return (
            self._search_provider.name
            if self._search_provider is not None
            else "unconfigured"
        )
