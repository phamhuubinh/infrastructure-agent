"""Replaceable external integration boundaries."""

from orion.integrations.internet import (
    InternetClient,
    InternetClientError,
    InternetFetch,
    InternetSearchResult,
    InternetStatus,
    SearxngInternetClient,
    UnavailableInternetClient,
)

__all__ = [
    "InternetClient",
    "InternetClientError",
    "InternetFetch",
    "InternetSearchResult",
    "InternetStatus",
    "SearxngInternetClient",
    "UnavailableInternetClient",
]
