from __future__ import annotations

import subprocess
import threading

from src.shared.execution.tool_result import ToolResult
from src.tool.execution_backend import (
    LocalExecutionBackend,
    SSHExecutionBackend,
)
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


class FakeCompleted:
    returncode = 0
    stdout = "ok\n"
    stderr = ""


def _fake_run_ok(*args, **kwargs):
    return FakeCompleted()


def _fake_run_fail(*args, **kwargs):
    return FakeCompleted(returncode=1, stdout="", stderr="error")


class TestLocalExecutionBackendThreadSafety:
    def test_concurrent_run_same_instance(self, monkeypatch) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_run_ok)
        backend = LocalExecutionBackend()

        n_threads = 10
        iterations = 20
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _run(tid: int) -> None:
            barrier.wait()
            for i in range(iterations):
                try:
                    ok, out = backend.run(["echo", f"test_{tid}_{i}"])
                    assert ok is True
                    assert out == "ok"
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_run, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent LocalExecutionBackend.run: {errors}"
        )

    def test_concurrent_run_mixed_success_failure(self, monkeypatch) -> None:
        call_count: int = 0
        call_lock = threading.Lock()

        def _flaky_run(*args, **kwargs):
            nonlocal call_count
            with call_lock:
                call_count += 1
                if call_count % 3 == 0:
                    msg = "intermittent failure"
                    raise OSError(msg)
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", _flaky_run)
        backend = LocalExecutionBackend()

        n_threads = 8
        iterations = 15
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _run() -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    ok, out = backend.run(["echo", "test"])
                    assert isinstance(ok, bool)
                    assert isinstance(out, str)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=_run) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent flaky run: {errors}"

    def test_concurrent_timeout_handling(self, monkeypatch) -> None:
        def _slow_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["sleep"], timeout=1)

        monkeypatch.setattr(subprocess, "run", _slow_run)
        backend = LocalExecutionBackend()

        n_threads = 8
        iterations = 10
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _run() -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    ok, out = backend.run(["sleep", "10"], timeout=1)
                    assert ok is False
                    assert out == ""
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=_run) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent timeout handling: {errors}"

    def test_high_contention_determinism(self, monkeypatch) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_run_ok)
        backend = LocalExecutionBackend()

        runs = 3
        n_threads = 6
        iterations = 10
        result_counts: list[int] = []

        for run_idx in range(runs):
            barrier = threading.Barrier(n_threads)
            errors: list[Exception] = []
            success_count: int = 0
            count_lock = threading.Lock()

            def _run(
                _barrier=barrier,
                _errors=errors,
                _count_lock=count_lock,
            ) -> None:
                _barrier.wait()
                local_ok = 0
                for _ in range(iterations):
                    try:
                        ok, _ = backend.run(["echo", "test"])
                        if ok:
                            local_ok += 1
                    except Exception:
                        pass
                with _count_lock:
                    nonlocal success_count
                    success_count += local_ok

            threads = [threading.Thread(target=_run) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, (
                f"Errors during deterministic test run {run_idx}: {errors}"
            )
            result_counts.append(success_count)

        assert all(c == result_counts[0] for c in result_counts), (
            f"Non-deterministic: success counts differ across runs: {result_counts}"
        )


class TestSSHExecutionBackendThreadSafety:
    def test_concurrent_run_same_instance(self, monkeypatch) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_run_ok)
        backend = SSHExecutionBackend(host="10.0.0.1")

        n_threads = 8
        iterations = 15
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _run(tid: int) -> None:
            barrier.wait()
            for i in range(iterations):
                try:
                    ok, out = backend.run(["echo", f"test_{tid}_{i}"])
                    assert ok is True
                    assert out == "ok"
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_run, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent SSH run: {errors}"

    def test_concurrent_run_password_prompt_detection(self, monkeypatch) -> None:
        class FakePasswordPrompt:
            returncode = 255
            stdout = ""
            stderr = "root@10.0.0.1's password:"

        def _password_run(*args, **kwargs):
            return FakePasswordPrompt()

        monkeypatch.setattr(subprocess, "run", _password_run)
        backend = SSHExecutionBackend(host="10.0.0.1")

        n_threads = 6
        iterations = 10
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _run() -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    ok, out = backend.run(["ls"])
                    assert ok is False
                    assert "password" in out
                    assert "SSH authentication failed" in out
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=_run) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent SSH password detection: {errors}"

    def test_concurrent_run_with_custom_params(self, monkeypatch) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_run_ok)

        n_threads = 6
        backends = [
            SSHExecutionBackend(
                host="10.0.0.1",
                user="admin",
                port=2222,
                identity_file="/home/user/.ssh/id_rsa",
            )
            for _ in range(n_threads)
        ]

        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _run(tid: int) -> None:
            backend = backends[tid]
            barrier.wait()
            for _ in range(10):
                try:
                    ok, out = backend.run(["df", "-h"])
                    assert ok is True
                    assert out == "ok"
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_run, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent SSH with custom params: {errors}"

    def test_high_contention_determinism(self, monkeypatch) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_run_ok)

        runs = 3
        n_threads = 6
        iterations = 10
        result_counts: list[int] = []

        for run_idx in range(runs):
            backend = SSHExecutionBackend(host="10.0.0.1")
            barrier = threading.Barrier(n_threads)
            errors: list[Exception] = []
            success_count: int = 0
            count_lock = threading.Lock()

            def _run(
                _backend=backend,
                _barrier=barrier,
                _errors=errors,
                _count_lock=count_lock,
            ) -> None:
                _barrier.wait()
                local_ok = 0
                for _ in range(iterations):
                    try:
                        ok, _ = _backend.run(["echo", "test"])
                        if ok:
                            local_ok += 1
                    except Exception:
                        pass
                with _count_lock:
                    nonlocal success_count
                    success_count += local_ok

            threads = [threading.Thread(target=_run) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, f"Errors during SSH determinism run {run_idx}: {errors}"
            result_counts.append(success_count)

        assert all(c == result_counts[0] for c in result_counts), (
            f"Non-deterministic SSH: success counts differ: {result_counts}"
        )


class TestKnowledgeToolThreadSafety:
    def test_concurrent_execute_same_instance(self) -> None:
        kt = KnowledgeTool()

        n_threads = 10
        iterations = 20
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute(tid: int) -> None:
            barrier.wait()
            for _i in range(iterations):
                try:
                    result = kt.execute(
                        {
                            "source": "localhost",
                            "resource": "system_info",
                        }
                    )
                    assert isinstance(result, ToolResult)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_execute, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent KnowledgeTool.execute: {errors}"

    def test_concurrent_execute_unknown_source(self) -> None:
        kt = KnowledgeTool()

        n_threads = 8
        iterations = 15
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute() -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    result = kt.execute(
                        {
                            "source": "nonexistent",
                            "resource": "cpu_info",
                        }
                    )
                    assert isinstance(result, ToolResult)
                    assert result.success is False
                    assert "unknown source" in (result.error or "").lower()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=_execute) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent KnowledgeTool unknown source: {errors}"
        )

    def test_concurrent_execute_shared_registry(self) -> None:
        n_threads = 6
        iterations = 15
        registry = TargetRegistry()
        registry.add("localhost")

        backends = [LocalExecutionBackend() for _ in range(4)]
        for i, backend in enumerate(backends):
            registry.add(f"target_{i}", backend=backend)

        kt = KnowledgeTool(target_registry=registry)

        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute(tid: int) -> None:
            barrier.wait()
            target = f"target_{tid % 4}"
            for _ in range(iterations):
                try:
                    result = kt.execute(
                        {
                            "source": target,
                            "resource": "system_info",
                        }
                    )
                    assert isinstance(result, ToolResult)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_execute, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent KnowledgeTool shared registry: {errors}"
        )

    def test_concurrent_execute_missing_arguments(self) -> None:
        kt = KnowledgeTool()

        n_threads = 8
        iterations = 10
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute() -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    kt.execute({})
                except ValueError:
                    pass
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=_execute) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent KnowledgeTool missing args: {errors}"
        )

    def test_deterministic_output_under_concurrent_load(self) -> None:
        kt = KnowledgeTool()

        runs = 3
        n_threads = 8
        iterations = 10
        success_counts: list[int] = []

        for run_idx in range(runs):
            barrier = threading.Barrier(n_threads)
            errors: list[Exception] = []
            run_ok: int = 0
            ok_lock = threading.Lock()

            def _execute(
                _barrier=barrier,
                _errors=errors,
                _ok_lock=ok_lock,
            ) -> None:
                _barrier.wait()
                local_ok = 0
                for _ in range(iterations):
                    try:
                        result = kt.execute(
                            {
                                "source": "localhost",
                                "resource": "system_info",
                            }
                        )
                        if result.success:
                            local_ok += 1
                    except Exception:
                        pass
                with _ok_lock:
                    nonlocal run_ok
                    run_ok += local_ok

            threads = [threading.Thread(target=_execute) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, f"Errors during KT determinism run {run_idx}: {errors}"
            success_counts.append(run_ok)

        assert all(c == success_counts[0] for c in success_counts), (
            f"Non-deterministic KT: success counts differ: {success_counts}"
        )

    def test_concurrent_execute_with_registry_modification(self) -> None:
        registry = TargetRegistry()
        registry.add("localhost")
        kt = KnowledgeTool(target_registry=registry)

        n_executors = 4
        n_registrators = 2
        n_threads = n_executors + n_registrators
        iterations = 10
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []
        registry_lock = threading.Lock()

        def _registrator() -> None:
            barrier.wait()
            for i in range(iterations):
                with registry_lock:
                    try:
                        registry.add(f"dynamic_{i}", backend=LocalExecutionBackend())
                    except ValueError:
                        pass

        def _execute() -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    kt.execute(
                        {
                            "source": "localhost",
                            "resource": "system_info",
                        }
                    )
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=_execute) for _ in range(n_executors)]
        threads += [
            threading.Thread(target=_registrator) for _ in range(n_registrators)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent execute with registry modification: {errors}"
        )
