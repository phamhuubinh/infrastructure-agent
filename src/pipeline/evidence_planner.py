from __future__ import annotations

from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest

# ---------------------------------------------------------------------------
# Evidence templates — source of truth: docs/ai/06_EVIDENCE_TEMPLATES.md
# ---------------------------------------------------------------------------
# Each template is defined as (required_names, optional_names) matching the
# document's Required Evidence and Optional Evidence sections exactly.
#
# Optimization rules:
# 1. No two evidence items may call the same tool capability.
# 2. Each evidence item must serve a distinct purpose.
# 3. Optional evidence must provide meaningful additional value.

_TEMPLATES: dict[Intent, tuple[tuple[str, ...], tuple[str, ...]]] = {
    Intent.CPU_ASSESSMENT: (
        ("CPU Hardware",),
        ("CPU Usage", "Processes"),
    ),
    Intent.MEMORY_ASSESSMENT: (
        ("Memory",),
        ("Processes",),
    ),
    Intent.DISK_ASSESSMENT: (
        ("Storage",),
        ("Filesystem", "Block Device Information"),
    ),
    Intent.NETWORK_ASSESSMENT_SINGLE: (
        ("Network",),
        (),
    ),
    Intent.PROCESS_ASSESSMENT: (
        ("Processes",),
        (),
    ),
    Intent.FILESYSTEM_ASSESSMENT: (
        ("Filesystem",),
        ("Block Device Information",),
    ),
    Intent.MACHINE_ASSESSMENT: (
        (
            "System Information",
            "CPU",
            "Memory",
            "Swap",
            "Storage",
        ),
        (
            "Filesystem",
            "Network",
            "Services",
            "Processes",
            "Time Synchronization",
            "Recent Logs",
            "Docker",
            "Block Device Information",
            "GPU Information",
        ),
    ),
    Intent.APPLICATION_DISCOVERY: (
        (
            "Installed Packages",
            "System Services",
            "Running Processes",
        ),
        (
            "Listening Ports",
            "Configuration Files",
            "Containers",
        ),
    ),
    Intent.SERVICE_ASSESSMENT: (
        ("Service Status",),
        (
            "Service Configuration",
            "Service Logs",
            "Running Processes",
            "Listening Ports",
        ),
    ),
    Intent.MONITORING_ASSESSMENT: (
        (
            "Active Problems",
            "Triggers",
            "Alert Severity",
            "Host Status",
            "Host Groups",
            "Templates",
        ),
        (
            "Dashboards",
            "Dashboard Folders",
            "Data Sources",
            "Alert Rules",
            "Event History",
            "Users",
            "Maintenance Status",
        ),
    ),
    Intent.SECURITY_ASSESSMENT: (
        (
            "SSH Configuration",
            "Firewall",
            "Secure Boot",
            "AppArmor",
            "SELinux",
        ),
        (
            "Recent Logins",
            "Listening Ports",
            "Certificates",
        ),
    ),
    Intent.PERFORMANCE_ASSESSMENT: (
        (
            "CPU Usage",
            "Memory Usage",
            "Disk Usage",
            "Load Average",
        ),
        (
            "Processes",
            "I/O Statistics",
            "Network Usage",
        ),
    ),
    Intent.STORAGE_ASSESSMENT: (
        (
            "Filesystems",
            "Disk Usage",
            "Mount Points",
        ),
        (
            "SMART Status",
            "RAID Status",
            "Storage Performance",
            "Block Device Information",
        ),
    ),
    Intent.NETWORK_ASSESSMENT: (
        ("Network",),
        (
            "DNS",
            "Listening Ports",
            "Firewall",
        ),
    ),
    Intent.CONFIGURATION_ASSESSMENT: (
        (
            "Configuration Files",
            "Installed Packages",
            "Services",
        ),
        (
            "Running Processes",
            "Environment Variables",
        ),
    ),
    Intent.TROUBLESHOOTING: (
        (
            "System Information",
            "Services",
            "Recent Logs",
        ),
        (
            "CPU",
            "Memory",
            "Disk Usage",
            "Network",
        ),
    ),
}


def _build_requirements(
    names: tuple[str, ...],
    required: bool,
    category: str = "",
) -> list[EvidenceRequirement]:
    """Build a list of EvidenceRequirement from a tuple of names."""
    return [
        EvidenceRequirement(name=name, required=required, category=category)
        for name in names
    ]


class EvidencePlanner:
    """Map Intent to evidence requirements.

    Responsibilities:
    - select the correct Evidence Template for the given Intent
    - populate InvestigationRequest with required and optional EvidenceRequirements

    Never performs collection or assessment.
    Never references tools, capabilities, providers, or execution.
    """

    def plan(self, request: InvestigationRequest) -> None:
        """Populate evidence requirements from the investigation intent.

        Uses the deterministic templates defined in
        docs/ai/06_EVIDENCE_TEMPLATES.md.

        Args:
            request: The InvestigationRequest. Must have intent populated.
                     Mutates required_evidence and optional_evidence.
        """
        intent = request.intent

        if intent is None or intent not in _TEMPLATES:
            request.required_evidence = []
            request.optional_evidence = []
            return

        required_names, optional_names = _TEMPLATES[intent]

        request.required_evidence = _build_requirements(
            required_names,
            required=True,
        )
        request.optional_evidence = _build_requirements(
            optional_names,
            required=False,
        )
