from __future__ import annotations

from app.main import _analysis_llm_client
from app.schemas import QueryRequest


def test_analysis_model_client_is_request_scoped() -> None:
    first = QueryRequest.model_validate(
        {
            "query": "first",
            "model_config": {
                "base_url": "http://model-one:8000/v1",
                "model": "one",
            },
        }
    )
    second = QueryRequest.model_validate(
        {
            "query": "second",
            "model_config": {
                "base_url": "http://model-two:8000/v1",
                "model": "two",
            },
        }
    )

    first_client = _analysis_llm_client(first)
    second_client = _analysis_llm_client(second)

    assert first_client is not second_client
    assert first_client._model == "one"
    assert second_client._model == "two"
