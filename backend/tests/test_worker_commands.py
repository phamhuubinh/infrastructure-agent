"""Real local command processes; no network, credentials or unowned targets."""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import psutil
import pytest

from orion_endpoint.commands import CommandProcesses, available_shells
from orion_endpoint.executor import Executor
from orion_endpoint.policy import Policy

SHELLS = tuple(available_shells())


def test_os_shell_discovery_without_host_path(monkeypatch):
    monkeypatch.setenv("PATH", "")
    found = available_shells()
    assert ("cmd" if os.name == "nt" else "sh") in found


@pytest.mark.anyio
@pytest.mark.parametrize("shell", SHELLS)
async def test_private_script_supports_quotes_pipes_and_long_input(tmp_path, shell):
    runner = CommandProcesses()
    identity = uuid.uuid4().hex
    script = (
        "# padding\n" * 4000 + 'Write-Output "quoted value" | Select-String "quoted"'
        if shell == "powershell"
        else "rem padding\r\n" * 3000 + 'echo "quoted value" | findstr quoted'
        if shell == "cmd"
        else "# padding\n" * 4000 + "printf 'quoted value\\n' | grep quoted"
    )
    try:
        await runner.start({"command_id": identity, "shell": shell, "command": script})
        result = await finish(runner, identity)
        assert result["state"] == "succeeded"
        assert "quoted value" in result["stdout"] and '\\"' not in result["stdout"]
    finally:
        await runner.close()


async def finish(runner, identity):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = runner.status({"command_id": identity})
        if result["state"] not in {"created", "running"}:
            return result
        await asyncio.sleep(0.02)
    pytest.fail("Command did not terminate")


def invoke(shell: str, script: Path) -> str:
    if shell == "powershell":
        # PowerShell -File does not implicitly propagate native child exit codes.
        return f"& '{sys.executable}' '{script}'; exit $LASTEXITCODE"
    if shell == "cmd":
        return f'"{sys.executable}" "{script}"'
    import shlex

    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


@pytest.mark.anyio
@pytest.mark.parametrize("shell", SHELLS)
async def test_worker_shell_unicode_streams_cwd_and_nonzero_exit(tmp_path, shell):
    runner = CommandProcesses()
    script = tmp_path / "program with spaces.py"
    script.write_text(
        "import os,sys\nprint('hello 你好',flush=True)\n"
        "print(os.getcwd(),flush=True)\nprint('error stream',file=sys.stderr)\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    directory = tmp_path / "cwd with spaces"
    directory.mkdir()
    identity = uuid.uuid4().hex
    try:
        await runner.start(
            {
                "command_id": identity,
                "shell": shell,
                "command": invoke(shell, script),
                "cwd": str(directory),
            }
        )
        result = await finish(runner, identity)
        assert result["state"] == "failed" and result["exit_code"] == 7
        assert "hello 你好" in result["stdout"] and str(directory) in result["stdout"]
        assert "error stream" in result["stderr"]
        assert result["process_tree_terminated"]
        assert runner.handles[identity].process.poll() == 7
    finally:
        await runner.close()


@pytest.mark.anyio
@pytest.mark.parametrize("shell", SHELLS)
async def test_output_is_drained_after_combined_bound_without_pipe_deadlock(tmp_path, shell):
    runner = CommandProcesses()
    script = tmp_path / "output.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write(b'x'*100000)\nsys.stderr.buffer.write(b'y'*100000)\n",
        encoding="utf-8",
    )
    identity = uuid.uuid4().hex
    try:
        await runner.start(
            {
                "command_id": identity,
                "shell": shell,
                "command": invoke(shell, script),
                "max_output_bytes": 1024,
            }
        )
        result = await finish(runner, identity)
        assert result["state"] == "succeeded"
        assert result["captured_output_bytes"] == 1024
        assert result["omitted_output_bytes"] == 198976
        assert len(result["stdout"] + result["stderr"]) == 1024
    finally:
        await runner.close()


