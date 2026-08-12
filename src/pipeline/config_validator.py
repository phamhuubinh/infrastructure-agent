"""GA2-H06/H07/H08: safe, non-executing validation for generated config.

Validates generated technical artifacts with parser/structural checks only.
It NEVER executes deployment commands.  Supported artifact types:

- ``shell``          : shell-syntax check (shlex, no execution)
- ``yaml``           : generic YAML parse
- ``github_actions`` : YAML parse + GitHub Actions structural checks
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode


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
    def safe_repair(artifact_type: str, content: str) -> str | None:
        """Apply one narrow, syntax-preserving local formatting repair.

        Model replies sometimes prefix an otherwise complete YAML artifact
        with prose (for example, ``Here is the workflow:``) without using a
        Markdown fence. Removing only that preamble is safe: it neither adds
        nor changes configuration values. All other syntax defects are left
        untouched for an explicit validation warning.
        """
        if artifact_type not in {"yaml", "github_actions"}:
            return None
        start = re.search(
            r"(?m)^(?:---\s*\n)?(?:name|on|permissions|env|defaults|jobs):\s*",
            content,
        )
        if start is None or start.start() == 0:
            return None
        prefix = content[: start.start()]
        if not prefix.strip() or ":" not in prefix:
            return None
        return content[start.start() :].strip()

    @staticmethod
    def _shell(content: str) -> ValidationResult:
        """Parse shell syntax with ``sh -n``; never executes the snippet."""
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
        try:
            parsed = subprocess.run(
                ["sh", "-n"],
                input=content,
                text=True,
                capture_output=True,
                check=False,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ValidationResult(
                "shell",
                False,
                (ValidationIssue("error", f"Shell syntax check unavailable: {exc}"),),
            )
        if parsed.returncode != 0:
            detail = parsed.stderr.strip().splitlines()[-1][:180]
            return ValidationResult(
                "shell",
                False,
                (ValidationIssue("error", f"Shell syntax error: {detail}"),),
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
        document = yaml.compose(content)
        duplicate_keys = cls._duplicate_mapping_keys(document)
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            return ValidationResult(
                "github_actions",
                False,
                (ValidationIssue("error", "Workflow is missing a 'jobs' mapping."),),
            )
        issues: list[ValidationIssue] = [
            ValidationIssue("error", f"Duplicate YAML key '{key}'.")
            for key in duplicate_keys
        ]
        allowed_top_level = {
            "name",
            "on",
            "permissions",
            "env",
            "defaults",
            "concurrency",
            "jobs",
            "run-name",
        }
        for key in data:
            if key is True:
                continue
            if str(key) not in allowed_top_level:
                issues.append(
                    ValidationIssue(
                        "error", f"Unsupported workflow key '{key}'.",
                    )
                )
        for job_name, job in data["jobs"].items():
            if not isinstance(job, dict):
                issues.append(
                    ValidationIssue("error", f"Job '{job_name}' must be a mapping.")
                )
                continue
            if "uses" in job and any(key in job for key in ("runs-on", "steps")):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Job '{job_name}' mixes reusable 'uses' with steps/runs-on.",
                    )
                )
            if "uses" in job:
                continue
            if not isinstance(job.get("steps"), list):
                issues.append(
                    ValidationIssue("error", f"Job '{job_name}' has no steps list.")
                )
                continue
            steps = job["steps"]
            strategy = job.get("strategy")
            matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
            claims_matrix = "matrix" in str(job_name).casefold() or any(
                "matrix" in str(step.get("name", "")).casefold()
                for step in steps
                if isinstance(step, dict)
            )
            if claims_matrix and not isinstance(matrix, dict):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Job '{job_name}' claims a matrix but has no strategy.matrix mapping.",
                    )
                )
            if strategy is not None and not isinstance(strategy, dict):
                issues.append(
                    ValidationIssue(
                        "error", f"Job '{job_name}' has malformed strategy mapping."
                    )
                )
            if matrix is not None and not isinstance(matrix, dict):
                issues.append(
                    ValidationIssue(
                        "error", f"Job '{job_name}' has malformed strategy.matrix mapping."
                    )
                )
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

    @staticmethod
    def _duplicate_mapping_keys(node: Node | None) -> tuple[str, ...]:
        """Preserve duplicate-key signals that ``safe_load`` would discard."""
        if node is None:
            return ()
        duplicates: list[str] = []

        def visit(current: Node) -> None:
            if isinstance(current, MappingNode):
                seen: set[str] = set()
                for key, value in current.value:
                    key_name = (
                        key.value if isinstance(key, ScalarNode) else str(key.value)
                    )
                    if key_name in seen:
                        duplicates.append(key_name)
                    seen.add(key_name)
                    visit(value)
            elif hasattr(current, "value") and isinstance(current.value, list):
                for child in current.value:
                    if isinstance(child, tuple):
                        for item in child:
                            visit(item)
                    elif isinstance(child, Node):
                        visit(child)

        visit(node)
        return tuple(duplicates)


__all__ = ["ConfigValidator", "ValidationResult"]
