"""GA2-H06/H07/H08: safe, non-executing validation for generated config.

Validates generated technical artifacts with parser/structural checks only.
It NEVER executes deployment commands.  Supported artifact types:

- ``shell``          : shell-syntax check (shlex, no execution)
- ``yaml``           : generic YAML parse
- ``github_actions`` : YAML parse + GitHub Actions structural checks
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

import yaml


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    kind: str  # error | warning
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "message": self.message}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    artifact_type: str
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_type": self.artifact_type,
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
        }


_MUTATING_WORDS = frozenset(
    {
        "rm ",
        "reboot",
        "shutdown",
        "mkfs",
        "fdisk",
        "systemctl stop",
        "systemctl restart",
        "systemctl enable",
        "systemctl disable",
    }
)


class ConfigValidator:
    """Deterministic, non-executing validation by artifact type."""

    @classmethod
    def validate(cls, artifact_type: str, content: str) -> ValidationResult:
        if artifact_type == "shell":
            return cls._shell(content)
        if artifact_type == "yaml":
            return cls._yaml(content)
        if artifact_type == "github_actions":
            return cls._github_actions(content)
        return ValidationResult(
            artifact_type,
            False,
            (
                ValidationIssue(
                    "error", f"Unsupported artifact type '{artifact_type}'."
                ),
            ),
        )

    @staticmethod
    def _shell(content: str) -> ValidationResult:
        """Syntax-only shell check using shlex; never executes anything."""
        if not content.strip():
            return ValidationResult(
                "shell", False, (ValidationIssue("error", "Shell snippet is empty."),)
            )
        try:
            list(shlex.shlex(content, posix=True))
        except ValueError as exc:
            return ValidationResult(
                "shell",
                False,
                (ValidationIssue("error", f"Shell syntax error: {exc}"),),
            )
        lower = content.casefold()
        warning = (
            (
                ValidationIssue(
                    "warning",
                    "Snippet contains a mutating/administrative command; Orion "
                    "does not execute it.",
                ),
            )
            if any(word in lower for word in _MUTATING_WORDS)
            else ()
        )
        return ValidationResult("shell", True, warning)

    @staticmethod
    def _yaml(content: str) -> ValidationResult:
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as exc:
            return ValidationResult(
                "yaml", False, (ValidationIssue("error", f"YAML parse error: {exc}"),)
            )
        return ValidationResult("yaml", True)

    @classmethod
    def _github_actions(cls, content: str) -> ValidationResult:
        """YAML + GitHub Actions structural checks (no network)."""
        base = cls._yaml(content)
        if not base.valid:
            return base
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or "jobs" not in data:
            return ValidationResult(
                "github_actions",
                False,
                (ValidationIssue("error", "Workflow is missing a 'jobs' mapping."),),
            )
        issues: list[ValidationIssue] = []
        for job_name, job in data["jobs"].items():
            if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
                issues.append(
                    ValidationIssue("error", f"Job '{job_name}' has no steps list.")
                )
                continue
            steps = job["steps"]
            seen_out: set[str] = set()
            for step in steps:
                if isinstance(step, dict) and step.get("id"):
                    seen_out.add(str(step["id"]))
            for step in steps:
                if not isinstance(step, dict):
                    continue
                run = step.get("run")
                if isinstance(run, str):
                    for ref in run.split():
                        if ref.startswith("steps."):
                            segment = ref.split(".")[1] if ref.count(".") >= 1 else ""
                            if segment and segment not in seen_out:
                                issues.append(
                                    ValidationIssue(
                                        "error",
                                        f"Step references nonexistent output '{ref}'.",
                                    )
                                )
        # GitHub Actions uses the YAML key "on" which YAML 1.1 parsers may
        # treat as the boolean True; accept both spellings.
        on_value = data.get("on")
        if on_value is None:
            for key, value in data.items():
                if key is True and isinstance(value, dict):
                    on_value = value
                    break
        if isinstance(on_value, dict):
            schedule = on_value.get("schedule")
            if isinstance(schedule, list):
                for item in schedule:
                    if isinstance(item, dict) and "cron" in item:
                        parts = str(item["cron"]).split()
                        if len(parts) != 5:
                            issues.append(
                                ValidationIssue(
                                    "error", f"Invalid schedule cron: '{item['cron']}'."
                                )
                            )
        return ValidationResult(
            "github_actions",
            not any(i.kind == "error" for i in issues),
            tuple(issues),
        )


__all__ = ["ConfigValidator", "ValidationResult"]
