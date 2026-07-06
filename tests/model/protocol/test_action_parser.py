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


def test_parse_final_with_final_prefix() -> None:
    result = parse_response(
        """
        Final:
        {
            "type":"final",
            "content":"hello"
        }
        """
    )

    assert isinstance(result, FinalResponse)
    assert result.content == "hello"


def test_parse_action_with_action_prefix() -> None:
    result = parse_response(
        """
        Action:
        {
            "type":"action",
            "tool":"knowledge",
            "arguments":{
                "source":"linux",
                "resource":"system_info"
            }
        }
        """
    )

    assert isinstance(result, Action)
    assert result.tool == "knowledge"
    assert result.arguments == {
        "source": "linux",
        "resource": "system_info",
    }


def test_parse_final_with_json_prefix() -> None:
    result = parse_response(
        'JSON: {"type":"final","content":"hello"}'
    )

    assert isinstance(result, FinalResponse)
    assert result.content == "hello"


def test_parse_final_wrapped_in_markdown_fence_with_language() -> None:
    result = parse_response(
        """
        ```json
        {
            "type":"final",
            "content":"hello"
        }
        ```
        """
    )

    assert isinstance(result, FinalResponse)
    assert result.content == "hello"


def test_parse_final_wrapped_in_plain_markdown_fence() -> None:
    result = parse_response(
        """
        ```
        {
            "type":"final",
            "content":"hello"
        }
        ```
        """
    )

    assert isinstance(result, FinalResponse)
    assert result.content == "hello"


def test_parse_action_with_nested_braces_and_prefix() -> None:
    result = parse_response(
        """
        Action:
        {
            "type":"action",
            "tool":"knowledge",
            "arguments":{
                "source":"linux",
                "resource":"system_info",
                "nested":{"a":{"b":1}}
            }
        }
        """
    )

    assert isinstance(result, Action)
    assert result.arguments["nested"] == {"a": {"b": 1}}


def test_parse_final_with_braces_inside_string_content() -> None:
    result = parse_response(
        """
        Final:
        {
            "type":"final",
            "content":"value with { brace } inside"
        }
        """
    )

    assert isinstance(result, FinalResponse)
    assert result.content == "value with { brace } inside"


def test_parse_skips_invalid_leading_brace_and_finds_valid_object() -> None:
    result = parse_response(
        'I was thinking {something not json} then: {"type":"final","content":"ok"}'
    )

    assert isinstance(result, FinalResponse)
    assert result.content == "ok"


def test_no_json_object_raises_value_error_not_json_decode_error() -> None:
    with pytest.raises(ValueError):
        parse_response("This is just plain text with no JSON at all.")


def test_malformed_json_raises_value_error_not_json_decode_error() -> None:
    with pytest.raises(ValueError):
        parse_response('Final: {"type": "final", "content": "unterminated')


def test_non_object_json_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_response("[1, 2, 3]")


def test_empty_response_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_response("")
