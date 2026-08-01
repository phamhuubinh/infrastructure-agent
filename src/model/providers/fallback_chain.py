from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.shared.logger import warning as _warning


class FallbackChain:
    """Ordered list of providers tried in sequence on failure.

    Each provider is tried in order.  If a call raises ConnectionError,
    TimeoutError, OSError, or RuntimeError, the next provider is tried.
    If all providers are exhausted, RuntimeError is raised.

    Usage::

        chain = FallbackChain([adapter1, adapter2, adapter3])
        result = chain.execute_with_fallback(
            lambda a: a.assess(request)
        )
    """

    def __init__(self, adapters: list[AssessmentModelAdapter]) -> None:
        if not adapters:
            raise ValueError("FallbackChain requires at least one adapter")
        self._chain = adapters

    @property
    def chain(self) -> list[AssessmentModelAdapter]:
        return list(self._chain)

    def execute_with_fallback(self, fn: Callable[[AssessmentModelAdapter], Any]) -> Any:
        """Call *fn* on each adapter in order until one succeeds.

        Args:
            fn: A callable that receives an AssessmentModelAdapter and
                returns a result.  Exceptions are caught to trigger
                fallback to the next provider.

        Returns:
            The first successful result from *fn*.

        Raises:
            RuntimeError: If all providers in the chain fail.
        """
        errors: list[str] = []
        for adapter in self._chain:
            try:
                return fn(adapter)
            except (ConnectionError, TimeoutError, OSError, RuntimeError) as exc:
                adapter_name = type(adapter).__name__
                err_msg = f"{adapter_name}: {exc}"
                errors.append(err_msg)
                _warning(
                    "fallback",
                    adapter=adapter_name,
                    error=str(exc)[:120],
                    message="Provider failed, trying next",
                )
        raise RuntimeError(
            "All providers exhausted. Errors:\n  "
            + "\n  ".join(f"[{i + 1}] {e}" for i, e in enumerate(errors))
        )
