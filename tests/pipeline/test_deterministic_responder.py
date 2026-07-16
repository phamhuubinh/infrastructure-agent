from __future__ import annotations

from src.pipeline.deterministic_responder import DeterministicResponder
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.investigation_request import InvestigationRequest


class TestDeterministicResponder:
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
                data={"total": 5},
            ),
        ]
        result = DeterministicResponder().try_response(inv)
        assert result is not None
        assert "All **5 services** are running normally" in result

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
        assert result is not None
        assert "All **3 services** are running normally" in result

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
        assert result is not None
        assert "All **2 services** are running normally" in result

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
        assert result is not None
        assert "No service status data available" in result

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
