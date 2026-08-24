from __future__ import annotations

import json
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
        assert client._timeout == 180
        assert client._temperature == 0.0

    def test_init_custom_values(self) -> None:
        client = LLMClient(
            base_url="http://test:8080",
            model="my-model",
            api_key="sk-test",
            timeout=30,
            temperature=0.5,
        )
        assert client._base_url == "http://test:8080"
        assert client._model == "my-model"
        assert client._api_key == "sk-test"
        assert client._timeout == 30
        assert client._temperature == 0.5

    def test_trailing_slash_stripped(self) -> None:
        client = LLMClient(base_url="http://test:8000/")
        assert client._base_url == "http://test:8000"

    def test_openai_v1_suffix_is_normalized(self) -> None:
        client = LLMClient(base_url="https://api.openai.com/v1/")
        assert client._base_url == "https://api.openai.com"

    def test_ollama_defaults_to_no_openai_schema_support(self) -> None:
        assert not LLMClient(base_url="http://ollama:11434").supports_structured_output
        assert LLMClient(
            base_url="http://ollama:11434",
            supports_structured_output=True,
        ).supports_structured_output

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
        assert "max_tokens" not in body
        assert "max_completion_tokens" not in body

    @mock.patch("urllib.request.urlopen")
    def test_generate_uses_message_content_not_parsed_or_reasoning_fields(
        self, mock_urlopen: mock.Mock
    ) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices":[{"message":{"content":"content-field",'
            b'"parsed":{"kind":"action"},'
            b'"reasoning_content":"reasoning-field"}}]}'
        )

        assert LLMClient().generate("test prompt") == "content-field"

    @mock.patch("urllib.request.urlopen")
    def test_generate_with_response_schema(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "{\\"ok\\": true}"}}]}'
        )
        schema: dict[str, object] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        }

        result = LLMClient().generate("test prompt", response_schema=schema)

        assert result == '{"ok": true}'

        request = mock_urlopen.call_args[0][0]
        body = json.loads(request.data)
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "orion_structured_output",
                "strict": True,
                "schema": schema,
            },
        }

    @mock.patch("urllib.request.urlopen")
    def test_generate_with_json_object_mode(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "{}"}}]}'
        )

        LLMClient(model="qwen").generate("test prompt", json_object=True)

        request = mock_urlopen.call_args[0][0]
        assert json.loads(request.data)["response_format"] == {"type": "json_object"}

    def test_qwen_keeps_the_native_schema_mode_proven_by_its_endpoint(self) -> None:
        client = LLMClient(model="Qwen2.5")

        assert client.supports_structured_output
        assert client.supports_json_object_output

    @mock.patch("urllib.request.urlopen")
    def test_generate_omits_output_limit_without_explicit_configuration(
        self, mock_urlopen: mock.Mock
    ) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "ok"}}]}'
        )

        LLMClient().generate("test prompt")

        request = mock_urlopen.call_args[0][0]
        assert "max_tokens" not in json.loads(request.data)

    @mock.patch("urllib.request.urlopen")
    def test_generate_removes_internal_reasoning(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "<think>hidden\\nreasoning</think>\\nVisible answer"}}]}'
        )

        assert LLMClient().generate("hello") == "Visible answer"

    @mock.patch("urllib.request.urlopen")
    def test_generate_keeps_safe_generation_metadata_without_content(
        self, mock_urlopen: mock.Mock
    ) -> None:
        content = "<think>private reasoning</think>\n{\"kind\":\"action\""
        mock_urlopen.return_value = _mock_response(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": content},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 111,
                        "completion_tokens": 1024,
                    },
                }
            ).encode("utf-8"),
            status=200,
        )
        client = LLMClient()

        assert client.generate("hello") == '{"kind":"action"'
        assert client.last_generation_diagnostics == {
            "finish_reason": "length",
            "usage_completion_tokens": 1024,
            "usage_prompt_tokens": 111,
            "stop_sequence_configured": False,
            "content_bytes_before_sanitization": len(content.encode("utf-8")),
            "content_bytes_after_sanitization": len(b'{"kind":"action"'),
            "provider_http_status": 200,
        }

        request = mock_urlopen.call_args[0][0]
        body = json.loads(request.data)
        assert "max_tokens" not in body
        assert "max_completion_tokens" not in body
        assert "stop" not in body

    @mock.patch("urllib.request.urlopen")
    def test_generate_normalizes_usage_payload(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "ok"}}], "usage": {'
            b'"prompt_tokens": 12, "completion_tokens": 40, '
            b'"completion_tokens_details": {"reasoning_tokens": 15}}}'
        )
        client = LLMClient(base_url="https://api.openai.com", model="gpt-4")

        assert client.generate("test", purpose="assessment") == "ok"

        usage = client.last_usage
        assert usage is not None
        assert usage.input_tokens == 12
        assert usage.reasoning_tokens == 15
        assert usage.visible_output_tokens == 25
        assert usage.total_output_tokens == 40
        assert usage.model == "gpt-4"
        assert usage.provider == "openai"
        assert usage.purpose == "assessment"
        assert usage.latency_ms is not None and usage.latency_ms >= 0

    @mock.patch("urllib.request.urlopen")
    def test_generate_without_usage_keeps_tokens_unknown(
        self, mock_urlopen: mock.Mock
    ) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "ok"}}]}'
        )
        client = LLMClient()

        client.generate("test")

        usage = client.last_usage
        assert usage is not None
        assert usage.input_tokens is None
        assert usage.total_output_tokens is None
        assert usage.model == "gpt-4"

    @mock.patch("urllib.request.urlopen")
    def test_generate_failure_resets_last_usage(self, mock_urlopen: mock.Mock) -> None:
        mock_urlopen.side_effect = OSError("down")
        client = LLMClient()

        with pytest.raises(RuntimeError):
            client.generate("test")

        assert client.last_usage is None

    @mock.patch("urllib.request.urlopen")
    def test_generate_rejects_reasoning_only_response(
        self, mock_urlopen: mock.Mock
    ) -> None:
        mock_urlopen.return_value = _mock_response(
            b'{"choices": [{"message": {"content": "<think>hidden</think>"}}]}'
        )

        with pytest.raises(RuntimeError, match="no user-visible content"):
            LLMClient().generate("hello")

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
        mock_urlopen.return_value = _mock_response(b'{"choices": [{"message": {}}]}')
        client = LLMClient()
        with pytest.raises(RuntimeError, match="no content"):
            client.generate("test")
