"""R26 native Linux stdio/helper/process fixtures, separate from a live SSH server."""

import asyncio
import os
import shlex
import sys
import time

import psutil
import pytest

from orion.integrations.ssh.channel import SSHChannel
from orion.integrations.ssh.config import REMOTE_BOOTSTRAP, SSHTarget
from orion.integrations.ssh.payload import helper_payload

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        sys.platform != "linux",
        reason="R26 needs actual Linux process groups, prctl parent death and private filesystem",
    ),
]


async def channel(tmp_path):
    config, hosts = tmp_path / "config", tmp_path / "known_hosts"
    config.write_text("")
    hosts.write_text("")
    temporary = tmp_path / "remote-cache"
    temporary.mkdir(mode=0o700)

    async def spawn(_):
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-S",
            "-u",
            "-c",
            shlex.split(REMOTE_BOOTSTRAP)[3],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1_500_001,
            env={**os.environ, "TMPDIR": str(temporary)},
        )

    target = SSHTarget(
        target_ref="ssh:fixture",
        ssh_alias="unused-no-network",
        commands=True,
        config_file=str(config),
        known_hosts_file=str(hosts),
    )
    result = SSHChannel(target, sys.executable, helper_payload(), process_factory=spawn)
    await result.start()
    return result


async def terminal(connection, identity):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = await connection.call("command.status", {"command_id": identity})
        if result["state"] not in {"created", "running"}:
            return result
        await asyncio.sleep(0.02)
    pytest.fail("Native helper failed to finish within its bounded fixture")


def alive(process):
    try:
        return (
            process is not None
            and process.is_running()
            and process.status() != psutil.STATUS_ZOMBIE
        )
    except psutil.NoSuchProcess:
        return False


async def test_real_helper_streams_unicode_cwd_nonzero_and_output_pressure(tmp_path):
    connection = await channel(tmp_path)
    cwd = tmp_path / "folder with spaces"
    cwd.mkdir()
    identity = "a" * 32
    script = "printf '你好 stdout\\n'; printf 'error stream\\n' >&2; pwd; exit 7"
    try:
        await connection.call(
            "command.run",
            {
                "command_id": identity,
                "shell": "sh",
                "command": script,
                "cwd": str(cwd),
                "max_output_bytes": 1024,
                "timeout_seconds": 5,
            },
        )
        result = await terminal(connection, identity)
        assert result["state"] == "failed" and result["exit_code"] == 7
        assert "你好 stdout" in result["stdout"] and str(cwd) in result["stdout"]
        assert "error stream" in result["stderr"] and result["process_tree_terminated"]
        program = (
            "import sys;sys.stdout.buffer.write(b'x'*100000);sys.stderr.buffer.write(b'y'*100000)"
        )
        await connection.call(
            "command.run",
            {
                "command_id": "b" * 32,
                "shell": "sh",
                "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}",
                "max_output_bytes": 1024,
            },
        )
        bounded = await terminal(connection, "b" * 32)
        assert bounded["state"] == "succeeded" and bounded["captured_output_bytes"] == 1024
        assert bounded["omitted_output_bytes"] == 198976
    finally:
        await connection.close()


@pytest.mark.parametrize("reason", ["timeout", "cancel", "eof", "helper-crash"])
async def test_real_helper_owns_descendants_on_timeout_stop_eof_and_abrupt_death(tmp_path, reason):
    connection = await channel(tmp_path)
    pid_file = tmp_path / "child.pid"
    child = tmp_path / "child.py"
    child.write_text(
        "import os,time\nfrom pathlib import Path\n"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    identity = "c" * 32
    try:
        await connection.call(
            "command.run",
            {
                "command_id": identity,
                "shell": "sh",
                "command": f"{shlex.quote(sys.executable)} {shlex.quote(str(child))}",
                "timeout_seconds": 2 if reason == "timeout" else 15,
            },
        )
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert pid_file.exists()
        pid = int(pid_file.read_text())
        try:
            process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            process = None
        if reason == "cancel":
            await connection.call("command.cancel", {"command_id": identity})
        elif reason == "eof":
            await connection.close()
        elif reason == "helper-crash":
            connection.process.kill()  # Here the local fixture child IS the remote helper.
            await connection.process.wait()
        if reason in {"timeout", "cancel"}:
            result = await terminal(connection, identity)
            assert result["state"] == ("timed_out" if reason == "timeout" else "cancelled")
            assert result["process_tree_terminated"]
        deadline = time.monotonic() + 8
        while alive(process) and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert not alive(process)
    finally:
        await connection.close()


@pytest.mark.parametrize("reason", ["normal", "timeout", "cancel", "eof", "helper-crash"])
async def test_helper_does_not_claim_cleanup_of_a_detached_double_fork(tmp_path, reason):
    connection = await channel(tmp_path)
    pid_file = tmp_path / "daemon.pid"
    child = tmp_path / "daemon.py"
    child.write_text(
        "import os,time\nfrom pathlib import Path\n"
        f"marker=Path({str(pid_file)!r})\n"
        "first=os.fork()\n"
        "if first:\n os.waitpid(first,0)\n"
        " for _ in range(200):\n"
        "  if marker.exists(): break\n"
        "  time.sleep(.01)\n"
        + (" time.sleep(30)\n" if reason != "normal" else "")
        + " raise SystemExit(0)\n"
        "os.setsid()\n"
        "if os.fork(): os._exit(0)\n"
        "fd=os.open(os.devnull,os.O_RDWR)\n"
        "for stream in (0,1,2): os.dup2(fd,stream)\n"
        "temporary=marker.with_suffix('.tmp')\n"
        "temporary.write_text(str(os.getpid()))\nos.replace(temporary,marker)\ntime.sleep(30)\n"
    )
    process = None
    try:
        await connection.call(
            "command.run",
            {
                "command_id": "d" * 32,
                "shell": "sh",
                "command": f"{shlex.quote(sys.executable)} {shlex.quote(str(child))}",
                "timeout_seconds": 2 if reason == "timeout" else 15,
            },
        )
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert pid_file.exists(), "The fixture must actually reach its detached child"
        try:
            process = psutil.Process(int(pid_file.read_text()))
        except psutil.NoSuchProcess:
            pass
        if reason == "cancel":
            await connection.call("command.cancel", {"command_id": "d" * 32})
        elif reason == "eof":
            await connection.close()
        elif reason == "helper-crash":
            connection.process.kill()
            await connection.process.wait()
        if reason in {"normal", "timeout", "cancel"}:
            result = await terminal(connection, "d" * 32)
            assert result["process_tree_terminated"], result
            assert (
                result["state"]
                == {"normal": "succeeded", "timeout": "timed_out", "cancel": "cancelled"}[reason]
            )
        deadline = time.monotonic() + 8
        while alive(process) and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert not alive(process)
    finally:
        await connection.close()
        # psutil's identity-checked Process object only targets this fixture child.
        if process is not None:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
