"""DR1-804 — raw-payload contracts shared by every fact normalizer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.fact import FactValidity
from src.pipeline.fact_normalizers.grafana import GrafanaFactNormalizer
from src.pipeline.fact_normalizers.linux import LinuxFactNormalizer
from src.pipeline.fact_normalizers.zabbix import ZabbixFactNormalizer

FIXTURES = Path(__file__).parents[2] / "data" / "fact_normalization"


@pytest.mark.parametrize(
    ("fixture_name", "normalizer", "metric", "unit", "value"),
    [
        (
            "linux_payload.json",
            LinuxFactNormalizer(),
            "filesystem.usage",
            "percent",
            37.0,
        ),
        ("grafana_payload.json", GrafanaFactNormalizer(), "cpu.usage", "percent", 42),
        ("zabbix_payload.json", ZabbixFactNormalizer(), "cpu.usage", "percent", 15.5),
    ],
)
def test_raw_payload_contract_preserves_metric_unit_timestamp_and_provenance(
    fixture_name: str,
    normalizer: object,
    metric: str,
    unit: str,
    value: object,
) -> None:
    raw = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    facts = normalizer.normalize(  # type: ignore[attr-defined]
        raw["capability"],
        raw["payload"],
        target=raw["target"],
        collected_at=raw["collected_at"],
    )
    fact = next(item for item in facts if item.metric == metric)

    assert fact.value == value
    assert fact.unit == unit
    assert fact.target == "server-1"
    assert fact.observed_at.tzinfo is not None
    assert fact.provenance.target == "server-1"
    assert fact.provenance.capability == raw["capability"]


@pytest.mark.parametrize(
    "normalizer",
    [LinuxFactNormalizer(), GrafanaFactNormalizer(), ZabbixFactNormalizer()],
)
def test_malformed_payload_is_a_schema_invalid_fact_not_a_zero(
    normalizer: object,
) -> None:
    facts = normalizer.normalize("get_items", ["malformed"])  # type: ignore[attr-defined]

    assert facts[0].validity is FactValidity.SCHEMA_INVALID
    assert facts[0].value is None
