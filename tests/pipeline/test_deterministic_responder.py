from __future__ import annotations

from dataclasses import replace

from src.pipeline.deterministic_responder import DeterministicResponder
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.health_aggregator import HealthAggregator
from src.pipeline.investigation_request import InvestigationRequest
from src.tool.capability_result import CapabilityStatus
from tests.pipeline.reasoning_fact_factory import fact


def _dim(f, **dimensions):
    """Attach dimensions to a Fact built by the reasoning_fact_factory."""
    return replace(f, dimensions=dimensions)


class TestDeterministicResponder:
    def test_health_response_never_hides_active_monitoring_problem(self) -> None:
        inv = InvestigationRequest(raw_request="check server health")
        inv.fact_set = FactSet(
            (
                fact(
                    "monitoring.problem_active",
                    {
                        "active": True,
                        "name": "DHCP link down",
                        "severity": "high",
                    },
                    unit="event",
                ),
                fact("monitoring.host_enabled", True, unit="boolean"),
            )
        )
        inv.health_summary = HealthAggregator().aggregate(inv.fact_set)

        result = DeterministicResponder().try_response(inv)

        assert result is not None
        assert "Critical" in result
        assert "DHCP link down" in result
        assert "Healthy" not in result

    def test_no_evidence_returns_none(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_unsuccessful_evidence_skipped(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=False,
                error="timeout",
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_partial_evidence_is_not_used_for_deterministic_fact(self) -> None:
        inv = InvestigationRequest(raw_request="check zombie process")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                status=CapabilityStatus.PARTIAL,
                data={"zombie_count": 3},
                error="process listing truncated",
            ),
        ]

        result = DeterministicResponder().try_response(inv)

        assert result is None

    def test_zombie_count_from_zombie_key(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": 3},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Zombie Process Detected" in result
        assert "3 zombie processes" in result

    def test_zombie_count_from_zombies_key(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombies": 1},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "is **1 zombie process**" in result

    def test_zombie_count_from_zombie_count_key(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie_count": 5},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "5 zombie processes" in result

    def test_zombie_zero_returns_none(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": 0},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_zombie_negative_returns_none(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": -1},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_zombie_not_int_or_float_returns_none(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": "yes"},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_zombie_with_process_list(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={
                    "zombie": 2,
                    "zombie_processes": ["defunct_1", "defunct_2"],
                },
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "defunct_1, defunct_2" in result

    def test_zombie_with_more_than_five_processes(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={
                    "zombie": 7,
                    "zombie_processes": [f"p{i}" for i in range(7)],
                },
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "p0, p1, p2, p3, p4" in result
        assert "(+2 more)" in result

    def test_service_status_failed(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"failed": ["nginx", "sshd"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Failed Services" in result
        assert "nginx, sshd" in result

    def test_service_status_failed_from_failed_services(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"failed_services": ["apache2"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Failed Services" in result
        assert "apache2" in result

    def test_service_status_failed_more_than_ten(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"failed": [f"svc{i}" for i in range(12)]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "(+2 more)" in result

    def test_service_status_all_running(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"total": 5, "failed": 0},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "No failed services were detected among **5 services**" in result

    def test_service_status_all_running_via_service_count(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"service_count": 3},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_service_status_all_running_via_service_list_length(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"services": ["a", "b"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_service_status_disabled(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"disabled": ["cron", "rsyslog"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Disabled Services" in result
        assert "cron, rsyslog" in result

    def test_service_status_disabled_from_disabled_services(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"disabled_services": ["postfix"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Disabled Services" in result
        assert "postfix" in result

    def test_service_status_disabled_more_than_ten(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"disabled": [f"svc{i}" for i in range(12)]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "(+2 more)" in result

    def test_service_status_no_data_available(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_service_keyword_triggers_vietnamese(self) -> None:
        inv = InvestigationRequest(raw_request="kiểm tra trạng thái dịch vụ")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"failed": ["nginx"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Failed Services" in result

    def test_service_request_without_service_keyword_skipped(self) -> None:
        inv = InvestigationRequest(raw_request="check generic status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"failed": ["nginx"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_non_dict_data_skipped(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data="not a dict",
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_processes_evidence_takes_priority_over_service(self) -> None:
        inv = InvestigationRequest(raw_request="check service status")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": 2},
            ),
            EvidencePackage(
                capability_name="Services",
                evidence_name="Service Status",
                success=True,
                data={"failed": ["nginx"]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Zombie Process Detected" in result

    def test_single_zombie_uses_singular_grammar(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": 1},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "There is **1 zombie process**" in result

    def test_multiple_zombies_uses_plural_grammar(self) -> None:
        inv = InvestigationRequest(raw_request="check system")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": 3},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "There are **3 zombie processes**" in result

    def test_contradictory_facts_block_deterministic_fast_path(self) -> None:
        """DR1-707: a package whose own facts disagree must not answer
        from raw data; it must fall through (return None) so assessment
        sees the contradiction explicitly."""

        inv = InvestigationRequest(raw_request="check zombie process")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": 2},
                facts=(
                    fact(
                        "process.zombie_count",
                        2,
                        validity=FactValidity.CONTRADICTORY,
                        unit="count",
                    ),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None

    def test_stale_facts_block_deterministic_fast_path(self) -> None:
        inv = InvestigationRequest(raw_request="check zombie process")
        inv.evidence = [
            EvidencePackage(
                capability_name="Process",
                evidence_name="Processes",
                success=True,
                data={"zombie": 2},
                facts=(
                    fact(
                        "process.zombie_count",
                        2,
                        validity=FactValidity.STALE,
                        freshness=FactFreshness.STALE,
                        unit="count",
                    ),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None


class TestDeterministicResponderReadsCanonicalFacts:
    """DR1-707: responders prefer canonical Facts over raw pkg.data when
    the normalizer produced them, with the legacy dict-key lookup kept
    only as a fallback for packages with no Fact coverage."""

    def test_hostname_from_fact(self) -> None:
        inv = InvestigationRequest(raw_request="hostname là gì")
        inv.evidence = [
            EvidencePackage(
                capability_name="System Information",
                evidence_name="System Information",
                success=True,
                data={},
                facts=(fact("system.hostname", "orion-db-01", unit="text"),),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "orion-db-01" in result

    def test_kernel_from_fact(self) -> None:
        inv = InvestigationRequest(raw_request="phiên bản kernel")
        inv.evidence = [
            EvidencePackage(
                capability_name="System Information",
                evidence_name="System Information",
                success=True,
                data={},
                facts=(fact("system.kernel", "6.8.0-generic", unit="text"),),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "6.8.0-generic" in result

    def test_ram_available_from_fact_uses_bytes_not_kb(self) -> None:
        # Real get_memory payloads use available_bytes/total_bytes (see
        # output_schema.py); the legacy dict lookup for
        # available_kb/total_kb never matched them. This is the bug the
        # Fact-based read fixes.
        inv = InvestigationRequest(raw_request="ram còn trống bao nhiêu")
        inv.evidence = [
            EvidencePackage(
                capability_name="Memory Information",
                evidence_name="Memory Information",
                success=True,
                data={"available_bytes": 4 * 1024**3, "total_bytes": 16 * 1024**3},
                facts=(
                    fact("memory.available", 4 * 1024**3, unit="byte"),
                    fact("memory.total", 16 * 1024**3, unit="byte"),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "4.0 GB" in result
        assert "16.0 GB" in result
        assert "25.0% free" in result

    def test_ram_available_falls_back_to_dict_when_no_facts(self) -> None:
        inv = InvestigationRequest(raw_request="ram còn trống bao nhiêu")
        inv.evidence = [
            EvidencePackage(
                capability_name="Memory Information",
                evidence_name="Memory Information",
                success=True,
                data={"available_kb": 2097152, "total_kb": 8388608},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "2.0 GB" in result

    def test_load_average_from_facts(self) -> None:
        inv = InvestigationRequest(raw_request="tải trung bình hệ thống")
        inv.evidence = [
            EvidencePackage(
                capability_name="CPU Information",
                evidence_name="CPU Information",
                success=True,
                data={},
                facts=(
                    fact("system.load_1m", 0.5, unit="load"),
                    fact("system.load_5m", 0.8, unit="load"),
                    fact("system.load_15m", 1.1, unit="load"),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "0.5" in result and "0.8" in result and "1.1" in result

    def test_swap_from_fact_uses_bytes_not_kb(self) -> None:
        # Real get_swap/get_memory payloads use *_bytes fields; the legacy
        # dict lookup for swap_total/swap_total_kb never matched them.
        inv = InvestigationRequest(raw_request="tình trạng swap")
        inv.evidence = [
            EvidencePackage(
                capability_name="Memory Information",
                evidence_name="Memory Information",
                success=True,
                data={"swap_total_bytes": 2 * 1024**3, "swap_used_bytes": 1024**3},
                facts=(
                    fact("swap.total", 2 * 1024**3, unit="byte"),
                    fact("swap.used", 1024**3, unit="byte"),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "2.0 GB" in result
        assert "1.0 GB" in result
        assert "50.0%" in result

    def test_listening_ports_from_facts(self) -> None:
        inv = InvestigationRequest(raw_request="cổng nào đang listen")
        inv.evidence = [
            EvidencePackage(
                capability_name="Network Information",
                evidence_name="Network Information",
                success=True,
                data={},
                facts=(
                    fact(
                        "network.listening_socket",
                        {"port_number": 443, "protocol": "tcp", "process": "nginx"},
                        unit="record",
                    ),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "443" in result
        assert "nginx" in result

    def test_disk_usage_from_facts_grouped_by_mountpoint(self) -> None:
        inv = InvestigationRequest(raw_request="ổ đĩa còn trống bao nhiêu")
        inv.evidence = [
            EvidencePackage(
                capability_name="Storage Information",
                evidence_name="Storage",
                success=True,
                data={},
                facts=(
                    _dim(
                        fact("filesystem.usage", 92.5, unit="percent"),
                        mountpoint="/",
                    ),
                    _dim(
                        fact("filesystem.usage", 40.0, unit="percent"),
                        mountpoint="/data",
                    ),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "92.5%" in result
        assert "Near capacity" in result
        assert "/" in result

    def test_service_status_for_named_service_from_facts(self) -> None:
        inv = InvestigationRequest(raw_request="trạng thái service nginx")
        inv.extracted_params = type(
            "Params", (), {"service_name": "nginx"}
        )()
        inv.evidence = [
            EvidencePackage(
                capability_name="Service Status",
                evidence_name="Service Status",
                success=True,
                data={},
                facts=(
                    _dim(
                        fact("service.status", "active", unit="state"),
                        service_name="nginx",
                    ),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "active" in result
        assert "nginx" in result

    def test_untrustworthy_package_facts_still_block_new_fact_reads(self) -> None:
        # The DR1-707 package-level guard must still apply even though
        # these responders now read facts directly.
        inv = InvestigationRequest(raw_request="hostname là gì")
        inv.evidence = [
            EvidencePackage(
                capability_name="System Information",
                evidence_name="System Information",
                success=True,
                data={"hostname": "stale-host"},
                facts=(
                    fact(
                        "system.hostname",
                        "stale-host",
                        validity=FactValidity.STALE,
                        freshness=FactFreshness.STALE,
                        unit="text",
                    ),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is None


class TestDeterministicResponderMatchesRealEvidenceNames:
    """DR1-707 follow-up: some evidence_name values that
    src/pipeline/capability_library.py treats as their own distinct
    EvidenceRequirement (e.g. "Swap" is separate from "Memory") were never
    matched by the responder's evidence_name checks, so those packages
    silently fell through to the LLM path even with perfectly good facts.
    """

    def test_swap_evidence_name_matches_dedicated_swap_requirement(self) -> None:
        inv = InvestigationRequest(raw_request="tình trạng swap")
        inv.evidence = [
            EvidencePackage(
                capability_name="Swap Information",
                evidence_name="Swap",  # distinct from "Memory" per capability_library.py
                success=True,
                data={},
                facts=(
                    fact("swap.total", 2 * 1024**3, unit="byte"),
                    fact("swap.used", 1024**3, unit="byte"),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "## Swap" in result

    def test_load_average_evidence_name_matches_dedicated_requirement(self) -> None:
        inv = InvestigationRequest(raw_request="tải trung bình hệ thống")
        inv.evidence = [
            EvidencePackage(
                capability_name="System Load Assessment",
                evidence_name="Load Average",  # distinct from "CPU"
                success=True,
                data={},
                facts=(
                    fact("system.load_1m", 0.5, unit="load"),
                    fact("system.load_5m", 0.8, unit="load"),
                    fact("system.load_15m", 1.1, unit="load"),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "Load Average" in result

    def test_listening_ports_evidence_name_matches_dedicated_requirement(self) -> None:
        inv = InvestigationRequest(raw_request="cổng nào đang listen")
        inv.evidence = [
            EvidencePackage(
                capability_name="Port Discovery",
                evidence_name="Listening Ports",  # distinct from "Network"
                success=True,
                data={"ports": [{"port_number": 22, "protocol": "tcp"}]},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "22" in result

    def test_system_uptime_evidence_name_matches_dedicated_requirement(self) -> None:
        inv = InvestigationRequest(raw_request="uptime bao lâu rồi")
        inv.evidence = [
            EvidencePackage(
                capability_name="System Uptime",
                evidence_name="System Uptime",  # distinct from CPU/System Information
                success=True,
                data={"uptime_seconds": 90000},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "## Uptime" in result

    def test_disk_usage_evidence_name_matches_dedicated_requirement(self) -> None:
        inv = InvestigationRequest(raw_request="ổ đĩa còn trống bao nhiêu")
        inv.evidence = [
            EvidencePackage(
                capability_name="Disk Utilization",
                evidence_name="Disk Usage",  # from STORAGE_ASSESSMENT/PERFORMANCE_ASSESSMENT
                success=True,
                data={},
                facts=(
                    replace(
                        fact("filesystem.usage", 95.0, unit="percent"),
                        dimensions={"mountpoint": "/var"},
                    ),
                ),
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "95.0%" in result
