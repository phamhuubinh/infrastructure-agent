"""Canonical model backend contract for Orion.

A model backend owns text/model I/O only. It does not classify intent,
select capabilities, resolve targets or sources, grant authority, or execute.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from src.shared.language import detect_language
from src.shared.logger import warning as _warning


MODEL_UNCONFIGURED_MESSAGE = (
    "Chưa cấu hình model. Hãy mở Cài đặt → Model hoặc dùng lệnh "
    "`orion model add` rồi chạy kiểm tra kết nối."
)

MODEL_UNCONFIGURED_MESSAGE_EN = (
    "No model is configured. Open Settings → Model or use "
    "`orion model add`, then run the connection test."
)


@runtime_checkable
class AgentModelBackend(Protocol):
    """Minimal model-I/O boundary used by the canonical runtime."""

    def complete(
        self,
        prompt: str,
    ) -> str:
        """Return one model completion."""

    def health_check(
        self,
        timeout: float = 5.0,
    ) -> bool:
        """Return whether the configured backend is reachable."""


def model_unconfigured_message(
    raw_request: str,
) -> str:
    return (
        MODEL_UNCONFIGURED_MESSAGE_EN
        if detect_language(raw_request) == "en"
        else MODEL_UNCONFIGURED_MESSAGE
    )


class UnconfiguredAgentBackend:
    """Setup-mode backend used when no model is configured."""

    def complete(
        self,
        _prompt: str,
    ) -> str:
        return MODEL_UNCONFIGURED_MESSAGE

    def health_check(
        self,
        timeout: float = 5.0,
    ) -> bool:
        del timeout
        return False


class FallbackAgentBackend:
    """Ordered canonical model-backend fallback chain."""

    def __init__(
        self,
        backends: Sequence[
            AgentModelBackend
        ],
    ) -> None:
        resolved = tuple(backends)

        if not resolved:
            raise ValueError(
                "FallbackAgentBackend requires "
                "at least one backend."
            )

        if not all(
            isinstance(
                backend,
                AgentModelBackend,
            )
            for backend in resolved
        ):
            raise TypeError(
                "All fallback entries must "
                "implement AgentModelBackend."
            )

        self._backends = resolved

    @property
    def backends(
        self,
    ) -> tuple[
        AgentModelBackend,
        ...,
    ]:
        return self._backends

    def complete(
        self,
        prompt: str,
    ) -> str:
        failures: list[str] = []

        for backend in self._backends:
            try:
                return backend.complete(
                    prompt
                )
            except (
                ConnectionError,
                TimeoutError,
                OSError,
                RuntimeError,
            ) as exc:
                name = type(
                    backend
                ).__name__

                failures.append(
                    f"{name}: {exc}"
                )

                _warning(
                    "fallback",
                    backend=name,
                    error=str(exc)[:120],
                    message=(
                        "Model backend failed, "
                        "trying next"
                    ),
                )

        raise RuntimeError(
            "All model backends exhausted. "
            "Errors:\n  "
            + "\n  ".join(
                f"[{index}] {failure}"
                for index, failure
                in enumerate(
                    failures,
                    start=1,
                )
            )
        )

    def health_check(
        self,
        timeout: float = 5.0,
    ) -> bool:
        for backend in self._backends:
            try:
                if backend.health_check(
                    timeout=timeout
                ):
                    return True
            except Exception:
                continue

        return False


__all__ = [
    "AgentModelBackend",
    "FallbackAgentBackend",
    "MODEL_UNCONFIGURED_MESSAGE",
    "MODEL_UNCONFIGURED_MESSAGE_EN",
    "UnconfiguredAgentBackend",
    "model_unconfigured_message",
]
