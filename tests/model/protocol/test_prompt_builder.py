from __future__ import annotations

import json

from src.model.protocol.prompt_builder import build_prompt
from src.shared.discovery.observation import Observation


def test_prompt_is_valid_json() -> None:
    prompt = build_prompt("what is the docker version?", ())

    parsed = json.loads(prompt)

    assert isinstance(parsed, dict)


def test_prompt_contains_response_schemas() -> None:
    parsed = json.loads(build_prompt("hello", ()))

    assert parsed["response_schemas"]["action"]["type"] == "action"
    assert parsed["response_schemas"]["action"]["tool"] == "knowledge"
    assert parsed["response_schemas"]["final"]["type"] == "final"


def test_prompt_contains_user_request() -> None:
    parsed = json.loads(build_prompt("what is my ip?", ()))

    assert parsed["user_request"] == "what is my ip?"


def test_prompt_lists_available_resources_as_json_array() -> None:
    parsed = json.loads(build_prompt("what is the ip address?", ()))

    resources = parsed["available_resources"]["linux"]

    assert isinstance(resources, list)
    assert "interface_addresses" in resources
    assert "docker_version" in resources


def test_prompt_actions_taken_is_empty_list_with_no_observations() -> None:
    parsed = json.loads(build_prompt("what is the docker version?", ()))

    assert parsed["actions_taken"] == []


def test_prompt_actions_taken_includes_tool_arguments_and_data() -> None:
    observations = (
        Observation(
            data=[],
            success=True,
            tool="knowledge",
            arguments={"source": "linux", "resource": "docker_version"},
        ),
    )

    parsed = json.loads(build_prompt("what is the docker version?", observations))

    assert parsed["actions_taken"] == [
        {
            "tool": "knowledge",
            "arguments": {"source": "linux", "resource": "docker_version"},
            "success": True,
            "data": [],
        }
    ]


def test_prompt_actions_taken_includes_error_for_failed_entry() -> None:
    observations = (
        Observation(
            data=None,
            success=False,
            error="Unknown resource: 'ip'. Available resources: os_version.",
            tool="knowledge",
            arguments={"source": "linux", "resource": "ip"},
        ),
    )

    parsed = json.loads(build_prompt("what is my ip?", observations))

    assert parsed["actions_taken"] == [
        {
            "tool": "knowledge",
            "arguments": {"source": "linux", "resource": "ip"},
            "success": False,
            "error": "Unknown resource: 'ip'. Available resources: os_version.",
        }
    ]


def test_prompt_actions_taken_preserves_order_for_repeated_calls() -> None:
    observations = (
        Observation(
            data=[],
            success=True,
            tool="knowledge",
            arguments={"source": "linux", "resource": "docker_version"},
        ),
        Observation(
            data=[],
            success=True,
            tool="knowledge",
            arguments={"source": "linux", "resource": "docker_version"},
        ),
    )

    parsed = json.loads(build_prompt("what is the docker version?", observations))

    assert len(parsed["actions_taken"]) == 2
    assert parsed["actions_taken"][0] == parsed["actions_taken"][1]


def test_prompt_contains_no_repeat_rule() -> None:
    parsed = json.loads(build_prompt("what is the docker version?", ()))

    assert any("do not repeat" in rule for rule in parsed["rules"])


def test_prompt_contains_empty_result_rule() -> None:
    parsed = json.loads(build_prompt("what is the docker version?", ()))

    assert any("not a reason to retry" in rule for rule in parsed["rules"])