@pytest.mark.anyio
@pytest.mark.parametrize("reason", ["timeout", "cancel", "close"])
async def test_owned_process_tree_cleanup(tmp_path, reason):
    runner = CommandProcesses()
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess,sys,time\n"
        f"child=subprocess.Popen([sys.executable,{str(child)!r}])\n"
        "print(child.pid,flush=True)\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    identity = uuid.uuid4().hex
    shell = "cmd" if os.name == "nt" else "sh"
    try:
        await runner.start(
            {
                "command_id": identity,
                "shell": shell,
                "command": invoke(shell, parent),
                "timeout_seconds": 2,
            }
        )
        deadline = time.monotonic() + 5
        pid = None
        while time.monotonic() < deadline:
            output = runner.status({"command_id": identity})["stdout"].strip()
            if output:
                pid = int(output)
                break
            await asyncio.sleep(0.02)
        assert pid is not None and psutil.pid_exists(pid)
        if reason == "cancel":
            await runner.cancel(identity)
        elif reason == "close":
            await runner.close()
        result = await finish(runner, identity)
        assert result["state"] == ("timed_out" if reason == "timeout" else "cancelled")
        assert result["process_tree_terminated"]
        assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    finally:
        await runner.close()


@pytest.mark.anyio
async def test_disabled_policy_cannot_launch_and_reconnect_has_no_old_handles(tmp_path):
    executor = Executor(Policy())
    identity = uuid.uuid4().hex
    values = {"command_id": identity, "shell": SHELLS[0], "command": "echo forbidden"}
    try:
        assert not any(
            name.startswith("command.") for name in (await executor.hello()).capabilities
        )
        with pytest.raises(PermissionError):
            await executor.execute("command.run", values)
        executor.policy.commands = True
        hello = await executor.hello()
        assert "command.run" in hello.capabilities and hello.command_shells
        await executor.execute("command.run", values)
        await finish(executor.commands, identity)
        with pytest.raises(FileExistsError):
            await executor.execute("command.run", values)
        await executor.close()
        await executor.hello()
        with pytest.raises(ValueError, match="unavailable"):
            await executor.execute("command.status", {"command_id": identity})
    finally:
        await executor.close()


@pytest.mark.anyio
@pytest.mark.skipif(os.name != "nt", reason="Native Windows suspended Job assignment")
async def test_failed_job_assignment_never_executes_script(tmp_path, monkeypatch):
    from orion_endpoint.windows_job import WindowsJob

    def fail(*args):
        raise OSError("injected assignment failure")

    monkeypatch.setattr(WindowsJob, "attach_and_resume", fail)
    runner = CommandProcesses()
    identity = uuid.uuid4().hex
    marker = tmp_path / "never-created"
    try:
        await runner.start(
            {"command_id": identity, "shell": "cmd", "command": f'echo forbidden > "{marker}"'}
        )
        result = await finish(runner, identity)
        assert result["state"] == "outcome_unknown"
        assert not marker.exists()
        assert runner.handles[identity].process.poll() is not None
    finally:
        await runner.close()


@pytest.mark.anyio
async def test_paged_unicode_and_truncated_invalid_utf8_keep_raw_byte_cursors(tmp_path):
    runner = CommandProcesses()
    script = tmp_path / "unicode.py"
    text = "a" * 32767 + "你好" * 1000
    script.write_text(f"import sys\nsys.stdout.buffer.write({text.encode()!r} + b'\\xe4')\n")
    shell = "cmd" if os.name == "nt" else "sh"
    identity = uuid.uuid4().hex
    try:
        await runner.start(
            {"command_id": identity, "shell": shell, "command": invoke(shell, script)}
        )
        await finish(runner, identity)
        first = runner.status({"command_id": identity})
        assert first["next_stdout_offset"] == 32767
        second = runner.status({"command_id": identity, "stdout_offset": 32767})
        assert first["stdout"] + second["stdout"] == text + "\ufffd"
        assert second["next_stdout_offset"] == len(text.encode()) + 1
        with pytest.raises(ValueError, match="invalid_input"):
            runner.status(
                {"command_id": identity, "stdout_offset": second["next_stdout_offset"] + 1}
            )
    finally:
        await runner.close()
