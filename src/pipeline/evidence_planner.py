from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from src.pipeline.answer_type import AnswerType
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.time_range_resolver import TemporalRequirement, TimeRange

if TYPE_CHECKING:
    from src.shared.pipeline_state import PipelineState, StateUpdate

# ---------------------------------------------------------------------------
# Evidence templates — source of truth: docs/ai/06_TOOL_AND_CAPABILITY_DESIGN.md
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

_CANONICAL_METRICS: dict[str, str] = {
    "System Information": "system.hostname",
    "CPU": "cpu.logical_cores",
    "CPU Hardware": "cpu.logical_cores",
    "CPU Runtime": "cpu.usage",
    "CPU Usage": "cpu.usage",
    "Memory": "memory.usage",
    "Memory Usage": "memory.usage",
    "Swap": "swap.total",
    "Storage": "filesystem.usage",
    "Disk Usage": "filesystem.usage",
    "Filesystem": "filesystem.mount",
    "Filesystems": "filesystem.mount",
    "Mount Points": "filesystem.mount",
    "Network": "network.interface",
    "Network Usage": "network.rx_bytes",
    "Services": "service.inventory",
    "System Services": "service.inventory",
    "Service Status": "service.status",
    "Processes": "process.count",
    "Running Processes": "process.count",
    "Load Average": "system.load_1m",
    "Active Problems": "monitoring.problem_active",
    "Triggers": "monitoring.trigger_active",
    "Alert Severity": "monitoring.trigger_active",
    "Host Status": "monitoring.host_enabled",
    "Dashboards": "monitoring.dashboard",
    "Alert Rules": "monitoring.alert_rule",
    "Event History": "monitoring.event",
}


def _build_requirements(
    names: tuple[str, ...],
    required: bool,
    category: str = "",
) -> list[EvidenceRequirement]:
    """Build a list of EvidenceRequirement from a tuple of names."""
    return [
        EvidenceRequirement(
            name=name,
            required=required,
            category=category,
            metric=_CANONICAL_METRICS.get(name, ""),
        )
        for name in names
    ]


class EvidencePlanner:
    """Map Intent to evidence requirements.

    Responsibilities:
    - select the correct Evidence Template for the given Intent
    - populate InvestigationRequest with required and optional EvidenceRequirements
    - return a StateUpdate dict for immutable state accumulation

    Never performs collection or assessment.
    Never references tools, capabilities, providers, or execution.
    """

    # ------------------------------------------------------------------
    # Immutable pipeline state interface.
    # ------------------------------------------------------------------

    def plan_state(self, state: PipelineState) -> StateUpdate:
        """Return an immutable StateUpdate with evidence requirements."""
        intent = state.intent

        if intent is None or intent not in _TEMPLATES:
            return {"required_evidence": (), "optional_evidence": ()}

        required_names, optional_names = _TEMPLATES[intent]

        required = tuple(
            EvidenceRequirement(
                name=name,
                required=True,
                metric=_CANONICAL_METRICS.get(name, ""),
            )
            for name in required_names
        )
        optional = tuple(
            EvidenceRequirement(
                name=name,
                required=False,
                metric=_CANONICAL_METRICS.get(name, ""),
            )
            for name in optional_names
        )

        required = self._temporalize(
            required,
            getattr(state.request_frame, "timeframe", None),
            getattr(state.request_frame, "answer_type", None),
        )
        return {
            "required_evidence": required,
            "optional_evidence": optional,
        }

    def plan(self, request: InvestigationRequest) -> None:
        """Populate evidence requirements from the investigation intent.

        Uses the deterministic templates defined in this module.

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
        params = getattr(request, "extracted_params", None)
        service_name = getattr(params, "service_name", None)
        if service_name:
            canonical_service = re.sub(
                r"[^a-z0-9_]+",
                "_",
                str(service_name).casefold().removesuffix(".service"),
            ).strip("_")
            request.required_evidence = [
                replace(
                    item,
                    metric=f"service.{canonical_service or 'unknown'}.status",
                    parameter_scope={"service_name": service_name},
                )
                if item.name == "Service Status"
                else item
                for item in request.required_evidence
            ]
        if getattr(params, "ping_target", None):
            self._append_required(request, "Network Latency")
        if getattr(params, "port", None):
            self._append_required(request, "Listening Ports")
        request.required_evidence = list(
            self._temporalize(
                tuple(request.required_evidence),
                getattr(request.request_frame, "timeframe", None),
                request.answer_type,
            )
        )

    @staticmethod
    def _append_required(request: InvestigationRequest, name: str) -> None:
        if not any(item.name == name for item in request.required_evidence):
            request.required_evidence.append(
                EvidenceRequirement(name=name, metric=_CANONICAL_METRICS.get(name, ""))
            )
        request.optional_evidence = [
            item for item in request.optional_evidence if item.name != name
        ]

    @staticmethod
    def _temporalize(
        requirements: tuple[EvidenceRequirement, ...],
        timeframe: object,
        answer_type: object,
    ) -> tuple[EvidenceRequirement, ...]:
        if not isinstance(timeframe, TimeRange) and answer_type not in {
            AnswerType.COMPARISON,
            AnswerType.FORECAST,
        }:
            return requirements
        resolved = timeframe if isinstance(timeframe, TimeRange) else None
        temporal_kind = (
            TemporalRequirement.FORECAST
            if answer_type is AnswerType.FORECAST
            else TemporalRequirement.COMPARISON
            if answer_type is AnswerType.COMPARISON
            else resolved.requirement
            if resolved is not None
            else TemporalRequirement.HISTORICAL
        )
        minimum_windows = 2 if temporal_kind is TemporalRequirement.COMPARISON else 1
        minimum_points = 6 if temporal_kind is TemporalRequirement.FORECAST else 2
        return tuple(
            replace(
                requirement,
                timeframe=resolved,
                requires_time_series=True,
                minimum_windows=minimum_windows,
                minimum_points=minimum_points,
                requires_growth_model=(
                    temporal_kind is TemporalRequirement.FORECAST
                ),
            )
            for requirement in requirements
        )
