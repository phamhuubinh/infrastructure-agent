from __future__ import annotations

import pytest

from src.pipeline.parameter_binder import (
    ParameterBinder,
    ParameterBindingError,
)

_METADATA = {
    "parameter_specs": [
        {
            "name": "name",
            "source": "service_name",
            "required": True,
            "value_type": "str",
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$",
        }
    ]
}


@pytest.mark.parametrize(
    "value",
    ("nginx; rm -rf /", "nginx$(id)", "../nginx", "nginx\nspoof"),
)
def test_injection_strings_are_rejected(value: str) -> None:
    with pytest.raises(ParameterBindingError):
        ParameterBinder().bind(
            source="localhost",
            resource="get_service",
            metadata=_METADATA,
            extracted_params={"service_name": value},
        )


def test_valid_argument_is_an_argument_value_not_shell_text() -> None:
    bound = ParameterBinder().bind(
        source="localhost",
        resource="get_service",
        metadata=_METADATA,
        extracted_params={"service_name": "nginx.service"},
    )
    assert bound.arguments == {
        "source": "localhost",
        "resource": "get_service",
        "name": "nginx.service",
    }
