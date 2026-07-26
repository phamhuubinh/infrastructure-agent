from __future__ import annotations

import itertools
from dataclasses import dataclass, field


@dataclass
class CredentialPool:
    """Round-robin key pool for providers that support multiple API keys.

    Useful when a provider has rate limits per key — the pool cycles
    through available keys to distribute load.

    Attributes:
        keys: List of API keys.  The pool cycles through these
            in order, returning to the start when exhausted.
    """

    keys: list[str] = field(default_factory=list)
    _iter: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._iter = itertools.cycle(self.keys)

    def next(self) -> str | None:
        """Return the next key in the rotation, or None if the pool is empty."""
        if not self.keys:
            return None
        return next(self._iter)  # type: ignore[call-overload]

    def __bool__(self) -> bool:
        return len(self.keys) > 0
