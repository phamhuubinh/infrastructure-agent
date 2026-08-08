from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

from src.shared.execution.tool_result import ToolResult
from src.tool.internet_tool import (
    _CAPABILITIES,
    InternetTool,
    SearchResponse,
    SearchResult,
    _connect_to_pinned_address,
    _fetch_url,
    _is_private_address,
    _PinnedAddress,
    _resolve_host,
    _validate_external_url,
    _ValidatedURL,
    _web_fetch,
)

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeResponse:
    def __init__(
        self,
        status: int = _HTTP_OK,
        body: bytes = b"ok",
        content_type: str = "text/plain",
        location: str | None = None,
        reason: str = "OK",
    ) -> None:
        self.status = status
        self.reason = reason
        self._body = body
        self._location = location
        self.headers = {"Content-Type": content_type}

    def getheader(self, name: str) -> str | None:
        return self._location if name.lower() == "location" else None

    def read(self, _amount: int) -> bytes:
        return self._body


def _validated(url: str = "http://example.com/") -> _ValidatedURL:
    address = _PinnedAddress(
        family=socket.AF_INET,
        protocol=socket.IPPROTO_TCP,
        sockaddr=("93.184.216.34", 80),
        ip="93.184.216.34",
    )
    return _ValidatedURL(
        url=url,
        scheme="http",
        hostname="example.com",
        port=80,
        request_target="/",
        host_header="example.com",
        addresses=(address,),
    )


def _public_dns(ip: str = "93.184.216.34") -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 80))]


def test_execute_returns_tool_result() -> None:
    tool = InternetTool()
    with patch("src.tool.internet_tool._fetch_url", return_value={"data": "ok"}):
        result = tool.execute({"action": "web_fetch", "url": "http://example.com"})
    assert isinstance(result, ToolResult)


def test_execute_missing_action() -> None:
    tool = InternetTool()
    result = tool.execute({})
    assert result.success is False
    assert "Missing action" in (result.error or "")


def test_execute_unknown_action() -> None:
    tool = InternetTool()
    result = tool.execute({"action": "bogus"})
    assert result.success is False
    assert "Unknown action" in (result.error or "")
    assert "web_fetch" in (result.error or "")


def test_web_fetch_missing_url() -> None:
    result = _web_fetch(url="")
    assert "error" in result
    assert "Missing url" in str(result["error"])


def test_web_fetch_unsupported_scheme() -> None:
    result = _web_fetch(url="ftp://files.example.com")
    assert "error" in result
    assert "Unsupported scheme" in str(result["error"])


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool._validate_external_url")
def test_web_fetch_success_html(
    mock_validate: MagicMock,
    mock_open: MagicMock,
) -> None:
    connection = _FakeConnection()
    mock_validate.return_value = _validated()
    mock_open.return_value = (
        connection,
        _FakeResponse(
            body=b"<html><body><p>Hello World</p></body></html>",
            content_type="text/html",
        ),
    )

    result = _web_fetch(url="http://example.com")

    assert result["status"] == _HTTP_OK
    assert "Hello World" in str(result["data"])
    assert result["truncated"] is False
    assert result["fetch_status"] == "FETCH_SUCCESS"
    assert result["content_status"] == "CONTENT_EXTRACTED"
    assert connection.closed is True


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool._validate_external_url")
def test_web_fetch_success_json(
    mock_validate: MagicMock,
    mock_open: MagicMock,
) -> None:
    mock_validate.return_value = _validated()
    mock_open.return_value = (
        _FakeConnection(),
        _FakeResponse(
            body=b'{"key": "value", "number": 42}', content_type="application/json"
        ),
    )

    result = _web_fetch(url="http://example.com/data.json")

    assert result["status"] == _HTTP_OK
    assert result["data"] == {"key": "value", "number": 42}


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool._validate_external_url")
def test_web_fetch_truncated(
    mock_validate: MagicMock,
    mock_open: MagicMock,
) -> None:
    mock_validate.return_value = _validated()
    mock_open.return_value = (
        _FakeConnection(),
        _FakeResponse(body=b"x" * 600000),
    )

    result = _web_fetch(url="http://example.com/bigfile")

    assert result["status"] == _HTTP_OK
    assert result["truncated"] is True
    assert result["content_status"] == "CONTENT_TRUNCATED"


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool._validate_external_url")
def test_web_fetch_empty_body_is_not_content_evidence(
    mock_validate: MagicMock,
    mock_open: MagicMock,
) -> None:
    mock_validate.return_value = _validated()
    mock_open.return_value = (_FakeConnection(), _FakeResponse(body=b""))

    result = _web_fetch(url="http://example.com/")

    assert result["fetch_status"] == "FETCH_SUCCESS"
    assert result["content_status"] == "CONTENT_EMPTY"


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool._validate_external_url")
def test_web_fetch_http_error(
    mock_validate: MagicMock,
    mock_open: MagicMock,
) -> None:
    mock_validate.return_value = _validated()
    mock_open.return_value = (
        _FakeConnection(),
        _FakeResponse(status=_HTTP_NOT_FOUND, reason="Not Found"),
    )

    result = _web_fetch(url="http://example.com/404")

    assert result["status"] == _HTTP_NOT_FOUND
    assert "error" in result


