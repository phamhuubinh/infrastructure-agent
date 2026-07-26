from __future__ import annotations

import re

from src.pipeline.security.tool_inspector import (
    InspectionContext,
    InspectionResult,
    InspectionVerdict,
    ToolInspector,
)

# Patterns that indicate potentially dangerous parameter values.
# These are intentionally broad — false positives are acceptable
# because they result in a DENY that can be investigated.
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Shell injection patterns.
    (r"[;|&`$]", "shell metacharacter detected"),
    # Command substitution.
    (r"\$\(.*\)", "command substitution detected"),
    # Backtick substitution.
    (r"`[^`]*`", "backtick command substitution detected"),
    # Path traversal.
    (r"\.\./", "path traversal detected"),
    (r"\.\.\\", "path traversal detected"),
    # URL schemes that could be used for exfiltration.
    (r"^file://", "file:// URL scheme detected"),
    # Pipe redirection.
    (r">\s*/", "output redirection to path detected"),
    (r">>\s*/", "append redirection to path detected"),
    # Null byte injection.
    (r"\x00", "null byte injection detected"),
    # SQL injection heuristics (broad — catches most injection attempts).
    (r"(?i)(\bOR\b.*=.*\bOR\b)", "potential SQL injection pattern"),
    (r"(?i)(\bUNION\b.*\bSELECT\b)", "potential SQL UNION injection"),
    (r"(?i)(\bDROP\b\s+\bTABLE\b)", "DROP TABLE statement detected"),
    (r"(?i)(\bDELETE\b\s+\bFROM\b)", "DELETE FROM statement detected"),
    # Embedded newlines in parameter values (log injection).
    (r"\n", "newline character in parameter value"),
    (r"\r", "carriage return in parameter value"),
    # Long parameter values (>1000 chars) may indicate injection attempts.
]

_MAX_PARAMETER_LENGTH = 1000


def _is_dangerous(value: str) -> str | None:
    """Check if a string value matches any dangerous pattern.

    Returns the reason string if dangerous, None if safe.
    """
    if len(value) > _MAX_PARAMETER_LENGTH:
        return f"parameter value exceeds maximum length ({_MAX_PARAMETER_LENGTH})"

    for pattern, reason in _DANGEROUS_PATTERNS:
        if re.search(pattern, value):
            return reason

    return None


class ParameterSafetyInspector(ToolInspector):
    """Inspector that validates tool execution parameters for safety.

    Scans all parameter values for dangerous patterns including:
    - Shell injection (metacharacters, command substitution)
    - Path traversal (``../``)
    - SQL injection heuristics
    - URL-based file access
    - Output redirection
    - Null byte injection
    - Log injection (embedded newlines)
    - Excessively long values

    This inspector is run on every tool dispatch to prevent
    injection attacks through user-controlled parameters.
    """

    @property
    def name(self) -> str:
        return "ParameterSafetyInspector"

    def inspect(self, context: InspectionContext) -> InspectionResult:
        # Check all string argument values.
        for key, value in context.arguments.items():
            if not isinstance(value, str):
                continue

            # Skip known-safe keys that are validated elsewhere.
            if key in ("source", "resource", "action"):
                continue

            danger = _is_dangerous(value)
            if danger is not None:
                return InspectionResult(
                    verdict=InspectionVerdict.DENY,
                    reason=(f"Dangerous parameter '{key}={value[:80]}': {danger}"),
                    inspector_name=self.name,
                )

        return InspectionResult(
            verdict=InspectionVerdict.ALLOW,
            inspector_name=self.name,
        )
