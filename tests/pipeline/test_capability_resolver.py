from __future__ import annotations

import pytest

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.capability_library import CAPABILITY_BY_EVIDENCE
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest


@pytest.fixture
def resolver() -> CapabilityResolver:
    return CapabilityResolver()


def _with_evidence(
    required: list[str],
    optional: list[str] | None = None,
) -> InvestigationRequest:
    req = InvestigationRequest(raw_request="test", intent=Intent.MACHINE_ASSESSMENT)
    req.required_evidence = [EvidenceRequirement(name=n) for n in required]
    if optional:
        req.optional_evidence = [EvidenceRequirement(name=n, required=False) for n in optional]
    return req


def _names(refs: list[CapabilityReference]) -> list[str]:
    return [r.name for r in refs]


def _evidence_names(refs: list[CapabilityReference]) -> list[str]:
    return [r.evidence_name for r in refs]


# ---------------------------------------------------------------------------
# Machine Assessment evidence → capability mapping
# ---------------------------------------------------------------------------


class TestMachineAssessmentCapabilities:
    def test_required(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence([
            "System Information", "CPU", "Memory", "Swap",
            "Storage", "Filesystem", "Network", "Services",
        ])
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "System Information",
            "CPU Information",
            "Memory Information",
            "Swap Information",
            "Storage Information",
            "Filesystem Information",
            "Network Information",
            "Service Status",
        ]

    def test_optional(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence([], [
            "Processes", "Time Synchronization", "Recent Logs",
            "Docker", "Security Status",
        ])
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Process Discovery",
            "Time Synchronization",
            "Log Discovery",
            "Container Discovery",
            "Security Posture Summary",
        ]


# ---------------------------------------------------------------------------
# Application Discovery
# ---------------------------------------------------------------------------


class TestApplicationDiscoveryCapabilities:
    def test_all(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(
            ["Installed Packages", "System Services", "Running Processes"],
            ["Listening Ports", "Configuration Files", "Containers"],
        )
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Package Discovery",
            "Service Discovery",
            "Process Discovery",
            "Port Discovery",
            "Configuration Inspection",
            "Container Discovery",
        ]


# ---------------------------------------------------------------------------
# Monitoring Assessment
# ---------------------------------------------------------------------------


class TestMonitoringAssessmentCapabilities:
    def test_required(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence([
            "Active Problems", "Triggers", "Alert Severity", "Host Status",
        ])
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Monitoring Problems",
            "Alert Triggers",
            "Alert Severity Assessment",
            "Host Status Assessment",
        ]

    def test_optional(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence([], [
            "Dashboards", "Data Sources", "Event History",
        ])
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Dashboard Discovery",
            "Data Source Discovery",
            "Event History Discovery",
        ]


# ---------------------------------------------------------------------------
# Security Assessment
# ---------------------------------------------------------------------------


class TestSecurityAssessmentCapabilities:
    def test_required(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence([
            "SSH Configuration", "Firewall", "Secure Boot",
            "AppArmor", "SELinux",
        ])
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "SSH Configuration Inspection",
            "Firewall Inspection",
            "Secure Boot Status",
            "AppArmor Status",
            "SELinux Status",
        ]


# ---------------------------------------------------------------------------
# Performance Assessment
# ---------------------------------------------------------------------------


class TestPerformanceAssessmentCapabilities:
    def test_all(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(
            ["CPU Usage", "Memory Usage", "Disk Usage", "Load Average"],
            ["Processes", "I/O Statistics", "Network Usage"],
        )
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "CPU Utilization",
            "Memory Utilization",
            "Disk Utilization",
            "System Load Assessment",
            "Process Discovery",
            "I/O Performance Assessment",
            "Network Utilization",
        ]


# ---------------------------------------------------------------------------
# Storage Assessment
# ---------------------------------------------------------------------------


class TestStorageAssessmentCapabilities:
    def test_all(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(
            ["Filesystems", "Disk Usage", "Mount Points"],
            ["SMART Status", "RAID Status", "Storage Performance"],
        )
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Filesystem Discovery",
            "Disk Utilization",
            "Mount Point Discovery",
            "SMART Health Assessment",
            "RAID Health Assessment",
            "Storage Performance Assessment",
        ]


# ---------------------------------------------------------------------------
# Network Assessment
# ---------------------------------------------------------------------------


class TestNetworkAssessmentCapabilities:
    def test_all(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(
            ["Network Interfaces", "IP Configuration", "Default Gateway"],
            ["DNS", "Routing", "Listening Ports", "Firewall"],
        )
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Network Interface Discovery",
            "IP Configuration Assessment",
            "Default Gateway Discovery",
            "DNS Configuration Assessment",
            "Routing Table Assessment",
            "Port Discovery",
            "Firewall Inspection",
        ]


# ---------------------------------------------------------------------------
# Configuration Assessment
# ---------------------------------------------------------------------------


class TestConfigurationAssessmentCapabilities:
    def test_all(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(
            ["Configuration Files", "Installed Packages", "Services"],
            ["Running Processes", "Environment Variables"],
        )
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Configuration Inspection",
            "Package Discovery",
            "Service Status",
            "Process Discovery",
            "Environment Variable Discovery",
        ]


