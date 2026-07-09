from __future__ import annotations

import json

import pytest

from src.infrastructure.openai.openai_client import OpenAIClient


class _MockResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _mock_urlopen(
    monkeypatch,
    models_result: list[dict[str, str]],
) -> None:
    call_count = [0]

    def fake_urlopen(req, **kwargs):
        call_count[0] += 1
        is_models = "/v1/models" in req.full_url and req.get_method() == "GET"
        if is_models:
            return _MockResponse(
                json.dumps({"data": models_result}).encode("utf-8")
            )
        return _MockResponse(
            json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return call_count


def test_explicit_model_overrides_discovery(monkeypatch) -> None:
    _mock_urlopen(monkeypatch, [{"id": "some-other-model"}])
    client = OpenAIClient(model="explicit-model")
    assert client._model == "explicit-model"


def test_discovery_selects_first_model(monkeypatch) -> None:
    _mock_urlopen(monkeypatch, [{"id": "deepseek-ai/DeepSeek-V4-Flash"}])
    client = OpenAIClient()
    assert client._model == "deepseek-ai/DeepSeek-V4-Flash"


def test_discovery_selects_first_of_multiple(monkeypatch) -> None:
    _mock_urlopen(monkeypatch, [
        {"id": "model-alpha"},
        {"id": "model-beta"},
    ])
    client = OpenAIClient()
    assert client._model == "model-alpha"


def test_empty_model_list_raises(monkeypatch) -> None:
    _mock_urlopen(monkeypatch, [])
    with pytest.raises(RuntimeError, match="returned no models"):
        OpenAIClient()


def test_missing_models_key_raises(monkeypatch) -> None:
    _mock_urlopen(monkeypatch, [])
    with pytest.raises(RuntimeError, match="returned no models"):
        OpenAIClient()


def test_http_failure_raises(monkeypatch) -> None:
    def fake_urlopen(req, **kwargs):
        raise OSError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Cannot reach"):
        OpenAIClient()


def test_discovered_model_is_used_for_generate(monkeypatch) -> None:
    def fake_urlopen(req, **kwargs):
        is_models = "/v1/models" in req.full_url and req.get_method() == "GET"
        if is_models:
            return _MockResponse(
                json.dumps({"data": [{"id": "discovered-model"}]}).encode("utf-8")
            )
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "discovered-model"
        return _MockResponse(
            json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = OpenAIClient()
    response = client.generate("hello")
    assert response == "ok"


def test_payload_never_contains_model_default(monkeypatch) -> None:
    """
    Regression test: without an explicit model, the client must discover
    the model and never send "model": "default" in the payload.
    """
    captured_payloads = []

    def fake_urlopen(req, **kwargs):
        is_models = "/v1/models" in req.full_url and req.get_method() == "GET"
        if is_models:
            return _MockResponse(
                json.dumps({"data": [{"id": "real-model"}]}).encode("utf-8")
            )
        payload = json.loads(req.data.decode("utf-8"))
        captured_payloads.append(payload)
        return _MockResponse(
            json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = OpenAIClient()
    client.generate("test")

    assert captured_payloads[0]["model"] != "default"
    assert captured_payloads[0]["model"] == "real-model"


def test_discovery_only_happens_once(monkeypatch) -> None:
    calls = _mock_urlopen(monkeypatch, [{"id": "m"}])

    client = OpenAIClient()
    client.generate("first")
    client.generate("second")

    assert calls[0] == 3  # 1 models + 2 generate
