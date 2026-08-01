from __future__ import annotations

from src.pipeline.security.tool_inspector import (
    InspectionContext,
    InspectionResult,
    InspectionVerdict,
    ToolInspector,
)

# Capabilities that are known to mutate system state.
# These are blocked by default in the ReadOnlyInspector.
# The list is intentionally conservative — only capabilities
# with verified write side-effects are listed here.
_MUTATING_CAPABILITIES: set[str] = {
    "service_restart",
    "service_start",
    "service_stop",
    "service_enable",
    "service_disable",
    "process_kill",
    "reboot",
    "shutdown",
    "package_install",
    "package_remove",
    "package_update",
    "file_write",
    "file_delete",
    "file_chmod",
    "file_chown",
    "user_create",
    "user_delete",
    "user_modify",
    "firewall_add_rule",
    "firewall_remove_rule",
    "docker_container_start",
    "docker_container_stop",
    "docker_container_restart",
    "docker_container_remove",
    "iptables_add",
    "iptables_delete",
    "cron_add",
    "cron_remove",
}

# Capability names that signal read-only operations.
_READ_ONLY_PREFIXES: tuple[str, ...] = (
    "get_",
    "list_",
    "check_",
    "read_",
    "show_",
    "query_",
    "fetch_",
    "inspect_",
    "describe_",
    "monitor_",
    "collect_",
    "assess_",
    "diagnose_",
    "analyze_",
    "audit_",
    "scan_",
    "verify_",
    "validate_",
    "report_",
    "export_",
    "view_",
    "display_",
    "find_",
    "search_",
    "calc_",
    "compute_",
    "measure_",
    "test_",
    "ping_",
    "resolve_",
    "lookup_",
    "discover_",
)


class ReadOnlyInspector(ToolInspector):
    """Inspector that validates capabilities are read-only.

    Enforces the architectural guarantee that Orion's capabilities
    do not mutate system state. This is the primary safety mechanism —
    it transforms "currently happens to be read-only" into an
    enforced architectural constraint.

    Detection strategy (ordered, first match wins):
    1. Explicit block list: If the capability name is in
       ``_MUTATING_CAPABILITIES``, deny.
    2. Heuristic allow: If the capability name starts with a known
       read-only prefix (e.g., ``get_``, ``list_``), allow.
    3. Default: Deny. New capabilities must be explicitly named with a
       read-only prefix or added to the reviewed policy.
    """

    @property
    def name(self) -> str:
        return "ReadOnlyInspector"

    def inspect(self, context: InspectionContext) -> InspectionResult:
        cap_name = context.capability_name.lower()

        # 1. Explicit block list.
        if cap_name in _MUTATING_CAPABILITIES:
            return InspectionResult(
                verdict=InspectionVerdict.DENY,
                reason=(
                    f"Capability '{context.capability_name}' is classified as "
                    f"mutating and is not allowed in read-only execution mode."
                ),
                inspector_name=self.name,
            )

        # 2. Heuristic: known read-only prefixes.
        if cap_name.startswith(_READ_ONLY_PREFIXES):
            return InspectionResult(
                verdict=InspectionVerdict.ALLOW,
                inspector_name=self.name,
            )

        # 3. Fail closed for unknown capabilities.
        return InspectionResult(
            verdict=InspectionVerdict.DENY,
            reason=(
                f"Capability '{context.capability_name}' has no explicit "
                f"read-only classification. Denied by default."
            ),
            inspector_name=self.name,
        )
