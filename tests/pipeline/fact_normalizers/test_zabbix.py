from __future__ import annotations

from src.pipeline.fact import FactValidity
from src.pipeline.fact_normalizers.zabbix import ZabbixFactNormalizer


def test_zabbix_cpu_item_maps_to_same_canonical_metric_and_time() -> None:
    facts = ZabbixFactNormalizer().normalize(
        "get_items",
        {
            "items": [
                {
                    "itemid": "10",
                    "name": "CPU utilization",
                    "key_": "system.cpu.util",
                    "lastvalue": "15.5",
                    "units": "%",
                    "lastclock": "1785888000",
                }
            ]
        },
        target="server-1",
    )

    assert facts[0].metric == "cpu.usage"
    assert facts[0].unit == "percent"
    assert facts[0].value == 15.5
    assert int(facts[0].observed_at.timestamp()) == 1785888000
    assert "itemids" in (facts[0].provenance.source_reference or "")


def test_active_problem_keeps_severity_event_id_and_observed_time() -> None:
    facts = ZabbixFactNormalizer().normalize(
        "get_problems",
        {
            "problems": [
                {
                    "eventid": "99",
                    "name": "CPU overload",
                    "clock": "1785888000",
                    "severity": "4",
                    "severity_label": "high",
                }
            ]
        },
    )

    value = facts[0].to_dict()["value"]
    assert facts[0].metric == "monitoring.problem_active"
    assert value["severity"] == "high"
    assert facts[0].dimensions["event_id"] == "99"
    assert int(facts[0].observed_at.timestamp()) == 1785888000


def test_host_status_zero_means_enabled_not_healthy() -> None:
    facts = ZabbixFactNormalizer().normalize(
        "get_hosts",
        {"hosts": [{"hostid": "1", "host": "srv", "status": "0"}]},
    )

    assert facts[0].metric == "monitoring.host_enabled"
    assert facts[0].value is True
    assert all("health" not in fact.metric for fact in facts)


def test_non_object_payload_is_schema_invalid() -> None:
    facts = ZabbixFactNormalizer().normalize("get_items", [])

    assert facts[0].validity is FactValidity.SCHEMA_INVALID
    assert facts[0].value is None
