from __future__ import annotations

# ---------------------------------------------------------------------------
# Capability Library — single source of truth
# ---------------------------------------------------------------------------
# Source of truth: docs/ai/07_CAPABILITY_GRAPH.md
#
# This library defines the mapping from evidence names (from Evidence
# Templates) to operational capability names. Capability names describe
# operational questions rather than implementation actions.
#
# Capability names remain stable even if the underlying implementation
# (tool, command, API) changes. They are independent of any specific
# Child Tool, provider, or infrastructure domain.
#
# Multiple evidence items may map to the same capability when they
# represent the same operational fact.

CAPABILITY_BY_EVIDENCE: dict[str, str] = {
    # ------------------------------------------------------------------
    # Machine Assessment
    # ------------------------------------------------------------------
    "System Information": "System Information",
    "CPU": "CPU Information",
    "CPU Hardware": "CPU Information",
    "CPU Runtime": "CPU Information",
    "Memory": "Memory Information",
    "Swap": "Swap Information",
    "Storage": "Storage Information",
    "Filesystem": "Filesystem Information",
    "Network": "Network Information",
    "Services": "Service Status",
    "Processes": "Process Discovery",
    "Time Synchronization": "Time Synchronization",
    "Recent Logs": "Log Discovery",
    "Docker": "Container Discovery",
    "Security Status": "Security Posture Summary",

    # ------------------------------------------------------------------
    # Application Discovery
    # ------------------------------------------------------------------
    "Installed Packages": "Package Discovery",
    "System Services": "Service Discovery",
    "Running Processes": "Process Discovery",
    "Listening Ports": "Port Discovery",
    "Configuration Files": "Configuration Inspection",
    "Containers": "Container Discovery",

    # ------------------------------------------------------------------
    # Service Assessment
    # ------------------------------------------------------------------
    "Service Status": "Service Status",
    "Service Configuration": "Service Configuration Inspection",
    "Service Logs": "Service Log Discovery",
    "Dependencies": "Dependency Discovery",

    # ------------------------------------------------------------------
    # Monitoring Assessment
    # ------------------------------------------------------------------
    "Active Problems": "Monitoring Problems",
    "Triggers": "Alert Triggers",
    "Alert Severity": "Alert Severity Assessment",
    "Host Status": "Host Status Assessment",
    "Host Groups": "Host Group Discovery",
    "Templates": "Template Discovery",
    "Dashboards": "Dashboard Discovery",
    "Dashboard Folders": "Dashboard Folder Discovery",
    "Data Sources": "Data Source Discovery",
    "Alert Rules": "Alert Rule Discovery",
    "Event History": "Event History Discovery",
    "Users": "Monitoring User Discovery",
    "Maintenance Status": "Maintenance Status Discovery",
    "Host Interfaces": "Host Interface Discovery",
    "Items": "Item Discovery",
    "Alerts": "Alert Discovery",

    # ------------------------------------------------------------------
    # Security Assessment
    # ------------------------------------------------------------------
    "SSH Configuration": "SSH Configuration Inspection",
    "Firewall": "Firewall Inspection",
    "Secure Boot": "Secure Boot Status",
    "AppArmor": "AppArmor Status",
    "SELinux": "SELinux Status",
    "Recent Logins": "Recent Login Discovery",
    "Certificates": "Certificate Discovery",

    # ------------------------------------------------------------------
    # Performance Assessment
    # ------------------------------------------------------------------
    "CPU Usage": "CPU Utilization",
    "Memory Usage": "Memory Utilization",
    "Disk Usage": "Disk Utilization",
    "Load Average": "System Load Assessment",
    "I/O Statistics": "I/O Performance Assessment",
    "Network Usage": "Network Utilization",

    # ------------------------------------------------------------------
    # Storage Assessment
    # ------------------------------------------------------------------
    "Filesystems": "Filesystem Discovery",
    "Disk Usage": "Disk Utilization",
    "Mount Points": "Mount Point Discovery",
    "SMART Status": "SMART Health Assessment",
    "RAID Status": "RAID Health Assessment",
    "Storage Performance": "Storage Performance Assessment",

    # ------------------------------------------------------------------
    # Network Assessment
    # ------------------------------------------------------------------
    "Network Interfaces": "Network Interface Discovery",
    "IP Configuration": "IP Configuration Assessment",
    "Default Gateway": "Default Gateway Discovery",
    "DNS": "DNS Configuration Assessment",
    "Routing": "Routing Table Assessment",
    "Listening Ports": "Port Discovery",
    "Firewall": "Firewall Inspection",

    # ------------------------------------------------------------------
    # Configuration Assessment
    # ------------------------------------------------------------------
    "Configuration Files": "Configuration Inspection",
    "Environment Variables": "Environment Variable Discovery",

    # ------------------------------------------------------------------
    # Extended capabilities (newly routed — same name, no transformation)
    # ------------------------------------------------------------------
    "Firewall Status": "Firewall Status",
    "Block Device Information": "Block Device Information",
    "GPU Information": "GPU Information",
    "Listening Ports": "Port Discovery",

    # ------------------------------------------------------------------
    # Troubleshooting — no fixed mapping; evidence depends on the problem
    # ------------------------------------------------------------------
}


def lookup(evidence_name: str) -> str | None:
    """Look up the capability name for a given evidence name.

    Args:
        evidence_name: The evidence requirement name from an
                       EvidenceRequirement.

    Returns:
        The operational capability name, or None if no mapping exists.
    """
    return CAPABILITY_BY_EVIDENCE.get(evidence_name)