def test_execute_passes_timeout_parameter() -> None:
    tool = InternetTool()
    with patch("src.tool.internet_tool._fetch_url") as mock_fn:
        mock_fn.return_value = {"data": "ok"}
        result = tool.execute(
            {"action": "web_fetch", "url": "http://example.com", "timeout": 30},
        )
    assert result.success is True
    mock_fn.assert_called_once_with("http://example.com", timeout=30)


def test_capabilities_registered() -> None:
    assert "web_search" in _CAPABILITIES
    assert "web_fetch" in _CAPABILITIES
    cap = _CAPABILITIES["web_fetch"]
    assert cap.name == "web_fetch"
    assert cap.category == "network"
    assert "url" in cap.parameters
    assert "internet" in cap.supported_targets


class _SearchProvider:
    name = "fixture-search"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, query: str, **kwargs: object) -> SearchResponse:
        self.calls.append({"query": query, **kwargs})
        return SearchResponse(
            query=query,
            provider=self.name,
            results=(
                SearchResult(
                    title="Orion release notes",
                    url="https://example.com/release",
                    snippet="A result snippet is discovery metadata.",
                    rank=1,
                    provider=self.name,
                ),
            ),
        )


def test_web_search_has_provider_neutral_structured_response() -> None:
    provider = _SearchProvider()
    result = InternetTool(provider=provider).execute(
        {
            "action": "web_search",
            "query": "Orion newest release",
            "locale": "en-US",
            "max_results": 3,
        }
    )

    assert result.success is True
    assert result.data["provider"] == "fixture-search"
    assert result.data["results"][0]["url"] == "https://example.com/release"
    assert provider.calls == [
        {
            "query": "Orion newest release",
            "locale": "en-US",
            "max_results": 3,
            "timeout": 15,
        }
    ]


def test_web_search_without_provider_fails_closed() -> None:
    result = InternetTool().execute(
        {"action": "web_search", "query": "current weather"}
    )

    assert result.success is False
    assert result.capability_status is not None
    assert "not configured" in (result.error or "").lower()


def test_web_fetch_timeout_setting() -> None:
    tool = InternetTool()
    with patch(
        "src.tool.internet_tool._fetch_url", return_value={"status": _HTTP_OK}
    ) as mock_fetch:
        result = tool.execute(
            {"action": "web_fetch", "url": "http://example.com", "timeout": 5},
        )
    assert result.success is True
    mock_fetch.assert_called_once_with("http://example.com", timeout=5)


def test_fetch_url_rejects_exception() -> None:
    with (
        patch(
            "src.tool.internet_tool._validate_external_url", return_value=_validated()
        ),
        patch(
            "src.tool.internet_tool._open_pinned_request",
            side_effect=OSError("connection refused"),
        ),
    ):
        result = _fetch_url(url="http://example.com")
    assert "error" in result
    assert "connection refused" in str(result["error"]).lower()


# --- SSRF prevention tests ---


def test_is_private_address_loopback() -> None:
    assert _is_private_address("127.0.0.1") is True
    assert _is_private_address("127.255.255.255") is True


def test_is_private_address_rfc1918() -> None:
    assert _is_private_address("10.0.0.1") is True
    assert _is_private_address("10.255.255.255") is True
    assert _is_private_address("172.16.0.1") is True
    assert _is_private_address("172.31.255.255") is True
    assert _is_private_address("192.168.0.1") is True
    assert _is_private_address("192.168.255.255") is True


def test_is_private_address_link_local_and_reserved_ranges() -> None:
    for address in ("169.254.1.1", "0.0.0.0", "100.64.0.1", "192.0.2.1"):
        assert _is_private_address(address) is True


def test_is_private_address_ipv6() -> None:
    assert _is_private_address("::1") is True
    assert _is_private_address("fd00::1") is True
    assert _is_private_address("fe80::1") is True


def test_is_private_address_public() -> None:
    assert _is_private_address("8.8.8.8") is False
    assert _is_private_address("172.14.255.255") is False
    assert _is_private_address("172.32.0.1") is False
    assert _is_private_address("192.167.255.255") is False
    assert _is_private_address("1.1.1.1") is False


def test_is_private_address_non_ip() -> None:
    assert _is_private_address("example.com") is False
    assert _is_private_address("") is False
    assert _is_private_address("not-an-ip") is False


def test_web_fetch_blocks_loopback_ip() -> None:
    result = _web_fetch(url="http://127.0.0.1/")
    assert "error" in result
    assert "private address" in str(result["error"]).lower()


def test_web_fetch_blocks_private_ip() -> None:
    for ip in ("10.1.2.3", "192.168.1.1", "172.16.0.5"):
        result = _web_fetch(url=f"http://{ip}/")
        assert "error" in result
        assert "private address" in str(result["error"]).lower()


