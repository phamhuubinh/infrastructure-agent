from __future__ import annotations

import re

import pytest

from orion.models.backend import ModelBackendError
from orion.models.providers.tool_names import ToolNameMap
from orion.tool_runtime.calculator import calculator_definition


def test_native_projection_is_legal_stable_reversible_and_avoids_separator_collisions():
    base = calculator_definition()
    names = ("system.command.run", "system_command_run", "mcp.server.tool", "a" * 200)
    definitions = tuple(base.model_copy(update={"name": name}) for name in names)
    mapping = ToolNameMap(definitions)
    projected = [mapping.to_wire(name) for name in names]
    assert len(set(projected)) == len(names)
    for canonical, wire in zip(names, projected, strict=True):
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", wire)
        assert mapping.to_canonical(wire) == canonical
        assert ToolNameMap(tuple(reversed(definitions))).to_wire(canonical) == wire


def test_unknown_wire_names_and_unavailable_history_are_rejected_without_echo():
    mapping = ToolNameMap((calculator_definition(),))
    for method in (mapping.to_wire, mapping.to_canonical):
        with pytest.raises(ModelBackendError) as caught:
            method("private-unadvertised-name")
        assert "private-unadvertised-name" not in str(caught.value)
    with pytest.raises(ModelBackendError, match="duplicate"):
        ToolNameMap((calculator_definition(), calculator_definition()))
