"""Unified retry policy with exponential backoff + jitter.

Provides :class:`RetryPolicy` for configuration and :class:`RetryExecutor`
for consistent retry behavior across all pipeline stages, tool dispatch,
and database operations.

.. versionadded:: 0.8.0
"""

from __future__ import annotations

import random
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")

# Default retryable exception classes for infrastructure operations.
_DEFAULT_RETRYABLE: tuple[type[Exception], ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
)


@dataclass
class RetryPolicy:
    """Configuration for a retry strategy.

    Attributes:
        max_attempts: Maximum number of attempts (including the first).
            Must be >= 1.
        backoff_base: Base delay in seconds before the first retry.
        backoff_max: Maximum delay cap in seconds.
        jitter: Fraction of the current delay added as random jitter
            (± *jitter* * delay).  Use 0.0 for no jitter.
        retryable_exceptions: Exception types that trigger a retry.
    """

    max_attempts: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 30.0
    jitter: float = 0.1
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: _DEFAULT_RETRYABLE,
    )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_base < 0:
            raise ValueError("backoff_base must be >= 0")
        if self.backoff_max < self.backoff_base:
            raise ValueError("backoff_max must be >= backoff_base")
        if not 0.0 <= self.jitter <= 1.0:
            raise ValueError("jitter must be between 0.0 and 1.0")

    def compute_delay(self, attempt: int) -> float:
        """Compute the delay for a given attempt index (1-based).

        Delay = min(backoff_base * 2^(attempt-1), backoff_max)
        with ±jitter applied.
        """
        if attempt <= 0:
            return 0.0
        base = min(
            self.backoff_base * (2 ** (attempt - 1)),
            self.backoff_max,
        )
        if self.jitter > 0:
            jitter_amount = base * self.jitter * random.uniform(-1.0, 1.0)
            base += jitter_amount
        return max(0.0, base)


class RetryExecutor:
    """Execute a callable with configurable retry + exponential backoff.

    Usage::

        policy = RetryPolicy(max_attempts=3)
        executor = RetryExecutor(policy)
        result = executor.execute(lambda: tool.dispatch(args),
                                  context="node_cpu_check")
    """

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self.policy = policy or RetryPolicy()

    def execute(
        self,
        fn: Callable[[], T],
        context: str = "",
    ) -> T:
        """Execute *fn*, retrying on transient failures.

        Args:
            fn: A zero-argument callable to execute.
            context: Optional label for log / debugging purposes.

        Returns:
            The return value of *fn* on success.

        Raises:
            Any non-retryable exception immediately.
            The last retryable exception after exhausting all attempts.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                return fn()
            except self.policy.retryable_exceptions as exc:
                last_exc = exc
                if attempt == self.policy.max_attempts:
                    break
                delay = self.policy.compute_delay(attempt)
                _time.sleep(delay)

        # Exhausted all attempts.
        msg = f"Retry exhausted after {self.policy.max_attempts} attempts" + (
            f" [context: {context}]" if context else ""
        )  # noqa: W503
        raise RuntimeError(msg) from last_exc
