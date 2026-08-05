"""Tests for unified retry policy and executor."""

from __future__ import annotations

import time as _time

import pytest

from src.pipeline.retry import RetryExecutor, RetryPolicy, is_recoverable_result
from src.shared.execution.command_result import CommandResult, CommandStatus
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus

# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicyDefaults:
    def test_default_max_attempts(self) -> None:
        policy = RetryPolicy()
        assert policy.max_attempts == 3

    def test_default_backoff_base(self) -> None:
        policy = RetryPolicy()
        assert policy.backoff_base == 1.0

    def test_default_backoff_max(self) -> None:
        policy = RetryPolicy()
        assert policy.backoff_max == 30.0

    def test_default_jitter(self) -> None:
        policy = RetryPolicy()
        assert policy.jitter == 0.1

    def test_default_retryable_exceptions(self) -> None:
        policy = RetryPolicy()
        assert TimeoutError in policy.retryable_exceptions
        assert ConnectionError in policy.retryable_exceptions
        assert OSError in policy.retryable_exceptions


class TestRetryPolicyValidation:
    def test_max_attempts_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            RetryPolicy(max_attempts=0)

    def test_max_attempts_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            RetryPolicy(max_attempts=-1)

    def test_backoff_base_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="backoff_base must be >= 0"):
            RetryPolicy(backoff_base=-0.1)

    def test_backoff_max_less_than_base_raises(self) -> None:
        with pytest.raises(ValueError, match="backoff_max must be >= backoff_base"):
            RetryPolicy(backoff_base=2.0, backoff_max=1.0)

    def test_jitter_out_of_range_low(self) -> None:
        with pytest.raises(ValueError, match="jitter must be between 0.0 and 1.0"):
            RetryPolicy(jitter=-0.1)

    def test_jitter_out_of_range_high(self) -> None:
        with pytest.raises(ValueError, match="jitter must be between 0.0 and 1.0"):
            RetryPolicy(jitter=1.1)


class TestRetryPolicyComputeDelay:
    def test_attempt_zero_returns_zero(self) -> None:
        policy = RetryPolicy()
        assert policy.compute_delay(0) == 0.0

    def test_attempt_one_returns_base(self) -> None:
        policy = RetryPolicy(backoff_base=1.0)
        delay = policy.compute_delay(1)
        assert 0.9 <= delay <= 1.1  # jitter range

    def test_exponential_increase(self) -> None:
        policy = RetryPolicy(backoff_base=1.0, jitter=0.0)
        d1 = policy.compute_delay(1)
        d2 = policy.compute_delay(2)
        d3 = policy.compute_delay(3)
        assert d1 == 1.0
        assert d2 == 2.0
        assert d3 == 4.0

    def test_capped_at_max(self) -> None:
        policy = RetryPolicy(backoff_base=10.0, backoff_max=15.0, jitter=0.0)
        assert policy.compute_delay(1) == 10.0
        assert policy.compute_delay(2) == 15.0  # 20.0 capped
        assert policy.compute_delay(3) == 15.0  # 40.0 capped

    def test_jitter_adds_variation(self) -> None:
        """Jitter should produce variation across multiple samples."""
        policy = RetryPolicy(backoff_base=1.0, jitter=0.5)
        delays = [policy.compute_delay(1) for _ in range(100)]
        assert len(set(delays)) > 1  # not all identical
        assert all(0.5 <= d <= 1.5 for d in delays)  # within ±50%


# ---------------------------------------------------------------------------
# RetryExecutor
# ---------------------------------------------------------------------------


