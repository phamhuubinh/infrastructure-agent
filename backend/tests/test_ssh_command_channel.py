"""Real local stdio-process fixtures; these are not a live SSH/Linux helper test."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

from orion.integrations.ssh.channel import SSHChannel, SSHChannelError
from orion.integrations.ssh.config import REMOTE_BOOTSTRAP, SSHTarget


def target(tmp_path):
    config = tmp_path / "config"
    hosts = tmp_path / "known_hosts"
    config.write_text("")
    hosts.write_text("")
    return SSHTarget(
        target_ref="ssh:lab",
        ssh_alias="fixture-alias",
        commands=True,
        config_file=str(config),
        known_hosts_file=str(hosts),
    )


def fixture_factory(argv_log, *, mode="normal", platform="linux"):
    hello = {
        "type": "hello",
        "version": 1,
        "platform": platform,
        "worker_version": "fixture",
        "capabilities": ["command.run", "command.status", "command.cancel"],
        "command_shells": ["sh"],
    }
    code = (
        "import json,sys,time\n"
        "n=int(sys.stdin.buffer.readline()); source=sys.stdin.buffer.read(n)\n"
        "assert source == b'fixed-helper-source'\n"
        f"print({json.dumps(hello)!r},flush=True)\n"
        "for line in sys.stdin.buffer:\n"
        " message=json.loads(line)\n"
        " if message['type']=='ping':\n"
        "  print(json.dumps({'type':'pong'}),flush=True); continue\n"
        " if message['type']!='request': continue\n"
        + (
            " sys.exit(0)\n"
            if mode == "eof"
            else " time.sleep(30)\n"
            if mode == "hang"
            else " print(json.dumps({'type':'result','request_id':message['request_id'],"
            "'data':{'safe':True}}),flush=True)\n"
        )
    )

    async def spawn(argv):
        argv_log.append(list(argv))
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-B",
            "-u",
            "-c",
            code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1_500_001,
        )

    return spawn


@pytest.mark.anyio
async def test_fixed_bootstrap_and_rpc_keep_script_out_of_local_argv(tmp_path):
    calls = []
    channel = SSHChannel(
        target(tmp_path),
        sys.executable,
        b"fixed-helper-source",
        process_factory=fixture_factory(calls),
    )
    try:
        await channel.start()
        await channel.start()
        result = await channel.call(
            "command.run",
            {"command_id": "a" * 32, "shell": "sh", "command": "echo private-script-marker"},
        )
        assert result == {"safe": True}
        assert len(calls) == 1 and calls[0][-1] == REMOTE_BOOTSTRAP
        assert "private-script-marker" not in str(calls)
        assert channel.hello.platform == "linux"
        with pytest.raises(SSHChannelError, match="policy_denied"):
            await channel.call("file.read", {})
    finally:
        await channel.close()
    assert channel.closed and channel.process.returncode is not None
    with pytest.raises(SSHChannelError):
        await channel.start()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "operation,category", [("command.run", "outcome_unknown"), ("command.status", "unavailable")]
)
async def test_eof_invalidates_pending_without_replay(tmp_path, operation, category):
    calls = []
    channel = SSHChannel(
        target(tmp_path),
        sys.executable,
        b"fixed-helper-source",
        process_factory=fixture_factory(calls, mode="eof"),
    )
    try:
        await channel.start()
        args = {"command_id": "a" * 32}
        if operation == "command.run":
            args.update(shell="sh", command="echo must-not-replay")
        with pytest.raises(SSHChannelError, match=category):
            await channel.call(operation, args)
        assert len(calls) == 1 and channel.closed
    finally:
        await channel.close()


@pytest.mark.anyio
async def test_shutdown_drains_pending_and_never_claims_remote_tree_killed(tmp_path):
    channel = SSHChannel(
        target(tmp_path),
        sys.executable,
        b"fixed-helper-source",
        process_factory=fixture_factory([], mode="hang"),
    )
    await channel.start()
    running = asyncio.create_task(
        channel.call(
            "command.run",
            {
                "command_id": "a" * 32,
                "shell": "sh",
                "command": "echo uncertain",
            },
        )
    )
    try:
        while not channel._pending:
            await asyncio.sleep(0)
        await channel.close()
        with pytest.raises(SSHChannelError, match="outcome_unknown"):
            await running
        assert channel.process.returncode is not None
        assert not channel._pending
    finally:
        await channel.close()


@pytest.mark.anyio
async def test_wrong_remote_platform_aborts_before_any_command(tmp_path):
    calls = []
    channel = SSHChannel(
        target(tmp_path),
        sys.executable,
        b"fixed-helper-source",
        process_factory=fixture_factory(calls, platform="windows"),
    )
    with pytest.raises(SSHChannelError):
        await channel.start()
    assert channel.closed and channel.process.returncode is not None
    assert len(calls) == 1 and not channel._pending
