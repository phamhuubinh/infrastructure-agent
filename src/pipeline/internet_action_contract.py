"""Typed high-level Internet actions exposed to the Agent v2 controller."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

INTERNET_CURRENT_CAPABILITY_ID = "internet.current"
INTERNET_FETCH_URL_CAPABILITY_ID = "internet.fetch_url"


class InternetActionKind(str, Enum):
    CURRENT = "current"
    FETCH_URL = "fetch_url"


class InternetActionBindingError(ValueError):
    """Raised when a closed Internet action cannot be bound safely."""


@dataclass(frozen=True, slots=True)
class InternetActionRequest:
    """One immutable model-controlled Internet input and nothing else."""

    kind: InternetActionKind
    queries: tuple[str, ...] = ()
    url: str | None = None

    @property
    def query(self) -> str | None:
        """Compatibility view for callers that only support one query."""
        return self.queries[0] if len(self.queries) == 1 else None

    def __post_init__(self) -> None:
        if self.kind is InternetActionKind.CURRENT:
            if self.url is not None or not 1 <= len(self.queries) <= 3:
                raise ValueError(
                    "current action requires one to three bounded queries."
                )
            if any(not _bounded_text(query, 1_000) for query in self.queries):
                raise ValueError("current action requires bounded queries.")
        elif self.kind is InternetActionKind.FETCH_URL:
            if self.queries or not _http_url(self.url):
                raise ValueError(
                    "fetch_url action requires only a public HTTP URL shape."
                )
        else:  # pragma: no cover - Enum construction makes this defensive.
            raise TypeError("kind must be an InternetActionKind.")


def internet_current_arguments_schema() -> dict[str, object]:
    # The controller disclosure protocol deliberately uses a closed, fully
    # required schema.  Legacy ``query`` callers are normalized before this
    # schema is applied by AgentActionValidator.
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "queries": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 1, "maxLength": 1_000},
            },
        },
        "required": ["queries"],
    }


def internet_fetch_url_arguments_schema() -> dict[str, object]:
    return _schema("url", 2_048)


def bind_internet_action(
    capability_id: str, arguments: dict[str, object] | object
) -> InternetActionRequest:
    """Bind an already schema-validated action without accepting extra authority."""

    if not isinstance(arguments, dict):
        arguments = dict(arguments) if hasattr(arguments, "items") else None
    if not isinstance(arguments, dict):
        raise InternetActionBindingError("invalid_arguments")
    if capability_id == INTERNET_CURRENT_CAPABILITY_ID:
        try:
            query = arguments.get("query")
            raw_queries = arguments.get("queries")
            if query is not None and raw_queries is not None:
                raise ValueError("query and queries are mutually exclusive")
            if raw_queries is None:
                queries = (query,) if isinstance(query, str) else ()
            elif isinstance(raw_queries, (list, tuple)):
                queries = tuple(raw_queries)
            else:
                queries = ()
            return InternetActionRequest(InternetActionKind.CURRENT, queries=queries)
        except (TypeError, ValueError) as exc:
            raise InternetActionBindingError("invalid_query") from exc
    if capability_id == INTERNET_FETCH_URL_CAPABILITY_ID:
        try:
            return InternetActionRequest(
                InternetActionKind.FETCH_URL, url=arguments.get("url")
            )
        except (TypeError, ValueError) as exc:
            raise InternetActionBindingError("invalid_url") from exc
    raise InternetActionBindingError("unknown_internet_action")


def _schema(name: str, maximum: int) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {name: {"type": "string", "minLength": 1, "maxLength": maximum}},
        "required": [name],
    }


def _bounded_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _http_url(value: object) -> bool:
    if not _bounded_text(value, 2_048) or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


__all__ = [
    "INTERNET_CURRENT_CAPABILITY_ID",
    "INTERNET_FETCH_URL_CAPABILITY_ID",
    "InternetActionBindingError",
    "InternetActionKind",
    "InternetActionRequest",
    "bind_internet_action",
    "internet_current_arguments_schema",
    "internet_fetch_url_arguments_schema",
]
