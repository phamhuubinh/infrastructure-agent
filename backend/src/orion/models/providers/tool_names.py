"""Reversible projection from canonical names to restricted vendor identifiers."""

from __future__ import annotations

import hashlib

from orion.contracts import ToolDefinition
from orion.models.backend import ModelBackendError, ModelBackendErrorKind


class ToolNameMap:
    def __init__(self, tools: tuple[ToolDefinition, ...]) -> None:
        self._canonical: dict[str, str] = {}
        self._wire: dict[str, str] = {}
        for tool in tools:
            wire = "t_" + hashlib.sha256(tool.name.encode()).hexdigest()[:60]
            if tool.name in self._canonical or wire in self._wire:
                raise ModelBackendError(
                    "Tool name projection contains duplicate identifiers.",
                    kind=ModelBackendErrorKind.PROTOCOL,
                )
            self._canonical[tool.name] = wire
            self._wire[wire] = tool.name

    def to_wire(self, canonical: str) -> str:
        try:
            return self._canonical[canonical]
        except KeyError:
            raise ModelBackendError(
                "Model history references an unavailable canonical tool.",
                kind=ModelBackendErrorKind.PROTOCOL,
            ) from None

    def to_canonical(self, wire: str) -> str:
        try:
            return self._wire[wire]
        except KeyError:
            raise ModelBackendError(
                "Provider returned a tool outside the advertised registry.",
                kind=ModelBackendErrorKind.PROTOCOL,
            ) from None
