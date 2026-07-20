from __future__ import annotations

# ---------------------------------------------------------------------------
# Capability Library — single source of truth for ALL operational names
# ---------------------------------------------------------------------------
# This module defines every valid operational capability name in the system.
# All consumers (CapabilityRouter, KnowledgeTool, etc.) MUST reference
# VALID_OPERATIONAL_NAMES and COVERS_TO_OPERATIONAL rather than duplicating
# strings.
#
# Adding a new operational capability:
#   1. Add the name to _ALL_OPERATIONAL below.
#   2. If it maps from an evidence requirement, add an entry in
#      CAPABILITY_BY_EVIDENCE.
#   3. Add the covers-tag → operational-name mapping in COVERS_TO_OPERATIONAL.
#
# Capability names describe operational questions, not implementation
# actions. They remain stable even if the underlying tool or provider
# changes. Multiple evidence items may map to the same capability.

# ------------------------------------------------------------------
# Machine Assessment
# ------------------------------------------------------------------
MACHINE_ASSESSMENT: dict[str, str] = {
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
}
# ------------------------------------------------------------------
# Application Discovery
# ------------------------------------------------------------------
APPLICATION_DISCOVERY: dict[str, str] = {
    "Installed Packages": "Package Discovery",
    "System Services": "Service Discovery",
    "Running Processes": "Process Discovery",
    "Configuration Files": "Configuration Inspection",
    "Containers": "Container Discovery",
}
# ------------------------------------------------------------------
# Service Assessment
# ------------------------------------------------------------------
SERVICE_ASSESSMENT: dict[str, str] = {
    "Service Status": "Service Status",
    "Service Configuration": "Service Configuration Inspection",
    "Service Logs": "Service Log Discovery",
    "Dependencies": "Dependency Discovery",
}
# ------------------------------------------------------------------
# Monitoring Assessment
# ------------------------------------------------------------------
MONITORING_ASSESSMENT: dict[str, str] = {
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
}
# ------------------------------------------------------------------
# Security Assessment
# ------------------------------------------------------------------
SECURITY_ASSESSMENT: dict[str, str] = {
    "SSH Configuration": "SSH Configuration Inspection",
    "Firewall": "Firewall Inspection",
    "Secure Boot": "Secure Boot Status",
    "AppArmor": "AppArmor Status",
    "SELinux": "SELinux Status",
    "Recent Logins": "Recent Login Discovery",
    "Certificates": "Certificate Discovery",
}
# ------------------------------------------------------------------
# Performance Assessment
# ------------------------------------------------------------------
PERFORMANCE_ASSESSMENT: dict[str, str] = {
    "CPU Usage": "CPU Utilization",
    "Memory Usage": "Memory Utilization",
    "Disk Usage": "Disk Utilization",
    "Load Average": "System Load Assessment",
    "I/O Statistics": "I/O Performance Assessment",
    "Network Usage": "Network Utilization",
}
# ------------------------------------------------------------------
# Storage Assessment
# ------------------------------------------------------------------
STORAGE_ASSESSMENT: dict[str, str] = {
    "Filesystems": "Filesystem Discovery",
    "Disk Usage": "Disk Utilization",
    "Mount Points": "Mount Point Discovery",
    "SMART Status": "SMART Health Assessment",
    "RAID Status": "RAID Health Assessment",
    "Storage Performance": "Storage Performance Assessment",
}
# ------------------------------------------------------------------
# Network Assessment
# ------------------------------------------------------------------
NETWORK_ASSESSMENT: dict[str, str] = {
    "Network Interfaces": "Network Interface Discovery",
    "IP Configuration": "IP Configuration Assessment",
    "Default Gateway": "Default Gateway Discovery",
    "DNS": "DNS Configuration Assessment",
    "Routing": "Routing Table Assessment",
    "Listening Ports": "Port Discovery",
    "Firewall": "Firewall Inspection",
    "Configuration Files": "Configuration Inspection",
    "Environment Variables": "Environment Variable Discovery",
}
# ------------------------------------------------------------------
# Extended capabilities (evidence name == operational name)
# ------------------------------------------------------------------
EXTENDED: dict[str, str] = {
    "Firewall Status": "Firewall Status",
    "Block Device Information": "Block Device Information",
    "GPU Information": "GPU Information",
}
# ------------------------------------------------------------------
# Tool-level operational capabilities (no evidence mapping needed)
# ------------------------------------------------------------------
# These are defined here so that VALID_OPERATIONAL_NAMES is complete.
# Tools that use these need a covers-tag entry in COVERS_TO_OPERATIONAL above.
# These tool-level capabilities have no evidence-template mapping but are still
# registered as valid operational names. The evidence_name == operational_name
# entries below ensure they appear in CAPABILITY_BY_EVIDENCE for consistency.
# ------------------------------------------------------------------
# Convention mapping: covers tag → operational capability name
# ------------------------------------------------------------------
# This mapping translates tool-level "covers" tags to operational
# capability names. Every value MUST be present in
# VALID_OPERATIONAL_NAMES.
#
# When adding a new covers tag:
#   1. Ensure the target operational name exists in this file.
#   2. Add the tag → name entry here.

