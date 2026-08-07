from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib import parse as urllib_parse

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.errors import source_api_error
from src.tool.tool import Tool

_MAX_RESPONSE_BYTES = 512 * 1024  # 512 KB
_DEFAULT_TIMEOUT = 15
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


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
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False
        if tag in ("p", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped + " ")

    def get_text(self) -> str:
        raw = "".join(self._text)
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
                    "content_type": content_type,
                    "content_length": len(raw),
                    "truncated": truncated,
                    "headers": dict(resp.headers),
                }

                if "json" in content_type.lower():
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
                    result["data"] = text[:10000]

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
) -> dict[str, object]:
    if not url:
        return {"error": "Missing url parameter."}

    return _fetch_url(url, timeout=timeout)


_CAPABILITIES: dict[str, Capability] = {
    "web_fetch": Capability(
        name="web_fetch",
        handler=_web_fetch,
        category="network",
        intents=("investigate", "discovery"),
        related=(),
        covers=("web-content", "internet", "url-fetch"),
        description="Fetch a URL from the internet and return its content as text or parsed JSON",
        supported_targets=("internet",),
        parameters=("url", "timeout"),
        estimated_cost=0.2,
    ),
}


class InternetTool(Tool):
    def execute(self, arguments: dict[str, object]) -> ToolResult:
        try:
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