# ---------------------------------------------------------------------------
# Service Assessment
# ---------------------------------------------------------------------------


class TestServiceAssessmentCapabilities:
    def test_all(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(
            ["Service Status", "Service Configuration", "Service Logs"],
            ["Running Processes", "Listening Ports", "Dependencies"],
        )
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "Service Status",
            "Service Configuration Inspection",
            "Service Log Discovery",
            "Process Discovery",
            "Port Discovery",
            "Dependency Discovery",
        ]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_evidence(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence([])
        resolver.resolve(req)
        assert req.capability_references == []

    def test_no_intent_with_empty_evidence(self, resolver: CapabilityResolver) -> None:
        req = InvestigationRequest(raw_request="test")
        resolver.resolve(req)
        assert req.capability_references == []

    def test_unknown_evidence_is_skipped(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(["CPU", "UnknownEvidence", "Services"])
        resolver.resolve(req)
        assert _names(req.capability_references) == [
            "CPU Information",
            "Service Status",
        ]
        assert "UnknownEvidence" not in _evidence_names(req.capability_references)

    def test_duplicate_evidence_is_deduplicated(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(["CPU", "CPU", "CPU"])
        resolver.resolve(req)
        assert _names(req.capability_references) == ["CPU Information"]
        assert len(req.capability_references) == 1

    def test_same_capability_from_different_evidence_deduplicated(
        self, resolver: CapabilityResolver
    ) -> None:
        # Both "Services" and "Service Status" map to "Service Status"
        req = _with_evidence(["Services", "Service Status"])
        resolver.resolve(req)
        assert _names(req.capability_references) == ["Service Status"]
        assert len(req.capability_references) == 1

    def test_configuration_files_mapped_once(
        self, resolver: CapabilityResolver
    ) -> None:
        req = _with_evidence(["Configuration Files", "Configuration Files"])
        resolver.resolve(req)
        assert _names(req.capability_references) == ["Configuration Inspection"]
        assert len(req.capability_references) == 1

    def test_resolve_is_idempotent(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(["CPU", "Memory"])
        resolver.resolve(req)
        first = list(req.capability_references)
        resolver.resolve(req)
        assert req.capability_references == first

    def test_evidence_name_preserved(self, resolver: CapabilityResolver) -> None:
        req = _with_evidence(["CPU"])
        resolver.resolve(req)
        assert len(req.capability_references) == 1
        assert req.capability_references[0].evidence_name == "CPU"
        assert req.capability_references[0].name == "CPU Information"


# ---------------------------------------------------------------------------
# CapabilityReference properties
# ---------------------------------------------------------------------------


class TestCapabilityReference:
    def test_immutable(self) -> None:
        ref = CapabilityReference(name="CPU Information", evidence_name="CPU")
        with pytest.raises(AttributeError):
            ref.name = "Memory Information"  # type: ignore[misc]

    def test_repr(self) -> None:
        ref = CapabilityReference(
            name="CPU Information",
            evidence_name="CPU",
            description="CPU information capability",
        )
        assert repr(ref) == (
            "CapabilityReference(name='CPU Information', "
            "evidence_name='CPU', description='CPU information capability')"
        )

    def test_minimal(self) -> None:
        ref = CapabilityReference(name="CPU Information", evidence_name="CPU")
        assert ref.description == ""


# ---------------------------------------------------------------------------
# Library coverage — every evidence template item has a mapping
# ---------------------------------------------------------------------------


class TestLibraryCoverage:
    """Every evidence name used in EvidencePlanner templates must have a
    corresponding entry in the capability library."""

    _ALL_EVIDENCE_NAMES = {
        "System Information", "CPU", "Memory", "Swap",
        "Storage", "Filesystem", "Network", "Services",
        "Processes", "Time Synchronization", "Recent Logs",
        "Docker", "Security Status",
        "Installed Packages", "System Services", "Running Processes",
        "Listening Ports", "Configuration Files", "Containers",
        "Service Status", "Service Configuration", "Service Logs",
        "Dependencies",
        "Active Problems", "Triggers", "Alert Severity", "Host Status",
        "Dashboards", "Data Sources", "Event History",
        "SSH Configuration", "Firewall", "Secure Boot",
        "AppArmor", "SELinux", "Recent Logins", "Certificates",
        "CPU Usage", "Memory Usage", "Disk Usage", "Load Average",
        "I/O Statistics", "Network Usage",
        "Filesystems", "Disk Usage", "Mount Points",
        "SMART Status", "RAID Status", "Storage Performance",
        "Network Interfaces", "IP Configuration", "Default Gateway",
        "DNS", "Routing",
        "Environment Variables",
    }

    def test_all_evidence_names_have_mappings(self) -> None:
        missing = self._ALL_EVIDENCE_NAMES - set(CAPABILITY_BY_EVIDENCE)
        assert not missing, f"Missing capability mappings for: {missing}"

    def test_no_unused_mappings(self) -> None:
        extra = set(CAPABILITY_BY_EVIDENCE) - self._ALL_EVIDENCE_NAMES
        assert not extra, f"Unused capability mappings for: {extra}"
