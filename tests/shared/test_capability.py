from __future__ import annotations

import pytest

from src.shared.capability import Capability


def test_capability_environment_metadata_defaults_are_safe() -> None:
    capability = Capability(name="get_value", handler=lambda: None)

    assert capability.preconditions == ()
    assert capability.required_binaries == ()
    assert capability.required_any_binaries == ()
    assert capability.optional_binaries == ()
    assert capability.expected_reliability == 1.0
    assert capability.produces_facts == ()
    assert capability.mutation_risk == "none"


def test_capability_rejects_invalid_reliability() -> None:
    with pytest.raises(ValueError, match="expected_reliability"):
        Capability(
            name="get_value",
            handler=lambda: None,
            expected_reliability=1.1,
        )


def test_capability_rejects_unknown_mutation_risk() -> None:
    with pytest.raises(ValueError, match="mutation_risk"):
        Capability(
            name="get_value",
            handler=lambda: None,
            mutation_risk="mystery",
        )
