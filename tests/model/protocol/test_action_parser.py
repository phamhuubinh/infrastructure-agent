import pytest

from src.model.protocol.action_parser import parse_response
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


def test_action_json():
    data = {
        "type": "action",
        "tool": "shell",
        "arguments": {
            "command": "echo hello",
        },
    }

    action = Action(
        tool=data["tool"],
        arguments=data["arguments"],
    )

    assert action.tool == "shell"
    assert action.arguments["command"] == "echo hello"


def test_final_json():
    data = {
        "type": "final",
        "content": "hello",
    }

    response = FinalResponse(
        content=data["content"],
    )

    assert response.content == "hello"


def test_unknown_tool():
    with pytest.raises(ValueError):
        parse_response("""
            {
                "type":"action",
                "tool":"docker",
                "arguments":{}
            }
            """)


def test_missing_tool():
    with pytest.raises(ValueError):
        parse_response("""
            {
                "type":"action",
                "arguments":{}
            }
            """)


def test_unknown_response_type():
    with pytest.raises(ValueError):
        parse_response("""
            {
                "type":"hello"
            }
            """)
