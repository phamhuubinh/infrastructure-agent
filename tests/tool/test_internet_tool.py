from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.shared.execution.tool_result import ToolResult
from src.tool.internet_tool import InternetTool, _fetch_url, _web_fetch


def test_execute_returns_tool_result() -> None:
    tool = InternetTool()
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


@patch("src.tool.internet_tool.request.urlopen")
def test_web_fetch_success_html(mock_urlopen) -> None:
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"<html><body><p>Hello World</p></body></html>"
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = _web_fetch(url="http://example.com")
    assert result["status"] == 200
    assert "Hello World" in str(result["data"])
    assert result["truncated"] is False


@patch("src.tool.internet_tool.request.urlopen")
def test_web_fetch_success_json(mock_urlopen) -> None:
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"key": "value", "number": 42}'
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = _web_fetch(url="http://example.com/data.json")
    assert result["status"] == 200
    assert result["data"] == {"key": "value", "number": 42}


@patch("src.tool.internet_tool.request.urlopen")
def test_web_fetch_truncated(mock_urlopen) -> None:
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"x" * 600000
    mock_resp.headers = {"Content-Type": "text/plain"}
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = _web_fetch(url="http://example.com/bigfile")
    assert result["status"] == 200
    assert result["truncated"] is True


@patch("src.tool.internet_tool.request.urlopen")
def test_web_fetch_http_error(mock_urlopen) -> None:
    from urllib.error import HTTPError

    mock_urlopen.side_effect = HTTPError(
        url="http://example.com/404",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=None,
    )

    result = _web_fetch(url="http://example.com/404")
    assert result["status"] == 404
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
    from src.tool.internet_tool import _CAPABILITIES

    assert "web_fetch" in _CAPABILITIES
    cap = _CAPABILITIES["web_fetch"]
    assert cap.name == "web_fetch"
    assert cap.category == "network"
    assert "url" in cap.parameters
    assert "internet" in cap.supported_targets


def test_web_fetch_timeout_setting() -> None:
    tool = InternetTool()
    with patch("src.tool.internet_tool.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_resp.headers = {"Content-Type": "text/plain"}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = tool.execute(
            {"action": "web_fetch", "url": "http://example.com", "timeout": 5},
        )
        assert result.success is True
        assert result.data is not None
        data = dict(result.data) if isinstance(result.data, dict) else {}
        assert data.get("status") == 200


@patch("src.tool.internet_tool.request.urlopen")
def test_fetch_url_rejects_exception(mock_urlopen) -> None:
    mock_urlopen.side_effect = OSError("connection refused")
    result = _fetch_url(url="http://example.com")
    assert "error" in result
    assert "connection refused" in str(result["error"]).lower()
