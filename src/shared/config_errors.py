"""
Configuration error handling policy.

Provides a consistent exception hierarchy and error formatter for all
configuration errors.  The policy is:

1. Missing required config → ``MissingConfigFileError`` at startup.
   Fail fast, fail loud, fail with context.
2. Missing optional config → Warn via ``_warn()``, continue with safe defaults.
3. Invalid config value → ``InvalidConfigValueError`` at startup.
   Report file, key, expected type, received value.
4. All errors collected before exit → Don't fail on first error.
   Validate all configs, report all errors together, then exit.
"""

from __future__ import annotations

from collections.abc import Sequence


class ConfigurationError(Exception):
    """Base class for all configuration errors."""

    def __init__(self, file: str, key: str, expected: str, received: str) -> None:
        self.file = file
        self.key = key
        self.expected = expected
        self.received = received
        super().__init__(self.format())

    def format(self) -> str:
        return (
            f"Configuration error in {self.file}:\n"
            f"  Key: {self.key}\n"
            f"  Expected: {self.expected}\n"
            f"  Received: {self.received}"
        )


class MissingConfigFileError(ConfigurationError):
    """Config file does not exist."""


class InvalidConfigValueError(ConfigurationError):
    """Config value has wrong type or invalid value."""


class MissingRequiredKeyError(ConfigurationError):
    """Required key is missing from config."""


def format_error_batch(errors: Sequence[ConfigurationError]) -> str:
    """Format a list of configuration errors for reporting.

    Each error's ``format()`` output is joined with a double newline
    for readability.
    """
    return "\n\n".join(err.format() for err in errors)
