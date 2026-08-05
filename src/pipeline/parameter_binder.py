"""Metadata-driven capability parameter binding and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.pipeline.security.parameter_safety_inspector import _is_dangerous


class ParameterBindingError(ValueError):
    def __init__(self, parameter: str, reason: str) -> None:
        self.parameter = parameter
        self.reason = reason
        super().__init__(f"Invalid parameter '{parameter}': {reason}")


class MissingParameterError(ParameterBindingError):
    def __init__(self, parameter: str) -> None:
        super().__init__(parameter, "required value is missing")


@dataclass(frozen=True, slots=True)
class BoundParameters:
    arguments: dict[str, object]
    extracted: dict[str, object]


class ParameterBinder:
    """Bind canonical extracted values using child-capability metadata."""

    def bind(
        self,
        *,
        source: str,
        resource: str,
        metadata: dict[str, object],
        extracted_params: object = None,
        timeframe: object = None,
    ) -> BoundParameters:
        extracted = self._as_dict(extracted_params)
        extracted["__timeframe__"] = timeframe
        arguments: dict[str, object] = {"source": source, "resource": resource}
        raw_specs = metadata.get("parameter_specs", [])
        specs = raw_specs if isinstance(raw_specs, list) else []

        for raw_spec in specs:
            if not isinstance(raw_spec, dict):
                continue
            name = str(raw_spec.get("name") or "")
            if not name:
                continue
            source_name = str(raw_spec.get("source") or name)
            value = self._source_value(extracted, source_name)
            if value is None and bool(raw_spec.get("has_default")):
                value = raw_spec.get("default")
            if value is None:
                if bool(raw_spec.get("required")):
                    raise MissingParameterError(name)
                continue
            arguments[name] = self._validate(name, value, raw_spec)

        extracted.pop("__timeframe__", None)
        return BoundParameters(arguments=arguments, extracted=extracted)

    @staticmethod
    def _as_dict(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return dict(value)
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            result = to_dict()
            if isinstance(result, dict):
                return dict(result)
        return {}

    @staticmethod
    def _source_value(values: dict[str, object], source: str) -> object | None:
        if source.startswith("timeframe."):
            timeframe = values.get("__timeframe__")
            return getattr(timeframe, source.partition(".")[2], None)
        return values.get(source)

    def _validate(
        self,
        name: str,
        value: object,
        spec: dict[str, object],
    ) -> object:
        value_type = str(spec.get("value_type") or "str")
        if value_type == "int":
            if isinstance(value, bool):
                raise ParameterBindingError(name, "boolean is not an integer")
            if not isinstance(value, (str, int, float)):
                raise ParameterBindingError(name, "must be an integer")
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ParameterBindingError(name, "must be an integer") from exc
        elif value_type == "float":
            if isinstance(value, bool):
                raise ParameterBindingError(name, "boolean is not numeric")
            if not isinstance(value, (str, int, float)):
                raise ParameterBindingError(name, "must be numeric")
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise ParameterBindingError(name, "must be numeric") from exc
        elif value_type == "str":
            if not isinstance(value, str):
                raise ParameterBindingError(name, "must be a string")

        if isinstance(value, str):
            danger = _is_dangerous(value)
            if danger:
                raise ParameterBindingError(name, danger)
            pattern = spec.get("pattern")
            if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
                raise ParameterBindingError(name, "does not match the allowed pattern")

        enum = spec.get("enum")
        if isinstance(enum, list) and enum and value not in enum:
            raise ParameterBindingError(name, "is not an allowed value")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = spec.get("minimum")
            maximum = spec.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                raise ParameterBindingError(name, f"must be at least {minimum}")
            if isinstance(maximum, (int, float)) and value > maximum:
                raise ParameterBindingError(name, f"must be at most {maximum}")
        return value