class TestRetryExecutorSuccess:
    def test_first_attempt_succeeds(self) -> None:
        executor = RetryExecutor()
        result = executor.execute(lambda: 42)
        assert result == 42

    def test_success_after_retry(self) -> None:
        call_counter = [0]

        def flaky() -> int:
            call_counter[0] += 1
            if call_counter[0] < 3:
                raise ConnectionError("transient")
            return 99

        executor = RetryExecutor(
            RetryPolicy(max_attempts=3, backoff_base=0.001, jitter=0.0),
        )
        result = executor.execute(flaky)
        assert result == 99
        assert call_counter[0] == 3

    def test_context_in_result(self) -> None:
        executor = RetryExecutor()
        result = executor.execute(lambda: "ok", context="test_ctx")
        assert result == "ok"

    def test_custom_policy_respected(self) -> None:
        policy = RetryPolicy(max_attempts=5, backoff_base=0.5)
        executor = RetryExecutor(policy)
        assert executor.policy.max_attempts == 5
        assert executor.policy.backoff_base == 0.5

    def test_retries_recoverable_structured_result(self) -> None:
        call_count = [0]

        def flaky_result() -> ToolResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return ToolResult(
                    success=False,
                    capability_status=CapabilityStatus.COLLECTION_FAILED,
                    command_results=(CommandResult(status=CommandStatus.TIMEOUT),),
                )
            return ToolResult(success=True, data={"ok": True})

        executor = RetryExecutor(
            RetryPolicy(max_attempts=3, backoff_base=0, backoff_max=0, jitter=0)
        )
        result = executor.execute(
            flaky_result,
            should_retry_result=is_recoverable_result,
        )

        assert result.success is True
        assert call_count[0] == 2

    def test_does_not_retry_nonrecoverable_structured_result(self) -> None:
        call_count = [0]

        def denied_result() -> ToolResult:
            call_count[0] += 1
            return ToolResult(
                success=False,
                capability_status=CapabilityStatus.COLLECTION_FAILED,
                command_results=(
                    CommandResult(status=CommandStatus.PERMISSION_DENIED),
                ),
            )

        executor = RetryExecutor(
            RetryPolicy(max_attempts=3, backoff_base=0, backoff_max=0, jitter=0)
        )
        result = executor.execute(
            denied_result,
            should_retry_result=is_recoverable_result,
        )

        assert result.success is False
        assert call_count[0] == 1


class TestRetryExecutorFailure:
    def test_exhausts_retries_non_retryable(self) -> None:
        """Non-retryable exceptions should propagate immediately."""
        executor = RetryExecutor(
            RetryPolicy(
                max_attempts=5,
                backoff_base=0.001,
                retryable_exceptions=(OSError,),
                jitter=0.0,
            ),
        )

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError):
            executor.execute(lambda: (_ for _ in ()).throw(CustomError("boom")))

    def test_exhausts_all_retries(self) -> None:
        call_count = [0]

        def always_fails() -> int:
            call_count[0] += 1
            raise ConnectionError("no connection")

        executor = RetryExecutor(
            RetryPolicy(max_attempts=3, backoff_base=0.001, jitter=0.0),
        )
        with pytest.raises(RuntimeError, match="Retry exhausted after 3 attempts"):
            executor.execute(always_fails)
        assert call_count[0] == 3

    def test_exhaustion_includes_context(self) -> None:
        executor = RetryExecutor(
            RetryPolicy(max_attempts=2, backoff_base=0.001, jitter=0.0),
        )

        def fail() -> None:
            raise OSError("disk full")

        with pytest.raises(RuntimeError, match="\\[context: db_write\\]"):
            executor.execute(fail, context="db_write")


class TestRetryExecutorTiming:
    def test_delays_accumulate_on_retry(self) -> None:
        executor = RetryExecutor(
            RetryPolicy(max_attempts=3, backoff_base=0.05, jitter=0.0),
        )
        call_count = [0]

        def fail_twice() -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("transient")
            return "done"

        t0 = _time.perf_counter()
        result = executor.execute(fail_twice)
        elapsed = _time.perf_counter() - t0

        assert result == "done"
        assert call_count[0] == 3
        # Expected delays: 0.05 (attempt 1→2) + 0.10 (attempt 2→3) = 0.15s
        assert 0.14 <= elapsed <= 0.25


class TestRetryExecutorEdgeCases:
    def test_max_attempts_one_retries_zero(self) -> None:
        """With max_attempts=1, there are 0 retries — must succeed first try."""
        executor = RetryExecutor(
            RetryPolicy(max_attempts=1, backoff_base=0.001, jitter=0.0),
        )
        call_count = [0]

        def fail() -> None:
            call_count[0] += 1
            raise ConnectionError("fail")

        with pytest.raises(RuntimeError, match="Retry exhausted after 1 attempts"):
            executor.execute(fail)
        assert call_count[0] == 1

    def test_nested_retryable_raises_correctly(self) -> None:
        """Ensure a retryable exception raised *inside* another is retried."""
        executor = RetryExecutor(
            RetryPolicy(max_attempts=3, backoff_base=0.001, jitter=0.0),
        )
        call_count = [0]

        def nested() -> str:
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("outer")
            if call_count[0] == 2:
                return "ok"
            raise RuntimeError("should not happen")

        result = executor.execute(nested)
        assert result == "ok"
        assert call_count[0] == 2
