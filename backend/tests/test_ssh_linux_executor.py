from __future__ import annotations

import subprocess

import pytest

from orion.integrations.infrastructure import InfrastructureError, SshLinuxExecutor, Target


@pytest.fixture
def target() -> Target:
    return Target("linux", "node", "Node", {"ssh_alias": "node"}, "ssh", {})


def _invoke(executor: SshLinuxExecutor, target: Target, mode: str) -> object:
    if mode == "text":
        return executor._run(target, "ssh-config", ["cat", "/tmp/a file"])
    if mode == "bytes":
        return executor._run_bytes(target, "ssh-config", ["cat", "/tmp/a file"])
    return executor._run_input(target, "ssh-config", ["cat", "/tmp/a file"], b"content")


@pytest.mark.parametrize("mode", ["text", "bytes", "input"])
def test_ssh_command_modes_keep_arguments_and_output(
    monkeypatch: pytest.MonkeyPatch, target: Target, mode: str
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[object]:
        calls.append((argv, kwargs))
        output: object = "text output" if kwargs.get("text") else b"byte output"
        return subprocess.CompletedProcess(argv, 0, output)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _invoke(SshLinuxExecutor(), target, mode)

    assert result == {"text": "text output", "bytes": b"byte output", "input": None}[mode]
    assert calls == [
        (
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "node",
                "--",
                "cat '/tmp/a file'",
            ],
            {
                "check": True,
                "capture_output": True,
                **({"text": True} if mode == "text" else {}),
                **({"input": b"content"} if mode == "input" else {}),
                "timeout": 15,
            },
        )
    ]


@pytest.mark.parametrize("mode", ["text", "bytes", "input"])
@pytest.mark.parametrize(
    ("error", "code", "message", "retryable"),
    [
        (subprocess.TimeoutExpired("ssh", 15), "timeout", "Linux target timed out.", True),
        (
            subprocess.CalledProcessError(1, "ssh"),
            "upstream_error",
            "Linux operation failed.",
            False,
        ),
    ],
)
def test_ssh_command_modes_keep_error_contract(
    monkeypatch: pytest.MonkeyPatch,
    target: Target,
    mode: str,
    error: BaseException,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(InfrastructureError) as raised:
        _invoke(SshLinuxExecutor(), target, mode)

    assert (raised.value.code, raised.value.message, raised.value.retryable) == (
        code,
        message,
        retryable,
    )
    assert raised.value.__cause__ is error
