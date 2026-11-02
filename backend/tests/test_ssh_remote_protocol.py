"""Standalone stdlib helper protocol matches canonical closed worker contracts."""

import json

import pytest

from orion.integrations.ssh.remote_protocol import (
    encode_message,
    parse_message,
    parse_supervisor_observation,
)
from orion_endpoint.protocol import Request


def request(**changes):
    values = {"command_id": "a" * 32, "shell": "sh", "command": "echo pipe | cat", **changes}
    return Request(request_id="b" * 32, operation="command.run", arguments=values)


def test_run_schema_normalization_matches_canonical_wire():
    result = parse_message(request().model_dump_json().encode() + b"\n")
    assert result["arguments"]["timeout_seconds"] == 60
    assert result["arguments"]["max_output_bytes"] == 262_144
    assert result["arguments"]["cwd"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"command_id": "arbitrary-pid"},
        {"shell": "powershell"},
        {"shell": ["sh"]},
        {"command": "\0"},
        {"command": "你" * 25_000},
        {"timeout_seconds": True},
        {"max_output_bytes": 4_194_305},
        {"cwd": {"path": "model"}},
        {"elevate": True},
        {"metadata_fd": 3},
        {"parent_pid": 123},
    ],
)
def test_remote_run_rejects_unknown_authority_or_malformed_bounds(changes):
    with pytest.raises(ValueError):
        parse_message(request(**changes).model_dump_json().encode() + b"\n")


@pytest.mark.parametrize(
    "state,code",
    [("succeeded", 1), ("failed", 0), ("failed", True), ("timed_out", 0), ("running", None)],
)
def test_supervisor_metadata_is_not_a_claim_of_verified_tree_cleanup(state, code):
    with pytest.raises(ValueError):
        parse_supervisor_observation(
            json.dumps(
                {
                    "state": state,
                    "exit_code": code,
                    "cleanup_complete": True,
                }
            ).encode()
        )


def test_private_supervisor_cleanup_observation_is_closed_and_strict():
    value = {"state": "succeeded", "exit_code": 0, "cleanup_complete": True}
    assert parse_supervisor_observation(json.dumps(value).encode()) == ("succeeded", 0, True)
    for invalid in (None, 1, "true"):
        with pytest.raises(ValueError):
            parse_supervisor_observation(
                json.dumps({**value, "cleanup_complete": invalid}).encode()
            )
    with pytest.raises(ValueError):
        parse_supervisor_observation(b'{"state":"succeeded","exit_code":0}')


def test_ping_cancel_status_and_result_have_exact_shared_wire_shapes():
    assert parse_message(b'{"type":"ping"}\n') == {"type": "ping"}
    assert (
        parse_message(encode_message({"type": "cancel", "request_id": "a" * 32}))["type"]
        == "cancel"
    )
    status = Request(
        request_id="b" * 32, operation="command.status", arguments={"command_id": "a" * 32}
    )
    assert (
        parse_message(status.model_dump_json().encode() + b"\n")["arguments"]["stdout_offset"] == 0
    )
    with pytest.raises(ValueError):
        parse_message(b'{"type":"ping","version":1}\n')
    with pytest.raises(ValueError):
        parse_message(b'{"type":"ping"}')
