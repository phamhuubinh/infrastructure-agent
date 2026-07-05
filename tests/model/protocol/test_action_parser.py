from __future__ import annotations

import pytest

from src.model.protocol.action_parser import parse_response
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


def test_parse_action() -> None:
    result = parse_response("""
        {
            "type":"action",
            "tool":"knowledge",
            "arguments":{
                "source":"linux",
                "resource":"system_info"
            }
        }
        """)

    assert isinstance(result, Action)
    assert result.tool == "knowledge"
    assert result.arguments == {
        "source": "linux",
        "resource": "system_info",
    }


def test_parse_final() -> None:
    result = parse_response("""
        {
            "type":"final",
            "content":"hello"
        }
        """)

    assert isinstance(result, FinalResponse)
    assert result.content == "hello"


def test_missing_tool() -> None:
    with pytest.raises(ValueError):
        parse_response("""
            {
                "type":"action",
                "arguments":{}
            }
            """)


def test_missing_arguments() -> None:
    with pytest.raises(ValueError):
        parse_response("""
            {
                "type":"action",
                "tool":"knowledge"
            }
            """)


def test_unknown_response_type() -> None:
    with pytest.raises(ValueError):
        parse_response("""
            {
                "type":"unknown"
            }
            """)
