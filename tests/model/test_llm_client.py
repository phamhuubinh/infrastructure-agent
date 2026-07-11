from __future__ import annotations

from unittest import mock

import pytest

from src.model.llm_client import LLMClient


def _mock_response(data: bytes, status: int = 200) -> mock.MagicMock:
    resp = mock.MagicMock()
    resp.read.return_value = data
    resp.status = status
    resp.__enter__.return_value = resp
    return resp


class TestLLMClient:
    def test_init_defaults(self) -> None:
        client = LLMClient()
        assert client._base_url == "http://localhost:8000"
        assert client._model == "gpt-4"
        assert client._api_key is None
        assert client._timeout == 60
        assert client._temperature == 0.0
        assert client._max_tokens == 2048

    def test_init_custom_values(self) -> None:
        client = LLMClient(
            base_url="http://test:8080",
            model="my-model",
            api_key="sk-test",
            timeout=30,
            temperature=0.5,
            max_tokens=4096,
        )
        assert client._base_url == "http://test:8080"
        assert client._model == "my-model"
        assert client._api_key == "sk-test"
        assert client._timeout == 30
        assert client._temperature == 0.5
        assert client._max_tokens == 4096

    def test_trailing_slash_stripped(self) -> None:
        client = LLMClient(base_url="http://test:8000/")
        assert client._base_url == "http://test:8000"

    @mock.patch("urllib.request.urlopen")
    def test_generate_success(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "test response"}}]}'
        )
        client = LLMClient()
        result = client.generate("test prompt")
        assert result == "test response"

        # Verify request was built correctly
        call_args = mock_urlopen.call_args[0][0]
        assert call_args.get_method() == "POST"
        assert "/v1/chat/completions" in call_args.full_url
        import json
        body = json.loads(call_args.data)
        assert body["model"] == "gpt-4"
        assert body["messages"][0]["content"] == "test prompt"

    @mock.patch("urllib.request.urlopen")
    def test_generate_with_api_key(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "ok"}}]}'
        )
        client = LLMClient(api_key="sk-test")
        client.generate("test")
        call_args = mock_urlopen.call_args[0][0]
        assert call_args.headers.get("Authorization") == "Bearer sk-test"

    @mock.patch("urllib.request.urlopen")
    def test_generate_http_error(self, mock_urlopen: mock.Mock) -> None:
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            url="http://test/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        client = LLMClient()
        with pytest.raises(RuntimeError, match="LLM API returned HTTP 401"):
            client.generate("test")

    @mock.patch("urllib.request.urlopen")
    def test_generate_connection_error(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.side_effect = OSError("Connection refused")
        client = LLMClient()
        with pytest.raises(RuntimeError, match="LLM API request failed"):
            client.generate("test")

    @mock.patch("urllib.request.urlopen")
    def test_generate_empty_choices(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(b'{"choices": []}')
        client = LLMClient()
        with pytest.raises(RuntimeError, match="no choices"):
            client.generate("test")

    @mock.patch("urllib.request.urlopen")
    def test_generate_no_content(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {}}]}'
        )
        client = LLMClient()
        with pytest.raises(RuntimeError, match="no content"):
            client.generate("test")
