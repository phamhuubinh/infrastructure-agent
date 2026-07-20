from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent

_linux_outputs: dict[str, str | list[str]] | None = None
_grafana_responses: dict[str, object] | None = None
_zabbix_responses: dict[str, object] | None = None


def _load(name: str) -> dict[str, object]:
    return json.loads((_DATA_DIR / name).read_text())


def get_linux_cmd(key: str) -> str:
    global _linux_outputs
    if _linux_outputs is None:
        _linux_outputs = _load("linux_command_outputs.json")
    val = _linux_outputs[key]
    return val if isinstance(val, str) else str(val)


def get_grafana(key: str) -> object:
    global _grafana_responses
    if _grafana_responses is None:
        _grafana_responses = _load("grafana_responses.json")
    return _grafana_responses[key]


def get_zabbix(key: str) -> object:
    global _zabbix_responses
    if _zabbix_responses is None:
        _zabbix_responses = _load("zabbix_responses.json")
    return _zabbix_responses[key]
