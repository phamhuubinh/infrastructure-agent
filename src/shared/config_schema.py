from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Server config (servers.json)
# ---------------------------------------------------------------------------


class ServerConfig(BaseModel):
    """Configuration for a single model server."""

    base_url: str
    api_key: str | None = None
    model: str = "gpt-4"
    provider: str | None = None
    timeout: int = Field(default=60, ge=1, le=300)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)


class ServersConfig(BaseModel):
    """Top-level servers.json schema."""

    active_server: str = ""
    servers: dict[str, ServerConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def active_must_exist(self) -> ServersConfig:
        if not self.servers:
            if self.active_server:
                raise ValueError(
                    "active_server must be empty when no model is configured"
                )
            return self
        if self.active_server not in self.servers:
            available = ", ".join(sorted(self.servers))
            raise ValueError(
                f"active_server '{self.active_server}' is not defined "
                f"in servers. Available servers: {available}"
            )
        return self


# ---------------------------------------------------------------------------
# Tool config (tools.json)
# ---------------------------------------------------------------------------


class ToolEntry(BaseModel):
    """A single tool entry in tools.json."""

    model_config = {"extra": "allow"}

    tool: str
    url: str | None = None
    token: str | None = None
    target: str | None = None
    timeout: int | None = None


def _validate_tools_dict(data: dict[str, Any]) -> dict[str, ToolEntry]:
    """Validate each entry in tools.json against ToolEntry."""
    result: dict[str, ToolEntry] = {}
    for name, entry in data.items():
        if isinstance(entry, dict):
            result[name] = ToolEntry.model_validate(entry)
        else:
            raise ValueError(
                f"tools.json entry '{name}' must be a JSON object, "
                f"got {type(entry).__name__}"
            )
    return result


# ---------------------------------------------------------------------------
# Target config (targets.json)
# ---------------------------------------------------------------------------


class TargetEntry(BaseModel):
    """A single target entry in targets.json."""

    model_config = {"extra": "allow"}

    backend: str
    host: str | None = None
    user: str | None = None


class TargetsConfig(BaseModel):
    """Top-level targets.json schema."""

    default: str | None = None
    targets: dict[str, TargetEntry]


# ---------------------------------------------------------------------------
# Deterministic rule config (config/rules/*.yaml)
# ---------------------------------------------------------------------------


class WeightedConditionConfig(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
    operator: Literal["gt", "ge", "lt", "le", "eq", "ne"]
    threshold: Any
    weight: float = Field(gt=0)
    required: bool = True
    subject: str | None = None
    target: str | None = None
    max_age_seconds: float | None = Field(default=None, ge=0)


class AtomicRuleConfig(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
    operator: Literal["gt", "ge", "lt", "le", "eq", "ne"]
    threshold: float
    severity: Literal["info", "warning", "critical"]
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    owner: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_cases: tuple[str, ...] = Field(min_length=1)
    required_context: tuple[str, ...] = ()
    review_status: Literal["approved"]

    def to_domain(self):
        from src.pipeline.threshold_evaluator import AtomicRule

        return AtomicRule(
            id=self.id,
            metric=self.metric,
            operator=self.operator,
            threshold=self.threshold,
            severity=self.severity,
            version=self.version,
            required_context=self.required_context,
            owner=self.owner,
            rationale=self.rationale,
            source_cases=self.source_cases,
        )


class CompositeRuleConfig(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    conditions: tuple[WeightedConditionConfig, ...] = Field(min_length=1)
    decision_threshold: float = Field(gt=0)
    minimum_coverage: float = Field(default=0.0, ge=0, le=1)
    renormalize_missing: bool = False
    severity: Literal["info", "warning", "critical"]
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    owner: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_cases: tuple[str, ...] = Field(min_length=1)
    review_status: Literal["approved"]

    @model_validator(mode="after")
    def threshold_must_fit_total_weight(self) -> CompositeRuleConfig:
        total = sum(condition.weight for condition in self.conditions)
        if self.decision_threshold > total:
            raise ValueError("decision_threshold exceeds total condition weight")
        ids = [condition.id for condition in self.conditions]
        if len(ids) != len(set(ids)):
            raise ValueError("condition ids must be unique")
        return self

    def to_domain(self):
        from src.pipeline.composite_rule import CompositeRule, WeightedCondition

        return CompositeRule(
            id=self.id,
            type=self.type,
            conditions=tuple(
                WeightedCondition(**condition.model_dump())
                for condition in self.conditions
            ),
            decision_threshold=self.decision_threshold,
            minimum_coverage=self.minimum_coverage,
            renormalize_missing=self.renormalize_missing,
            severity=self.severity,
            version=self.version,
            owner=self.owner,
            rationale=self.rationale,
            source_cases=self.source_cases,
        )


class RuleConfigFile(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: Literal["reasoning.v1"]
    atomic_rules: tuple[AtomicRuleConfig, ...] = ()
    composite_rules: tuple[CompositeRuleConfig, ...] = ()

    @model_validator(mode="after")
    def rule_ids_must_be_unique(self) -> RuleConfigFile:
        ids = [rule.id for rule in self.atomic_rules + self.composite_rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique within a config file")
        return self


def load_rule_configs(path: Path | None = None) -> tuple[RuleConfigFile, ...]:
    """Load every reviewed rule file in deterministic filename order."""

    rules_dir = path or (_project_root() / "config" / "rules")
    if not rules_dir.exists():
        return ()
    loaded: list[RuleConfigFile] = []
    seen: set[str] = set()
    for rule_path in sorted(rules_dir.glob("*.yaml")):
        data = yaml.safe_load(rule_path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"{rule_path.name} must contain a YAML object")
        config = RuleConfigFile.model_validate(data)
        for rule in config.atomic_rules + config.composite_rules:
            if rule.id in seen:
                raise ValueError(f"duplicate rule id across config files: {rule.id}")
            seen.add(rule.id)
        loaded.append(config)
    return tuple(loaded)


# ---------------------------------------------------------------------------
# Validation entry point
# ---------------------------------------------------------------------------


class ConfigValidationError(Exception):
    """Raised when one or more configuration files fail schema validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        detail = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Configuration validation failed:\n{detail}")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _servers_path() -> Path:
    configured = os.environ.get("ORION_SERVERS_FILE", "").strip()
    return Path(configured) if configured else _project_root() / "servers.json"


def _load_json(path: Path) -> dict[str, Any]:
    """Load and parse a JSON file, returning the parsed dict."""
    raw = path.read_text()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object at the top level")
    return data


def validate_all_configs() -> None:
    """Validate servers.json, tools.json, and targets.json at startup.

    Raises:
        ConfigValidationError: if any config file fails validation.
    """
    root = _project_root()
    errors: list[str] = []

    # --- servers.json ---
    servers_path = _servers_path()
    if servers_path.exists():
        try:
            data = _load_json(servers_path)
            ServersConfig.model_validate(data)
        except Exception as exc:
            errors.append(f"servers.json: {exc}")

    # --- tools.json ---
    tools_path = root / "tools.json"
    if tools_path.exists():
        try:
            data = _load_json(tools_path)
            _validate_tools_dict(data)
        except Exception as exc:
            errors.append(f"tools.json: {exc}")

    # --- targets.json ---
    targets_path = root / "targets.json"
    if targets_path.exists():
        try:
            data = _load_json(targets_path)
            TargetsConfig.model_validate(data)
        except Exception as exc:
            errors.append(f"targets.json: {exc}")

    # --- config/rules/*.yaml ---
    try:
        load_rule_configs(root / "config" / "rules")
    except Exception as exc:
        errors.append(f"config/rules: {exc}")

    if errors:
        raise ConfigValidationError(errors)
