from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi import HTTPException

from src.backend.routers import knowledge


def _request(
    rag_url: str = "http://rag:8080",
    *,
    model: tuple[str, dict] | None = (
        "primary",
        {
            "provider": "openai",
            "base_url": "http://model:8000",
            "model": "qwen",
            "api_key": "secret",
            "timeout": 90,
        },
    ),
) -> SimpleNamespace:
    deps = SimpleNamespace(
        rag_service_url=rag_url,
        rag_internal_token="root-to-rag-test-token",
        model_store=SimpleNamespace(active=lambda: model),
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(deps=deps)))


def test_create_project_proxies_normalized_payload() -> None:
    with mock.patch.object(
        knowledge, "_json_request", return_value={"id": "project-1"}
    ) as proxy:
        result = knowledge.create_project(
            {"name": "  Project One  ", "description": "Corpus"}, _request()
        )

    assert result == {"id": "project-1"}
    proxy.assert_called_once_with(
        "http://rag:8080",
        "/projects",
        method="POST",
        body={"name": "Project One", "description": "Corpus"},
        token="root-to-rag-test-token",
    )


def test_analysis_is_scoped_to_encoded_project_id() -> None:
    with mock.patch.object(
        knowledge,
        "_json_request",
        return_value={"answer": "ok", "retrieved": []},
    ) as proxy:
        result = knowledge.analyze_project(
            "project/with space", {"query": "  compare  ", "top_k": 7}, _request()
        )

    assert result["answer"] == "ok"
    proxy.assert_called_once_with(
        "http://rag:8080",
        "/projects/project%2Fwith%20space/analyses",
        method="POST",
        body={
            "query": "compare",
            "top_k": 7,
            "model_config": {
                "base_url": "http://model:8000/v1",
                "model": "qwen",
                "api_key": "secret",
                "timeout": 90,
            },
        },
        timeout=120,
        token="root-to-rag-test-token",
    )


def test_analysis_requires_a_configured_model() -> None:
    with pytest.raises(HTTPException) as exc_info:
        knowledge.analyze_project(
            "project-1", {"query": "compare", "top_k": 5}, _request(model=None)
        )
    assert exc_info.value.status_code == 503


def test_proxy_refuses_requests_without_its_configured_internal_token() -> None:
    request = _request()
    request.app.state.deps.rag_internal_token = ""

    with (
        mock.patch.object(knowledge, "_json_request") as proxy,
        pytest.raises(HTTPException) as exc_info,
    ):
        knowledge.create_project({"name": "Project One"}, request)

    assert exc_info.value.status_code == 503
    proxy.assert_not_called()


@pytest.mark.parametrize("top_k", [0, 21, "not-a-number"])
def test_analysis_rejects_invalid_top_k(top_k: object) -> None:
    with pytest.raises(HTTPException) as exc_info:
        knowledge.analyze_project(
            "project-1", {"query": "compare", "top_k": top_k}, _request()
        )
    assert exc_info.value.status_code == 400


def test_rag_url_must_be_configured() -> None:
    with pytest.raises(HTTPException) as exc_info:
        knowledge.list_projects(_request(""))
    assert exc_info.value.status_code == 503