@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_web_fetch_blocks_private_dns_answer(mock_getaddrinfo: MagicMock) -> None:
    mock_getaddrinfo.return_value = _public_dns("10.0.0.99")

    result = _web_fetch(url="http://internal.example.com/")

    assert "error" in result
    assert "private address" in str(result["error"]).lower()


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_web_fetch_allows_public_dns_answer(
    mock_getaddrinfo: MagicMock,
    mock_open: MagicMock,
) -> None:
    mock_getaddrinfo.return_value = _public_dns()
    mock_open.return_value = (_FakeConnection(), _FakeResponse())

    result = _web_fetch(url="http://example.com/")

    assert result.get("status") == _HTTP_OK
    assert mock_open.call_args.args[0].addresses[0].ip == "93.184.216.34"


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_redirect_target_is_validated_before_a_second_request(
    mock_getaddrinfo: MagicMock,
    mock_open: MagicMock,
) -> None:
    def resolve(
        hostname: str, _port: int, **_kwargs: object
    ) -> list[tuple[object, ...]]:
        return _public_dns() if hostname == "example.com" else _public_dns("127.0.0.1")

    mock_getaddrinfo.side_effect = resolve
    mock_open.return_value = (
        _FakeConnection(),
        _FakeResponse(status=302, location="http://127.0.0.1/admin"),
    )

    result = _web_fetch(url="http://example.com/")

    assert "private address" in str(result["error"]).lower()
    assert mock_open.call_count == 1


@patch("src.tool.internet_tool._open_pinned_request")
@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_redirect_to_public_target_is_followed_with_a_new_validated_address(
    mock_getaddrinfo: MagicMock,
    mock_open: MagicMock,
) -> None:
    def resolve(
        hostname: str, _port: int, **_kwargs: object
    ) -> list[tuple[object, ...]]:
        return _public_dns("93.184.216.34" if hostname == "example.com" else "1.1.1.1")

    mock_getaddrinfo.side_effect = resolve
    mock_open.side_effect = [
        (
            _FakeConnection(),
            _FakeResponse(status=302, location="https://www.example.net/next"),
        ),
        (_FakeConnection(), _FakeResponse(body=b"done")),
    ]

    result = _web_fetch(url="http://example.com/")

    assert result["status"] == _HTTP_OK
    assert result["url"] == "https://www.example.net/next"
    assert mock_open.call_count == 2
    assert mock_open.call_args_list[1].args[0].addresses[0].ip == "1.1.1.1"


@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_web_fetch_rejects_a_mixed_public_and_private_dns_answer(
    mock_getaddrinfo: MagicMock,
) -> None:
    mock_getaddrinfo.return_value = _public_dns() + _public_dns("10.0.0.8")

    result = _web_fetch(url="http://example.com/")

    assert "private address" in str(result["error"]).lower()


def test_connect_to_pinned_address_never_resolves_hostname_again() -> None:
    fake_socket = MagicMock()
    address = _validated().addresses[0]
    with patch(
        "src.tool.internet_tool.socket.socket", return_value=fake_socket
    ) as mock_socket:
        result = _connect_to_pinned_address(address, timeout=5)

    assert result is fake_socket
    mock_socket.assert_called_once_with(
        socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP
    )
    fake_socket.connect.assert_called_once_with(("93.184.216.34", 80))


def test_validate_external_url_rejects_embedded_credentials() -> None:
    with patch("src.tool.internet_tool.socket.getaddrinfo") as mock_getaddrinfo:
        result = _web_fetch(url="http://user:secret@example.com/")
    assert "embedded credentials" in str(result["error"]).lower()
    mock_getaddrinfo.assert_not_called()


def test_validate_external_url_rejects_port_zero() -> None:
    with patch("src.tool.internet_tool.socket.getaddrinfo") as mock_getaddrinfo:
        result = _web_fetch(url="http://example.com:0/")
    assert "invalid url port" in str(result["error"]).lower()
    mock_getaddrinfo.assert_not_called()


def test_resolve_host_returns_none_on_gai_error() -> None:
    result = _resolve_host("")
    assert result is None


@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_resolve_host_returns_private_ip(mock_getaddrinfo: MagicMock) -> None:
    mock_getaddrinfo.return_value = _public_dns("10.0.0.1")
    assert _resolve_host("internal.local") == "10.0.0.1"


@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_resolve_host_returns_none_for_public(mock_getaddrinfo: MagicMock) -> None:
    mock_getaddrinfo.return_value = _public_dns()
    assert _resolve_host("example.com") is None


@patch("src.tool.internet_tool.socket.getaddrinfo")
def test_validate_external_url_preserves_non_default_port(
    mock_getaddrinfo: MagicMock,
) -> None:
    mock_getaddrinfo.return_value = _public_dns()

    validated = _validate_external_url("https://example.com:8443/path?item=1")

    assert validated.port == 8443
    assert validated.host_header == "example.com:8443"
    assert validated.request_target == "/path?item=1"