COVERS_TO_OPERATIONAL: dict[str, str] = {
    "system-identity": "System Information",
    "cpu": "CPU Information",
    "cpu_usage": "CPU Utilization",
    "memory": "Memory Information",
    "memory_usage": "Memory Utilization",
    "swap": "Swap Information",
    "storage": "Storage Information",
    "storage_performance": "Storage Performance Assessment",
    "filesystem": "Filesystem Information",
    "disk_usage": "Disk Utilization",
    "mount": "Mount Point Discovery",
    "filesystem_discovery": "Filesystem Discovery",
    "smart": "SMART Health Assessment",
    "raid": "RAID Health Assessment",
    "network": "Network Information",
    "interface": "Network Interface Discovery",
    "ip": "IP Configuration Assessment",
    "gateway": "Default Gateway Discovery",
    "dns": "DNS Configuration Assessment",
    "routing": "Routing Table Assessment",
    "listening-ports": "Port Discovery",
    "network_usage": "Network Utilization",
    "services": "Service Status",
    "service_config": "Service Configuration Inspection",
    "service_logs": "Service Log Discovery",
    "dependencies": "Dependency Discovery",
    "processes": "Process Discovery",
    "packages": "Package Discovery",
    "service_discovery": "Service Discovery",
    "container": "Container Discovery",
    "config": "Configuration Inspection",
    "load": "System Load Assessment",
    "system-time": "Time Synchronization",
    "system-logs": "Log Discovery",
    "io": "I/O Performance Assessment",
    "env": "Environment Variable Discovery",
    "secure-boot": "Secure Boot Status",
    "apparmor": "AppArmor Status",
    "selinux": "SELinux Status",
    "ssh": "SSH Configuration Inspection",
    "firewall": "Firewall Inspection",
    "sessions": "Recent Login Discovery",
    "certificates": "Certificate Discovery",
    "gpu": "GPU Information",
    "block_device": "Block Device Information",
    "firewall_status": "Firewall Status",
    "open_ports": "Port Discovery",
    "zabbix-problems": "Monitoring Problems",
    "zabbix-triggers": "Alert Triggers",
    "alert_severity": "Alert Severity Assessment",
    "zabbix-hosts": "Host Status Assessment",
    "zabbix-groups": "Host Group Discovery",
    "zabbix-templates": "Template Discovery",
    "zabbix-users": "Monitoring User Discovery",
    "zabbix-maintenance": "Maintenance Status Discovery",
    "zabbix-events": "Event History Discovery",
    "zabbix-interfaces": "Host Interface Discovery",
    "zabbix-items": "Item Discovery",
    "dashboards": "Dashboard Discovery",
    "monitoring-folders": "Dashboard Folder Discovery",
    "datasources": "Data Source Discovery",
    "monitoring-alerts": "Alert Rule Discovery",
    "monitoring-health": "Monitoring Health",
    "monitoring-version": "Monitoring Version",
    "panels": "Dashboard Panel Discovery",
    "queries": "Dashboard Query Discovery",
    "monitoring-annotations": "Monitoring Annotation Discovery",
    "users": "User Discovery",
    "hardware": "Hardware Inventory",
    "uptime": "System Uptime",
    "boot-time": "System Boot Time",
    "kernel-modules": "Kernel Module Discovery",
    "system-locale": "System Locale Discovery",
    "system-environment": "Environment Variable Discovery",
    "tls-certificates": "Certificate Discovery",
    "application-discovery": "Service Discovery",
    "web-content": "Web Content Fetch",
    "internet": "Internet Resource Access",
    "url-fetch": "URL Fetch",
    "knowledge-base-health": "Knowledge Base Health",
    "knowledge-base-ingest": "Knowledge Base Ingestion",
    "knowledge-base-query": "Knowledge Base Query",
    "documentation": "Documentation Lookup",
    "runbook": "Runbook Lookup",
}

