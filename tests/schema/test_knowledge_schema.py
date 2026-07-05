from __future__ import annotations

import pytest

from src.schema.knowledge_schema import validate


def test_validate_accepts_valid_resources() -> None:
    validate(
        {
            "resources": [
                "system.hostname",
                "memory.total",
            ],
        }
    )


def test_missing_resources() -> None:
    with pytest.raises(ValueError):
        validate({})


def test_resources_must_be_list() -> None:
    with pytest.raises(ValueError):
        validate(
            {
                "resources": "system.hostname",
            }
        )


def test_resources_must_not_be_empty() -> None:
    with pytest.raises(ValueError):
        validate(
            {
                "resources": [],
            }
        )


def test_resource_must_be_string() -> None:
    with pytest.raises(ValueError):
        validate(
            {
                "resources": [
                    123,
                ],
            }
        )


def test_resource_must_not_be_empty() -> None:
    with pytest.raises(ValueError):
        validate(
            {
                "resources": [
                    "",
                ],
            }
        )
