from __future__ import annotations

import json
from unittest import mock

from src.backend.dify_client import DifyClient, wait_for_dify


def test_client_init_defaults() -> None:
    client = DifyClient()
    assert client.api_url == "http://dify-api:5001"


def test_client_init_custom() -> None:
    client = DifyClient(api_url="http://custom:5001", api_key="key123")
    assert client.api_url == "http://custom:5001"


@mock.patch("urllib.request.urlopen")
def test_health_ok(mock_urlopen) -> None:
    mock_resp = mock.MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value = mock_resp

    client = DifyClient()
    result = client.health()
    assert result["status"] == "ok"


@mock.patch("urllib.request.urlopen")
def test_health_error(mock_urlopen) -> None:
    mock_urlopen.side_effect = RuntimeError("dify down")

    client = DifyClient()
    result = client.health()
    assert result["status"] == "error"


@mock.patch("urllib.request.urlopen")
def test_chat_sends_request(mock_urlopen) -> None:
    mock_resp_data = {
        "answer": "hello from dify",
        "conversation_id": "conv-1",
        "message_id": "msg-1",
    }
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    client = DifyClient(api_key="test-key")
    result = client.chat(query="check nginx")
    assert result["answer"] == "hello from dify"
    assert result["conversation_id"] == "conv-1"


@mock.patch("urllib.request.urlopen")
def test_chat_sends_headers(mock_urlopen) -> None:
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = b'{"answer": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    client = DifyClient(api_key="my-api-key")
    client.chat(query="hello")

    req = mock_urlopen.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer my-api-key"


@mock.patch("urllib.request.urlopen")
def test_chat_error_returns_error_dict(mock_urlopen) -> None:
    from urllib.error import HTTPError

    mock_urlopen.side_effect = HTTPError("http://dify", 500, "Internal", {}, None)

    client = DifyClient()
    result = client.chat(query="hello")
    assert "error" in result


@mock.patch("src.backend.dify_client.DifyClient.health")
def test_wait_for_dify_success(mock_health) -> None:
    mock_health.return_value = {"status": "ok", "code": 200}
    client = DifyClient()
    assert wait_for_dify(client, max_retries=1) is True


@mock.patch("src.backend.dify_client.DifyClient.health")
def test_wait_for_dify_failure(mock_health) -> None:
    mock_health.return_value = {"status": "error", "error": "timeout"}
    client = DifyClient()
    assert wait_for_dify(client, max_retries=1) is False
