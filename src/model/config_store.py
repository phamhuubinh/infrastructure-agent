"""Persistent configuration for user-managed model connections."""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.parse
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.model.llm_client import LLMClient
from src.shared.config_schema import ServerConfig, ServersConfig

_lock = threading.RLock()


def model_config_path() -> Path:
    configured = os.environ.get("ORION_SERVERS_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent.parent / "servers.json"


class ModelConfigStore:
    """Manage the same model registry consumed by the Chat runtime."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else model_config_path()

    def ensure_exists(self) -> None:
        with _lock:
            if not self.path.exists():
                self._save({"active_server": "", "servers": {}, "fallback_chain": []})

    def list_public(self) -> dict[str, Any]:
        data = self._load()
        models = []
        for name, raw in data["servers"].items():
            models.append(
                {
                    "name": name,
                    "provider": raw.get("provider", "openai"),
                    "base_url": raw["base_url"],
                    "model": raw.get("model", "gpt-4"),
                    "timeout": raw.get("timeout", 60),
                    "temperature": raw.get("temperature", 0.0),
                    "max_tokens": raw.get("max_tokens", 2048),
                    "api_key_configured": bool(
                        str(raw.get("api_key") or "").strip()
                        and str(raw.get("api_key")).upper() != "EMPTY"
                    ),
                    "available": True,
                    "active": name == data["active_server"],
                }
            )
        return {"active_server": data["active_server"], "models": models}

    def get(self, name: str) -> dict[str, Any] | None:
        data = self._load()
        value = data["servers"].get(name)
        return deepcopy(value) if isinstance(value, dict) else None

    def active(self) -> tuple[str, dict[str, Any]] | None:
        data = self._load()
        name = data["active_server"]
        value = data["servers"].get(name)
        if not name or not isinstance(value, dict):
            return None
        return name, deepcopy(value)

    def upsert(
        self,
        name: str,
        config: dict[str, Any],
        *,
        activate: bool = True,
    ) -> dict[str, Any]:
        normalized_name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", normalized_name):
            raise ValueError(
                "Model connection name must use 1-80 letters, numbers, dots, "
                "underscores, or hyphens"
            )

        base_url = str(config.get("base_url", "")).strip().rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3].rstrip("/")
        model = str(config.get("model", "")).strip()
        provider = str(config.get("provider", "openai")).strip().lower()
        if not base_url or not model:
            raise ValueError("base_url and model are required")
        parsed_url = urllib.parse.urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("base_url must be an absolute http:// or https:// URL")
        if parsed_url.username or parsed_url.password:
            raise ValueError(
                "base_url must not contain credentials; use api_key instead"
            )
        if parsed_url.query or parsed_url.fragment:
            raise ValueError("base_url must not contain a query string or fragment")
        host_alias = os.environ.get("ORION_MODEL_HOST_ALIAS", "").strip()
        if host_alias and parsed_url.hostname in {"localhost", "127.0.0.1", "::1"}:
            port = f":{parsed_url.port}" if parsed_url.port is not None else ""
            parsed_url = parsed_url._replace(netloc=f"{host_alias}{port}")
            base_url = urllib.parse.urlunsplit(parsed_url)
        if provider not in {"openai", "ollama", "vllm", "anthropic"}:
            raise ValueError("provider must be openai, ollama, vllm, or anthropic")
        config = {**config, "base_url": base_url, "model": model, "provider": provider}

        validated = ServerConfig.model_validate(config).model_dump(exclude_none=True)
        with _lock:
            data = self._load_unlocked()
            data["servers"][normalized_name] = validated
            if activate or not data["active_server"]:
                data["active_server"] = normalized_name
            fallback = [
                item
                for item in data.get("fallback_chain", [])
                if item in data["servers"] and item != normalized_name
            ]
            data["fallback_chain"] = [normalized_name, *fallback]
            self._save(data)
        return self.list_public()

    def set_active(self, name: str) -> dict[str, Any]:
        with _lock:
            data = self._load_unlocked()
            if name not in data["servers"]:
                raise KeyError(name)
            data["active_server"] = name
            fallback = [item for item in data.get("fallback_chain", []) if item != name]
            data["fallback_chain"] = [name, *fallback]
            self._save(data)
        return self.list_public()

    def delete(self, name: str) -> bool:
        with _lock:
            data = self._load_unlocked()
            if data["servers"].pop(name, None) is None:
                return False
            data["fallback_chain"] = [
                item for item in data.get("fallback_chain", []) if item != name
            ]
            if data["active_server"] == name:
                data["active_server"] = next(iter(data["servers"]), "")
            self._save(data)
        return True

    def test(self, name: str, timeout: int = 30) -> dict[str, Any]:
        config = self.get(name)
        if config is None:
            raise KeyError(name)
        client = LLMClient(
            base_url=str(config["base_url"]),
            model=str(config.get("model", "gpt-4")),
            api_key=_normalized_key(config.get("api_key")),
            timeout=min(max(timeout, 1), 300),
            temperature=float(config.get("temperature", 0.0)),
            max_tokens=int(config.get("max_tokens", 2048)),
        )
        try:
            available = client.health_check(timeout=min(max(timeout, 1), 300))
            result = {"status": "ok" if available else "error", "name": name}
            if not available:
                result["error"] = "Model health check returned false"
            return result
        except Exception as exc:
            return {"status": "error", "name": name, "error": str(exc)[:500]}

    def _load(self) -> dict[str, Any]:
        with _lock:
            return deepcopy(self._load_unlocked())

    def _load_unlocked(self) -> dict[str, Any]:
        self.ensure_exists()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            validated = ServersConfig.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid model configuration: {exc}") from exc
        data = raw if isinstance(raw, dict) else {}
        data["active_server"] = validated.active_server
        data["servers"] = {
            key: value.model_dump(exclude_none=True)
            for key, value in validated.servers.items()
        }
        data.setdefault("fallback_chain", [])
        data.setdefault("credential_pool", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ServersConfig.model_validate(data)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        temp.replace(self.path)


def _normalized_key(value: object) -> str | None:
    normalized = str(value or "").strip()
    return None if not normalized or normalized.upper() == "EMPTY" else normalized
