from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_base_tool import (
    _CAPABILITIES,
    KnowledgeBaseTool,
    _rag_health,
    _rag_query,
)


def test_execute_returns_tool_result() -> None:
    tool = KnowledgeBaseTool()
    result = tool.execute({"action": "kb_health"})
    assert isinstance(result, ToolResult)


def test_execute_missing_action() -> None:
    tool = KnowledgeBaseTool()
    result = tool.execute({})
    assert result.success is False
    assert "Missing action" in (result.error or "")


def test_execute_unknown_action() -> None:
    tool = KnowledgeBaseTool()
    result = tool.execute({"action": "bogus"})
    assert result.success is False
    assert "Unknown action" in (result.error or "")
    assert "kb_health" in (result.error or "")


def test_capabilities_registered() -> None:
    assert "kb_health" in _CAPABILITIES
    assert "kb_query" in _CAPABILITIES
    assert "kb_ingest" in _CAPABILITIES

    cap = _CAPABILITIES["kb_query"]
    assert cap.name == "kb_query"
    assert cap.category == "knowledge"
    assert "query" in cap.parameters
    assert "knowledge-base" in cap.supported_targets


@patch("src.tool.knowledge_base_tool.request.urlopen")
def test_rag_health_ok(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "ok", "embedding_provider": "hash"}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = _rag_health()
    assert result["status"] == "ok"


@patch("src.tool.knowledge_base_tool.request.urlopen")
def test_rag_health_error(mock_urlopen: MagicMock) -> None:
    from urllib.error import URLError

    mock_urlopen.side_effect = URLError("connection refused")

    result = _rag_health()
    assert "error" in result


@patch("src.tool.knowledge_base_tool.request.urlopen")
def test_rag_query_ok(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"answer": "test answer", "retrieved": [{"id": "1", "text": "chunk", "score": 0.9, "payload": {}}]}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = _rag_query(query="test query", top_k=3)
    assert result["answer"] == "test answer"
    assert len(result["retrieved"]) == 1


def test_rag_query_empty_query() -> None:
    result = _rag_query(query="", top_k=5)
    assert "error" in result
    assert "Missing query" in str(result["error"])


@patch("src.tool.knowledge_base_tool.request.urlopen")
def test_execute_query_proxies_correctly(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"answer": "found it", "retrieved": []}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    tool = KnowledgeBaseTool()
    result = tool.execute({"action": "kb_query", "query": "find docs", "top_k": 5})

    assert result.success is True
    data = dict(result.data) if isinstance(result.data, dict) else {}
    assert data.get("answer") == "found it"


def test_execute_health_proxies() -> None:
    tool = KnowledgeBaseTool()
    with patch("src.tool.knowledge_base_tool.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = tool.execute({"action": "kb_health"})
        assert result.success is True
