"""Helper packaging/protocol fixtures, never represented as live SSH proof."""

import ast
import json
import subprocess
import sys

import pytest

from orion.integrations.ssh.config import REMOTE_BOOTSTRAP
from orion.integrations.ssh.payload import helper_payload
from orion.integrations.ssh.remote import Helper
from orion.integrations.ssh.remote_protocol import parse_message
from orion.integrations.ssh.remote_runner import RemoteCommands, _Command


def test_payload_is_standalone_stdlib_source_and_runs_with_site_packages_disabled():
    payload = helper_payload()
    assert 0 < len(payload) <= 131_072
    compile(payload, "<helper-fixture>", "exec")
    # -I ignores PYTHONPATH; -S removes site packages. All remote modules are
    # supplied by the fixed payload, not an Orion/psutil/Pydantic install.
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-u",
            "-c",
            "import sys;exec(compile(sys.stdin.buffer.read(),'<helper-fixture>','exec'))",
        ],
        input=payload,
        capture_output=True,
        timeout=15,
    )
    if sys.platform == "linux":
        assert completed.returncode == 0
        hello = json.loads(completed.stdout.splitlines()[0])
        assert hello["platform"] == "linux" and "command.run" in hello["capabilities"]
    else:
        assert completed.returncode == 125 and completed.stdout == b""
    assert completed.stderr == b""


def test_fixed_bootstrap_accepts_framed_payload_without_local_shell():
    import shlex

    code = shlex.split(REMOTE_BOOTSTRAP)[3]
    payload = helper_payload()
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-u", "-c", code],
        input=str(len(payload)).encode() + b"\n" + payload,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == (0 if sys.platform == "linux" else 125)
    assert result.stderr == b""


def test_remote_sources_have_no_runtime_third_party_or_application_imports():
    from importlib.resources import files

    package = files("orion.integrations.ssh")
    allowed = {
        "asyncio",
        "codecs",
        "collections",
        "contextlib",
        "ctypes",
        "dataclasses",
        "json",
        "math",
        "os",
        "pathlib",
        "re",
        "signal",
        "stat",
        "subprocess",
        "sys",
        "tempfile",
        "time",
        "typing",
        "__future__",
    }
    for name in ("remote", "remote_runner", "remote_files", "remote_protocol", "supervisor"):
        tree = ast.parse(package.joinpath(name + ".py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in allowed for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                assert node.module.split(".")[0] in allowed


def test_remote_runner_refuses_non_linux_before_creating_script_cache(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(OSError, match="Linux Python3.10"):
        RemoteCommands("fixed-source")


def test_remote_cursor_pages_preserve_raw_unicode_split_and_terminal_replacement():
    record = _Command({"command_id": "a" * 32, "shell": "sh"})
    text = "a" * 32767 + "你好"
    record.stdout.extend(text.encode() + b"\xe4")
    first, offset = RemoteCommands._page(record.stdout, 0, True)
    second, end = RemoteCommands._page(record.stdout, offset, True)
    assert offset == 32767 and end == len(record.stdout)
    assert first + second == text + "\ufffd"
    with pytest.raises(ValueError):
        RemoteCommands._page(record.stdout, end + 1, True)


@pytest.mark.anyio
async def test_uncertain_cancel_retry_cannot_promote_a_proc_scan_to_containment_proof():
    class ObservedOnly(RemoteCommands):
        async def _terminate(self, record):
            return True

    commands = ObservedOnly.__new__(ObservedOnly)
    identity = "a" * 32
    record = _Command({"command_id": identity, "shell": "sh"}, state="outcome_unknown")
    record.process = object()
    commands.handles = {identity: record}
    result = await commands.cancel(identity)
    assert result["state"] == "outcome_unknown" and not result["process_tree_terminated"]
    record.containment_complete = True
    result = await commands.cancel(identity)
    assert result["state"] == "outcome_unknown" and result["process_tree_terminated"]


@pytest.mark.anyio
async def test_helper_executes_closed_operation_and_only_returns_safe_error_categories():
    class Commands:
        async def start(self, arguments):
            raise RuntimeError("private script or host credential must not be emitted")

    class MemoryHelper(Helper):
        def __init__(self):
            super().__init__(Commands())
            self.messages = []

        async def send(self, value):
            self.messages.append(value)

    helper = MemoryHelper()
    message = parse_message(
        json.dumps(
            {
                "type": "request",
                "request_id": "b" * 32,
                "operation": "command.run",
                "arguments": {"command_id": "a" * 32, "shell": "sh", "command": "echo fixture"},
            }
        ).encode()
        + b"\n"
    )
    await helper.execute(message)
    assert helper.messages == [
        {"type": "result", "request_id": "b" * 32, "data": {}, "error": "outcome_unknown"}
    ]
