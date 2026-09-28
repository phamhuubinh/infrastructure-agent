from __future__ import annotations

import pytest

from orion.security import redact_public, redact_text


def test_redact_public_preserves_nested_shapes_and_redacts_each_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORION_AUDIT_SECRET_TOKEN", "local-secret-value")
    value = {
        "items": [
            "local-secret-value",
            ("Authorization: Bearer local-secret-value", "ORION_TEST_SECRET_TOKEN"),
        ],
        12: "https://alice:local-secret-value@example.test/path",
    }

    assert redact_public(value) == {
        "items": [
            "[REDACTED]",
            ("Authorization: Bearer [REDACTED]", "[REDACTED]"),
        ],
        "12": "https://[REDACTED]@example.test/path",
    }


def test_redaction_reads_current_environment_on_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORION_AUDIT_SECRET_TOKEN", "first-secret")
    assert redact_text("first-secret second-secret") == "[REDACTED] second-secret"

    monkeypatch.setenv("ORION_AUDIT_SECRET_TOKEN", "second-secret")
    assert redact_public(["first-secret", "second-secret"]) == [
        "first-secret",
        "[REDACTED]",
    ]
