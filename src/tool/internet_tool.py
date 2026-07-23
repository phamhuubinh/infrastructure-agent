from __future__ import annotations

import ipaddress
import json
import re
import socket
from html.parser import HTMLParser
from urllib import error as urlerror
from urllib import parse as urllib_parse
from urllib import request

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool

_MAX_RESPONSE_BYTES = 512 * 1024  # 512 KB
_DEFAULT_TIMEOUT = 15

# RFC 1918, RFC 6890, RFC 3927, RFC 5735, RFC 4291
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_address(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _PRIVATE_NETWORKS)


def _resolve_host(hostname: str) -> str | None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, OSError):
        return None
    seen: set[str] = set()
    for info in infos:
        ip_str = info[4][0]
        if ip_str not in seen:
            seen.add(ip_str)
            if _is_private_address(ip_str):
                return ip_str
    return None


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._skip = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:  # noqa: ARG002
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
        req = request.Request(url=url, headers=req_headers, method="GET")
        with request.urlopen(req, timeout=timeout) as resp:
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
                "url": url,
                "status": resp.status,
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

    except urlerror.HTTPError as exc:
        return {
            "url": url,
            "status": exc.code,
            "error": f"HTTP {exc.code}: {exc.reason}",
            "data": None,
        }
    except urlerror.URLError as exc:
        return {
            "url": url,
            "status": None,
            "error": f"URL error: {exc.reason}",
            "data": None,
        }
    except (OSError, ValueError) as exc:
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

    parsed = urllib_parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {
            "error": f"Unsupported scheme: '{parsed.scheme}'. Only http and https are allowed.",
        }

    hostname = parsed.hostname or ""
    if _is_private_address(hostname):
        return {
            "error": f"Access to private address '{hostname}' is not allowed.",
        }

    private_ip = _resolve_host(hostname)
    if private_ip is not None:
        return {
            "error": f"Access to private address '{private_ip}' is not allowed.",
        }

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
            return ToolResult(success=False, error=f"InternetTool error: {exc}")
