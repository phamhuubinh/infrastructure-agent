from __future__ import annotations

from src.pipeline.fact import FactValidity
from src.pipeline.fact_normalizers.grafana import GrafanaFactNormalizer


def test_grafana_cpu_series_matches_linux_unit_and_timestamp() -> None:
    facts = GrafanaFactNormalizer().normalize(
        "query",
        {
            "series": [
                {
                    "name": "CPU usage percent",
                    "unit": "percentunit",
                    "dashboard_uid": "node",
                    "refId": "A",
                    "datapoints": [[0.42, 1785888000000]],
                }
            ]
        },
        target="server-1",
    )

    assert facts[0].metric == "cpu.usage"
    assert facts[0].unit == "percent"
    assert facts[0].value == 42
    assert int(facts[0].observed_at.timestamp()) == 1785888000
    assert facts[0].provenance.source_reference == "/d/node"


def test_dashboard_fact_keeps_uid_provenance() -> None:
    facts = GrafanaFactNormalizer().normalize(
        "dashboards",
        {"dashboards": [{"uid": "abc", "title": "Node", "folder": "Infra"}]},
    )

    assert facts[0].metric == "monitoring.dashboard"
    assert facts[0].dimensions["dashboard_uid"] == "abc"
    assert facts[0].provenance.source_reference == "/d/abc"


def test_non_object_payload_is_schema_invalid() -> None:
    facts = GrafanaFactNormalizer().normalize("query", [])

    assert facts[0].validity is FactValidity.SCHEMA_INVALID
    assert facts[0].value is None