_ADDITIONAL_EVIDENCE: dict[str, str] = {
    "Monitoring Health": "Monitoring Health",
    "Monitoring Version": "Monitoring Version",
    "Dashboard Panel Discovery": "Dashboard Panel Discovery",
    "Dashboard Query Discovery": "Dashboard Query Discovery",
    "Monitoring Annotation Discovery": "Monitoring Annotation Discovery",
    "User Discovery": "User Discovery",
    "Hardware Inventory": "Hardware Inventory",
    "System Uptime": "System Uptime",
    "System Boot Time": "System Boot Time",
    "Kernel Module Discovery": "Kernel Module Discovery",
    "System Locale Discovery": "System Locale Discovery",
}
_ADDITIONAL_OPERATIONAL: set[str] = {
    "Web Content Fetch",
    "Internet Resource Access",
    "URL Fetch",
    "Knowledge Base Health",
    "Knowledge Base Ingestion",
    "Knowledge Base Query",
    "Documentation Lookup",
    "Runbook Lookup",
}
# ------------------------------------------------------------------
# Combined mapping: evidence name → operational capability name
# ------------------------------------------------------------------
CAPABILITY_BY_EVIDENCE: dict[str, str] = {}
for _mapping in (
    MACHINE_ASSESSMENT,
    APPLICATION_DISCOVERY,
    SERVICE_ASSESSMENT,
    MONITORING_ASSESSMENT,
    SECURITY_ASSESSMENT,
    PERFORMANCE_ASSESSMENT,
    STORAGE_ASSESSMENT,
    NETWORK_ASSESSMENT,
    EXTENDED,
    _ADDITIONAL_EVIDENCE,
):
    CAPABILITY_BY_EVIDENCE.update(_mapping)

# ------------------------------------------------------------------
# Single source of truth: every valid operational name
# ------------------------------------------------------------------
VALID_OPERATIONAL_NAMES: set[str] = (
    set(CAPABILITY_BY_EVIDENCE.values()) | _ADDITIONAL_OPERATIONAL
)

# Validate that every operational name in COVERS_TO_OPERATIONAL is recognized
_unknown_covers = set(COVERS_TO_OPERATIONAL.values()) - VALID_OPERATIONAL_NAMES
if _unknown_covers:
    msg = (
        f"Unknown operational name(s) in COVERS_TO_OPERATIONAL: {sorted(_unknown_covers)}. "
        f"Add them to VALID_OPERATIONAL_NAMES or _ADDITIONAL_OPERATIONAL."
    )
    raise ValueError(msg)


def lookup(evidence_name: str) -> str | None:
    """Look up the capability name for a given evidence name."""
    return CAPABILITY_BY_EVIDENCE.get(evidence_name)
