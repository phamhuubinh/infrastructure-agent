"""Unified configuration accessor — single entry point for all 11 config sources.

Usage:
    from src.shared.config import get_config
    config = get_config()
    model_name = config.active_server.get("model", "")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# OrionConfig — aggregates all configuration sources
# ---------------------------------------------------------------------------


@dataclass
class OrionConfig:
    """Single accessor for all Orion configuration sources (11 total).

    Load once at startup via ``OrionConfig.load()``, then access
    read-only via ``get_config()``.
    """

    project_root: Path = field(default_factory=Path.cwd)

    # --- servers.json -------------------------------------------------------
    servers: dict[str, Any] = field(default_factory=dict)
    active_server_name: str = ""
    fallback_chain: list[str] = field(default_factory=list)
    credential_pool: dict[str, list[str]] = field(default_factory=dict)

    # --- tools.json ---------------------------------------------------------
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)

    # --- targets.json -------------------------------------------------------
    targets: dict[str, Any] = field(default_factory=dict)

    # --- config/secrets.local.json ------------------------------------------
    secrets: dict[str, Any] = field(default_factory=dict)

    # --- config/conversational_patterns.yaml --------------------------------
    vi_patterns: list[str] = field(default_factory=list)
    en_patterns: list[str] = field(default_factory=list)
    conv_question_mark: bool = True
    conv_equivalence_markers: list[str] = field(
        default_factory=lambda: [" là ", " is ", "=", "->"]
    )

    # --- config/capability_plans.yaml ---------------------------------------
    capability_plans: dict[str, Any] = field(default_factory=dict)

    # --- config/concepts.yaml ------------------------------------------------
    concepts: dict[str, Any] = field(default_factory=dict)

    # --- config/target_aliases.yaml -----------------------------------------
    target_aliases: dict[str, str] = field(default_factory=dict)

    # --- Environment variables (ORION_* only) -------------------------------
    orion_env: dict[str, str] = field(default_factory=dict)

    # --- config/health_patterns.yaml ----------------------------------------
    vague_health_patterns: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, project_root: Path | None = None) -> OrionConfig:
        """Load and validate all 11 configuration sources.

        Args:
            project_root: Repository root directory.  Defaults to three
                levels up from this file (src/shared/config.py → repo root).
        """
        config = cls()
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent
        config.project_root = project_root

        # --- 1. servers.json ------------------------------------------------
        servers, active = cls._load_servers(project_root / "servers.json")
        config.servers = servers
        config.active_server_name = active

        # Extract optional multi-provider fields from raw servers.json.
        raw = cls._load_json(project_root / "servers.json") or {}
        fb = raw.get("fallback_chain")
        config.fallback_chain = (
            [str(n) for n in fb if isinstance(n, str)] if isinstance(fb, list) else []
        )
        cp = raw.get("credential_pool")
        config.credential_pool = (
            {str(k): [str(vv) for vv in v] for k, v in cp.items()}
            if isinstance(cp, dict)
            else {}
        )

        # --- 2. tools.json + 4. secrets overlay ----------------------------
        config.tools = cls._load_tools(
            project_root / "tools.json", project_root / "config" / "secrets.local.json"
        )

        # --- 3. targets.json ------------------------------------------------
        config.targets = cls._load_targets(project_root / "targets.json")

        # --- 4. secrets (standalone) ----------------------------------------
        config.secrets = cls._load_secrets(
            project_root / "config" / "secrets.local.json"
        )

        # --- 5. conversational_patterns.yaml --------------------------------
        (
            config.vi_patterns,
            config.en_patterns,
            config.conv_question_mark,
            config.conv_equivalence_markers,
        ) = cls._load_conversational(project_root)

        # --- 6. capability_plans.yaml ---------------------------------------
        config.capability_plans = cls._load_yaml(
            project_root / "config" / "capability_plans.yaml"
        )

        # --- 7. concepts.yaml -----------------------------------------------
        config.concepts = cls._load_yaml(project_root / "config" / "concepts.yaml")

        # --- 8. target_aliases.yaml -----------------------------------------
        config.target_aliases = cls._load_yaml(
            project_root / "config" / "target_aliases.yaml"
        )

        # --- 9. ORION_* environment variables -------------------------------
        config.orion_env = {
            key: value for key, value in os.environ.items() if key.startswith("ORION_")
        }

        # --- 10. health_patterns.yaml ---------------------------------------
        health = cls._load_yaml(project_root / "config" / "health_patterns.yaml")
        config.vague_health_patterns = health.get("vague_health_patterns", [])

        return config

    @property
    def active_server(self) -> dict[str, Any]:
        """Return the currently active server config dict."""
        return self.servers.get(self.active_server_name, {})

    def env(self, key: str, default: str = "") -> str:
        """Read an ORION_* environment variable.

        Checks the cached ``orion_env`` dict first, then falls back to
        live ``os.environ.get()`` so that runtime changes (e.g. via
        monkeypatch in tests) are reflected.
        """
        return str(self.orion_env.get(key) or os.environ.get(key, default))

    # ------------------------------------------------------------------
    # File loaders (static helpers)
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any] | None:
        """Load a JSON file, returning None if it doesn't exist."""
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        return data

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        """Load a YAML file, returning an empty dict on failure."""
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    @classmethod
    def _load_servers(cls, path: Path) -> tuple[dict[str, Any], str]:
        """Load and validate servers.json."""
        data = cls._load_json(path)
        if data is None:
            return {}, ""
        servers = data.get("servers", {})
        if not isinstance(servers, dict):
            servers = {}
        active = str(data.get("active_server", ""))
        return servers, active

    @classmethod
    def _load_tools(
        cls, tools_path: Path, secrets_path: Path
    ) -> dict[str, dict[str, Any]]:
        """Load tools.json and overlay secrets."""
        data = cls._load_json(tools_path)
        if data is None:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for name, entry in data.items():
            if isinstance(entry, dict):
                result[name] = dict(entry)

        # Overlay secrets
        secrets = cls._load_secrets(secrets_path)
        for tool_name, secret_cfg in secrets.items():
            if tool_name in result:
                result[tool_name].update(secret_cfg)
        return result

    @staticmethod
    def _load_secrets(path: Path) -> dict[str, Any]:
        """Load secrets.local.json if it exists."""
        if not path.exists():
            return {}
        try:
            raw = path.read_text()
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    @classmethod
    def _load_targets(cls, path: Path) -> dict[str, Any]:
        """Load targets.json."""
        data = cls._load_json(path)
        if data is None:
            return {}
        return data

    @classmethod
    def _load_conversational(
        cls, project_root: Path
    ) -> tuple[list[str], list[str], bool, list[str]]:
        """Load conversational patterns from config YAML.

        Respects ORION_CONVERSATIONAL_CONFIG env var override.
        """
        config_path_str = os.environ.get(
            "ORION_CONVERSATIONAL_CONFIG",
            str(project_root / "config" / "conversational_patterns.yaml"),
        )
        config_path = Path(config_path_str)
        if not config_path.exists():
            return [], [], True, [" là ", " is ", "=", "->"]

        try:
            with open(config_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            vi = data.get("vi_patterns", [])
            en = data.get("en_patterns", [])
            qm = data.get("question_mark_ends_conversational", True)
            eq = data.get("equivalence_markers", [" là ", " is ", "=", "->"])
            return vi, en, qm, eq
        except Exception:
            return [], [], True, [" là ", " is ", "=", "->"]


# ---------------------------------------------------------------------------
# Singleton — loaded once at first access
# ---------------------------------------------------------------------------

_config: OrionConfig | None = None


def get_config() -> OrionConfig:
    """Return the global OrionConfig singleton, loading it if necessary."""
    global _config
    if _config is None:
        _config = OrionConfig.load()
    return _config


def _reset_config() -> None:
    """Reset the cached singleton (for tests only)."""
    global _config
    _config = None
