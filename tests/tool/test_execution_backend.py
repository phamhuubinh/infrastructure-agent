from __future__ import annotations

import subprocess

import pytest

from src.tool.execution_backend import (
    ExecutionBackend,
    LocalExecutionBackend,
    SSHExecutionBackend,
)


class TestExecutionBackend:
    def test_abstract_class_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            ExecutionBackend()  # type: ignore[abstract]


class TestLocalExecutionBackend:
    def test_run_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeCompleted:
            returncode = 0
            stdout = "hello world\n"
            stderr = ""

        def fake_run(*args, **kwargs):
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = LocalExecutionBackend()
        ok, out = backend.run(["echo", "hello"])

        assert ok is True
        assert out == "hello world"

    def test_run_nonzero_returncode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeCompleted:
            returncode = 1
            stdout = ""
            stderr = "error occurred"

        def fake_run(*args, **kwargs):
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = LocalExecutionBackend()
        ok, out = backend.run(["false"])

        assert ok is False
        assert out == ""

    def test_run_oserror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args, **kwargs):
            msg = "command not found"
            raise OSError(msg)

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = LocalExecutionBackend()
        ok, out = backend.run(["nonexistent"])

        assert ok is False
        assert out == ""

    def test_run_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["sleep"], timeout=1)

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = LocalExecutionBackend()
        ok, out = backend.run(["sleep", "10"], timeout=1)

        assert ok is False
        assert out == ""

    def test_run_empty_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = LocalExecutionBackend()

        with pytest.raises(IndexError):
            backend.run([])

    def test_run_strips_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeCompleted:
            returncode = 0
            stdout = "  spaced output  \n\n"
            stderr = ""

        def fake_run(*args, **kwargs):
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = LocalExecutionBackend()
        ok, out = backend.run(["echo", "test"])

        assert ok is True
        assert out == "spaced output"

    def test_run_timeout_parameter_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_timeout = None

        class FakeCompleted:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_run(*args, **kwargs):
            nonlocal captured_timeout
            captured_timeout = kwargs.get("timeout")
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = LocalExecutionBackend()
        backend.run(["echo", "hello"], timeout=42)

        assert captured_timeout == 42


class TestSSHExecutionBackend:
    def test_build_ssh_command_defaults(self) -> None:
        backend = SSHExecutionBackend(host="10.0.0.1")
        cmd = backend._build_ssh_command(["ls", "-la"])

        assert cmd[0] == "ssh"
        assert "-o" in cmd
        assert "BatchMode=yes" in cmd
        assert "StrictHostKeyChecking=no" in cmd
        assert "UserKnownHostsFile=/dev/null" in cmd
        assert "-p" in cmd
        assert "22" in cmd
        assert "root@10.0.0.1" in cmd
        assert cmd[-1] == "ls -la"

    def test_build_ssh_command_strict_host_key_checking(self) -> None:
        backend = SSHExecutionBackend(host="10.0.0.1", strict_host_key_checking=True)
        cmd = backend._build_ssh_command(["ls", "-la"])

        assert "StrictHostKeyChecking=yes" in cmd

    def test_build_ssh_command_with_custom_params(self) -> None:
        backend = SSHExecutionBackend(
            host="192.168.1.1",
            user="admin",
            port=2222,
            identity_file="/home/user/.ssh/id_rsa",
        )
        cmd = backend._build_ssh_command(["df", "-h"])

        assert "-p" in cmd
        assert "2222" in cmd
        assert "admin@192.168.1.1" in cmd
        assert "-i" in cmd
        assert "/home/user/.ssh/id_rsa" in cmd
        assert cmd[-1] == "df -h"

    def test_build_ssh_command_handles_spaces_in_remote_command(self) -> None:
        backend = SSHExecutionBackend(host="10.0.0.1")
        cmd = backend._build_ssh_command(["cat", "/var/log/syslog"])

        assert cmd[-1] == "cat /var/log/syslog"

    def test_run_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeCompleted:
            returncode = 0
            stdout = "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1        50G   20G   30G  40% /\n"
            stderr = ""

        def fake_run(*args, **kwargs):
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = SSHExecutionBackend(host="10.0.0.1")
        ok, out = backend.run(["df", "-h"])

        assert ok is True
        assert "Filesystem" in out
        assert "/dev/sda1" in out

    def test_run_nonzero_returncode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeCompleted:
            returncode = 1
            stdout = ""
            stderr = "remote: command not found"

        def fake_run(*args, **kwargs):
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = SSHExecutionBackend(host="10.0.0.1")
        ok, out = backend.run(["bogus"])

        assert ok is False
        assert "command not found" in out

    def test_run_password_prompt_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeCompleted:
            returncode = 255
            stdout = ""
            stderr = "root@10.0.0.1's password:"

        def fake_run(*args, **kwargs):
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = SSHExecutionBackend(host="10.0.0.1")
        ok, out = backend.run(["ls"])

        assert ok is False
        assert "password" in out
        assert "SSH authentication failed" in out

    def test_run_oserror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args, **kwargs):
            msg = "ssh: command not found"
            raise OSError(msg)

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = SSHExecutionBackend(host="10.0.0.1")
        ok, out = backend.run(["ls"])

        assert ok is False
        assert out == ""

    def test_run_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["ssh"], timeout=5)

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = SSHExecutionBackend(host="10.0.0.1")
        ok, out = backend.run(["sleep", "100"], timeout=5)

        assert ok is False
        assert out == ""

    def test_run_timeout_parameter_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_timeout = None

        class FakeCompleted:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_run(*args, **kwargs):
            nonlocal captured_timeout
            captured_timeout = kwargs.get("timeout")
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = SSHExecutionBackend(host="10.0.0.1")
        backend.run(["echo", "hello"], timeout=99)

        assert captured_timeout == 99

    def test_run_strips_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeCompleted:
            returncode = 0
            stdout = "\n  result  \n\n"
            stderr = ""

        def fake_run(*args, **kwargs):
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = SSHExecutionBackend(host="10.0.0.1")
        ok, out = backend.run(["echo", "test"])

        assert ok is True
        assert out == "result"
