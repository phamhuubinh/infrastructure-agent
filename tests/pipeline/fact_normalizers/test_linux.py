from __future__ import annotations

from src.pipeline.fact import FactValidity
from src.pipeline.fact_normalizers.linux import LinuxFactNormalizer


def _metrics(facts):
    return {fact.metric: fact for fact in facts}


def test_cpu_memory_and_disk_outputs_use_canonical_units() -> None:
    normalizer = LinuxFactNormalizer()
    cpu = normalizer.normalize(
        "get_cpu_usage",
        {
            "usage_percent": 25.0,
            "idle_percent": 70.0,
            "collection_strategy": "fixture",
        },
        target="server-1",
    )
    memory = normalizer.normalize(
        "get_memory",
        {
            "total_bytes": 1000,
            "used_bytes": 250,
            "available_bytes": 750,
            "usage_percent": 25.0,
        },
        target="server-1",
    )
    disk = normalizer.normalize(
        "get_disk",
        {
            "fact_type": "filesystem.capacity",
            "filesystems": [
                {
                    "source": "/dev/sda1",
                    "mountpoint": "/",
                    "size_bytes": 1000,
                    "used_bytes": 370,
                    "available_bytes": 630,
                    "usage_percent": 37.0,
                }
            ],
        },
        target="server-1",
    )

    assert _metrics(cpu)["cpu.usage"].unit == "percent"
    assert _metrics(memory)["memory.total"].unit == "byte"
    assert _metrics(memory)["memory.usage"].value == 25.0
    assert _metrics(disk)["filesystem.usage"].subject == "filesystem:/"


def test_service_inventory_does_not_create_specific_service_status() -> None:
    normalizer = LinuxFactNormalizer()
    inventory = normalizer.normalize(
        "get_services",
        {
            "services": [{"name": "nginx.service", "status": "running"}],
            "total": 1,
            "collection_strategy": "systemd",
            "confidence": 1.0,
        },
    )
    specific = normalizer.normalize(
        "get_service",
        {"name": "nginx", "active": "active"},
    )

    assert {fact.metric for fact in inventory} == {"service.inventory"}
    assert "service.nginx.status" in {fact.metric for fact in specific}
    assert "service.status" in {fact.metric for fact in specific}


def test_network_counters_and_schema_failure_are_explicit() -> None:
    normalizer = LinuxFactNormalizer()
    facts = normalizer.normalize(
        "get_network",
        {
            "interfaces": [
                {
                    "name": "eth0",
                    "family": "link",
                    "address": "00:11:22:33:44:55",
                    "statistics": {"rx_bytes": 10, "tx_bytes": 20},
                }
            ],
            "routes": [],
            "collection_sources": {"interfaces": "proc"},
        },
    )
    invalid = normalizer.normalize(
        "get_cpu_usage",
        {"usage_percent": 0, "collection_strategy": "broken"},
    )

    assert _metrics(facts)["network.rx_bytes"].value == 10
    assert invalid[0].validity is FactValidity.SCHEMA_INVALID
    assert invalid[0].value is None
