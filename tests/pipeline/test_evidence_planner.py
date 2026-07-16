from __future__ import annotations

import pytest

from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest


@pytest.fixture
def planner() -> EvidencePlanner:
    return EvidencePlanner()


def _request(intent: Intent) -> InvestigationRequest:
    return InvestigationRequest(raw_request="test", intent=intent)


def _names(items: list[EvidenceRequirement]) -> list[str]:
    return [e.name for e in items]


# ---------------------------------------------------------------------------
# Machine Assessment — 06_EVIDENCE_TEMPLATES.md
# ---------------------------------------------------------------------------


class TestMachineAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.MACHINE_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "System Information",
            "CPU",
            "Memory",
            "Swap",
            "Storage",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.MACHINE_ASSESSMENT)
        planner.plan(req)
        names = _names(req.optional_evidence)
        assert "Filesystem" in names
        assert "Network" in names
        assert "Services" in names
        assert "Processes" in names
        assert "Time Synchronization" in names
        assert "Recent Logs" in names
        assert "Docker" in names
        assert "Block Device Information" in names
        assert "GPU Information" in names

    def test_all_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.MACHINE_ASSESSMENT)
        planner.plan(req)
        for ev in req.required_evidence:
            assert ev.required is True

    def test_all_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.MACHINE_ASSESSMENT)
        planner.plan(req)
        for ev in req.optional_evidence:
            assert ev.required is False


# ---------------------------------------------------------------------------
# Application Discovery
# ---------------------------------------------------------------------------


class TestApplicationDiscovery:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.APPLICATION_DISCOVERY)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "Installed Packages",
            "System Services",
            "Running Processes",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.APPLICATION_DISCOVERY)
        planner.plan(req)
        assert _names(req.optional_evidence) == [
            "Listening Ports",
            "Configuration Files",
            "Containers",
        ]


# ---------------------------------------------------------------------------
# Service Assessment
# ---------------------------------------------------------------------------


class TestServiceAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.SERVICE_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "Service Status",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.SERVICE_ASSESSMENT)
        planner.plan(req)
        assert _names(req.optional_evidence) == [
            "Service Configuration",
            "Service Logs",
            "Running Processes",
            "Listening Ports",
        ]


# ---------------------------------------------------------------------------
# Monitoring Assessment
# ---------------------------------------------------------------------------


class TestMonitoringAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.MONITORING_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "Active Problems",
            "Triggers",
            "Alert Severity",
            "Host Status",
            "Host Groups",
            "Templates",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.MONITORING_ASSESSMENT)
        planner.plan(req)
        assert _names(req.optional_evidence) == [
            "Dashboards",
            "Dashboard Folders",
            "Data Sources",
            "Alert Rules",
            "Event History",
            "Users",
            "Maintenance Status",
        ]


# ---------------------------------------------------------------------------
# Security Assessment
# ---------------------------------------------------------------------------


class TestSecurityAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.SECURITY_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "SSH Configuration",
            "Firewall",
            "Secure Boot",
            "AppArmor",
            "SELinux",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.SECURITY_ASSESSMENT)
        planner.plan(req)
        names = _names(req.optional_evidence)
        assert "Recent Logins" in names
        assert "Listening Ports" in names
        assert "Certificates" in names


# ---------------------------------------------------------------------------
# Performance Assessment
# ---------------------------------------------------------------------------


class TestPerformanceAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.PERFORMANCE_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "CPU Usage",
            "Memory Usage",
            "Disk Usage",
            "Load Average",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.PERFORMANCE_ASSESSMENT)
        planner.plan(req)
        assert _names(req.optional_evidence) == [
            "Processes",
            "I/O Statistics",
            "Network Usage",
        ]


# ---------------------------------------------------------------------------
# Storage Assessment
# ---------------------------------------------------------------------------


class TestStorageAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.STORAGE_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "Filesystems",
            "Disk Usage",
            "Mount Points",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.STORAGE_ASSESSMENT)
        planner.plan(req)
        assert _names(req.optional_evidence) == [
            "SMART Status",
            "RAID Status",
            "Storage Performance",
            "Block Device Information",
        ]


# ---------------------------------------------------------------------------
# Network Assessment
# ---------------------------------------------------------------------------


class TestNetworkAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.NETWORK_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "Network",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.NETWORK_ASSESSMENT)
        planner.plan(req)
        assert _names(req.optional_evidence) == [
            "DNS",
            "Listening Ports",
            "Firewall",
        ]


# ---------------------------------------------------------------------------
# Configuration Assessment
# ---------------------------------------------------------------------------


class TestConfigurationAssessment:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.CONFIGURATION_ASSESSMENT)
        planner.plan(req)
        assert _names(req.required_evidence) == [
            "Configuration Files",
            "Installed Packages",
            "Services",
        ]

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.CONFIGURATION_ASSESSMENT)
        planner.plan(req)
        assert _names(req.optional_evidence) == [
            "Running Processes",
            "Environment Variables",
        ]


# ---------------------------------------------------------------------------
# Troubleshooting
# ---------------------------------------------------------------------------


class TestTroubleshooting:
    def test_required(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.TROUBLESHOOTING)
        planner.plan(req)
        assert len(req.required_evidence) == 3
        names = [e.name for e in req.required_evidence]
        assert "System Information" in names
        assert "Services" in names
        assert "Recent Logs" in names

    def test_optional(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.TROUBLESHOOTING)
        planner.plan(req)
        assert len(req.optional_evidence) == 4
        names = [e.name for e in req.optional_evidence]
        assert "CPU" in names
        assert "Memory" in names
        assert "Disk Usage" in names


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_intent(self, planner: EvidencePlanner) -> None:
        req = InvestigationRequest(raw_request="test")
        planner.plan(req)
        assert req.required_evidence == []
        assert req.optional_evidence == []

    def test_plan_is_idempotent(self, planner: EvidencePlanner) -> None:
        req = _request(Intent.MACHINE_ASSESSMENT)
        planner.plan(req)
        first_required = list(req.required_evidence)
        first_optional = list(req.optional_evidence)
        planner.plan(req)
        assert req.required_evidence == first_required
        assert req.optional_evidence == first_optional

    def test_plan_does_not_modify_other_fields(self, planner: EvidencePlanner) -> None:
        req = InvestigationRequest(
            raw_request="check server",
            intent=Intent.MACHINE_ASSESSMENT,
            target="prod-web",
            matched_keywords=("server",),
        )
        planner.plan(req)
        assert req.raw_request == "check server"
        assert req.target == "prod-web"
        assert req.matched_keywords == ("server",)


# ---------------------------------------------------------------------------
# EvidenceRequirement properties
# ---------------------------------------------------------------------------


class TestEvidenceRequirement:
    def test_required_flag(self) -> None:
        req = EvidenceRequirement(name="CPU", required=True)
        assert req.name == "CPU"
        assert req.required is True
        assert req.category == ""

    def test_optional_flag(self) -> None:
        req = EvidenceRequirement(name="Processes", required=False)
        assert req.name == "Processes"
        assert req.required is False

    def test_with_category(self) -> None:
        req = EvidenceRequirement(name="CPU", required=True, category="hardware")
        assert req.category == "hardware"

    def test_immutable(self) -> None:
        req = EvidenceRequirement(name="CPU", required=True)
        with pytest.raises(AttributeError):
            req.name = "Memory"  # type: ignore[misc]

    def test_repr(self) -> None:
        req = EvidenceRequirement(name="CPU", required=True, category="hardware")
        expected = (
            "EvidenceRequirement(name='CPU', required=True, category='hardware')"
        )
        assert repr(req) == expected
