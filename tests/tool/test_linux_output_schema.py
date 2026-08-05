from __future__ import annotations

from src.tool.linux import _CAPABILITIES
from src.tool.linux.output_schema import validate_linux_output


def test_every_linux_capability_uses_schema_validation_boundary() -> None:
    # Generic capabilities require dict output; core capabilities receive
    # stricter per-field validation inside the same boundary.
    for action in _CAPABILITIES:
        errors = validate_linux_output(action, ["not", "a", "dict"])
        assert errors, action


def test_cpu_schema_rejects_missing_idle_measurement() -> None:
    errors = validate_linux_output(
        "get_cpu_usage",
        {"usage_percent": 20.0, "collection_strategy": "fixture"},
    )

    assert any("idle_percent" in error for error in errors)


def test_disk_io_schema_requires_explicit_byte_and_second_units() -> None:
    errors = validate_linux_output(
        "get_disk_io",
        {
            "fact_type": "disk.io",
            "counter_semantics": "cumulative_since_boot",
            "devices": [{"device": "sda", "read_bytes": 10}],
        },
    )

    assert any("written_bytes" in error for error in errors)
    assert any("read_time_seconds" in error for error in errors)


def test_service_schema_rejects_name_without_observed_state() -> None:
    errors = validate_linux_output("get_service", {"name": "nginx"})

    assert errors == ("service status contains no observed state fact",)
