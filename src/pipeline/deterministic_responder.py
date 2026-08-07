from __future__ import annotations

from collections.abc import Mapping

from src.pipeline.fact import FactValidity
from src.pipeline.health_aggregator import HealthStatus
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.temporal_evidence_guard import TemporalEvidenceGuard


def _package_has_untrustworthy_facts(pkg: object) -> bool:
    """DR1-707: refuse the deterministic fast path when a package's own
    canonical facts are contradictory or stale.

    The raw-dict responders below were written before canonical Facts
    existed and still read ``pkg.data`` directly for speed. That is only
    safe when nothing in ``pkg.facts`` (the canonical, validity-checked
    view of the same evidence) disagrees with itself. If the fact
    normalizer already flagged this package as contradictory/stale, the
    fast path must not answer from the raw payload — fall through to the
    LLM assessment path, which is given the contradiction explicitly via
    ``AssessmentRequest`` and is instructed not to silently pick a number.
    """

    facts = getattr(pkg, "facts", ())
    return any(
        fact.validity in (FactValidity.CONTRADICTORY, FactValidity.STALE)
        for fact in facts
    )


def _safe_parse_pct(value: object) -> float | None:
    """Safely parse a percentage value that may include '%' suffix."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%").strip()
        try:
            return float(stripped)
        except (ValueError, TypeError):
            return None
    return None


def _first_present(data: dict, *keys: str) -> object | None:
    """Return the first present non-None value, preserving legitimate zeroes."""

    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _facts_by_metric(pkg: object, metric: str) -> tuple:
    """DR1-707: canonical, validity-checked view of a package's evidence.

    Returns only ``usable`` facts (VALID/VALID_EMPTY, not stale) for the
    given metric name. Responders below prefer this over ``pkg.data`` when
    a metric has canonical Fact coverage from the normalizer; raw-dict
    reads remain only for fields that have no Fact representation yet
    (documented per-method below).
    """

    return tuple(
        f for f in getattr(pkg, "facts", ()) if f.metric == metric and f.usable
    )


def _first_fact_value(pkg: object, metric: str, *, subject: str | None = None):
    """Return the value of the first usable fact matching metric (and
    optionally subject), or None if no such canonical fact exists."""

    for f in _facts_by_metric(pkg, metric):
        if subject is None or f.subject == subject:
            return f.value
    return None


class DeterministicResponder:
    """Generate deterministic responses without LLM when evidence is simple.

    Handles cases like zombie process counts and service status checks
    where the evidence itself contains enough information to answer.
    """

    def try_response(self, investigation: InvestigationRequest) -> str | None:
        temporal = TemporalEvidenceGuard().evaluate(investigation)
        if not temporal.sufficient:
            return TemporalEvidenceGuard.refusal(temporal.failures)

        raw = investigation.raw_request.lower()
        is_overall_health = any(
            phrase in raw
            for phrase in (
                "health",
                "healthy",
                "sức khỏe",
                "tình trạng tổng thể",
                "kiểm tra máy",
                "check server",
                "check system",
            )
        )
        if is_overall_health and investigation.health_summary is not None:
            return self._health_response(investigation)

        # Extract params for service-specific queries.
        params = getattr(investigation, "extracted_params", None)
        target_service = params.service_name if params else None

        is_service_status = any(
            kw in raw
            for kw in (
                "status",
                "trạng thái",
                "chạy",
                "die",
                "down",
                "disabled",
                "enabled",
            )
        ) and any(kw in raw for kw in ("service", "dịch vụ", "sshd", "nginx", "docker"))

        is_hostname = any(kw in raw for kw in ("hostname", "tên máy"))
        is_kernel = any(
            kw in raw for kw in ("kernel", "uname", "phiên bản kernel", "hạt nhân")
        )
        is_top_cpu = any(
            kw in raw
            for kw in ("top cpu", "tiến trình cpu", "cpu cao nhất", "top process")
        )
        is_ram_available = any(
            kw in raw
            for kw in ("ram available", "còn trống bộ nhớ", "ram còn trống", "ram free")
        )
        is_load = any(
            kw in raw
            for kw in (
                "load average",
                "tải trung bình",
                "tải cpu",
                "tải hệ thống",
                "mức tải",
            )
        )
        is_uptime = any(
            kw in raw
            for kw in (
                "uptime",
                "thời gian chạy",
                "thời gian hoạt động",
                "đã chạy bao lâu",
                "chạy được bao lâu",
                "chạy bao lâu",
            )
        )
        is_swap = any(kw in raw for kw in ("swap", "bộ nhớ ảo", "phân vùng trao đổi"))
        is_port_listen = any(
            kw in raw
            for kw in (
                "port",
                "cổng",
                "listen",
                "listening",
                "đang listen",
                "đang mở",
                "lắng nghe",
                "cổng nào",
            )
        )
        is_zombie = any(
            kw in raw for kw in ("zombie", "process zombie", "tiến trình zombie")
        )
        is_disk_full = any(
            kw in raw
            for kw in (
                "đầy",
                "full",
                "gần đầy",
                "còn trống",
                "còn bao nhiêu",
                "dung lượng",
            )
        )

        for pkg in investigation.evidence:
            if not pkg.valid_for_requirements or not isinstance(pkg.data, dict):
                continue
            if _package_has_untrustworthy_facts(pkg):
                # DR1-707: contradictory/stale canonical facts back this
                # package — do not answer from its raw payload.
                continue

            if (
                pkg.evidence_name in ("Processes", "Processes Information")
                and is_zombie
            ):
                result = self._check_zombie_processes(pkg)
                if result is not None:
                    return result

            if pkg.evidence_name == "Processes" and not is_zombie:
                result = self._check_zombie_processes(pkg)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("Service Status", "Services")
                and is_service_status
            ):
                result = self._check_service_status(
                    pkg, service_name=target_service
                )
                if result is not None:
                    return result

            if pkg.evidence_name == "System Information" and is_hostname:
                result = self._check_hostname(pkg)
                if result is not None:
                    return result

            if pkg.evidence_name == "System Information" and is_kernel:
                result = self._check_kernel(pkg)
                if result is not None:
                    return result

            if pkg.evidence_name in ("CPU", "CPU Information") and is_top_cpu:
                # DR1-707: no canonical Fact metric exists yet for "top CPU
                # processes" (only cpu.usage/cpu.model/system.load are
                # normalized). Reads pkg.data directly until a
                # process.top_cpu fact is added to LinuxFactNormalizer.
                result = self._check_top_cpu(pkg.data)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("Memory", "Memory Information")
                and is_ram_available
            ):
                result = self._check_ram_available(pkg)
                if result is not None:
                    return result

            if (
                pkg.evidence_name
                in ("CPU", "CPU Information", "CPU Hardware", "Load Average")
                and is_load
            ):
                result = self._check_load_average(pkg)
                if result is not None:
                    return result

            if (
                pkg.evidence_name
                in (
                    "CPU",
                    "CPU Information",
                    "CPU Hardware",
                    "System Information",
                    "System Uptime",
                )
                and is_uptime
            ):
                # DR1-707: no canonical Fact metric exists yet for uptime
                # (LinuxFactNormalizer does not emit system.uptime). Reads
                # pkg.data directly until that normalizer gap is closed.
                result = self._check_uptime(pkg.data)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("Memory", "Memory Information", "Swap")
                and is_swap
            ):
                result = self._check_swap(pkg)
                if result is not None:
                    return result

            if (
                pkg.evidence_name
                in ("Network", "Network Information", "Listening Ports")
                and is_port_listen
            ):
                result = self._check_listening_ports(pkg)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("Storage", "Filesystem", "Disk Usage")
                and is_disk_full
            ):
                result = self._check_disk_full(pkg)
                if result is not None:
                    return result

        return None

    @staticmethod
    def _health_response(investigation: InvestigationRequest) -> str:
        summary = investigation.health_summary
        assert summary is not None
        status = summary.status
        facts_by_id = {fact.id: fact for fact in investigation.fact_set}
        if status is HealthStatus.CRITICAL:
            incident_ids = {
                fact_id
                for target in summary.targets
                for fact_id in target.active_incident_fact_ids
            }
            labels: list[str] = []
            for fact_id in sorted(incident_ids):
                fact = facts_by_id.get(fact_id)
                value = getattr(fact, "value", None)
                if isinstance(value, Mapping):
                    label = value.get("name") or value.get("description")
                    if label:
                        labels.append(str(label))
            finding_types = sorted(
                {
                    finding.type
                    for finding in investigation.findings
                    if finding.decision.value == "supported"
                    and finding.severity == "critical"
                }
            )
            issues = labels + finding_types
            detail = ", ".join(issues[:10]) or "active critical incident"
            return (
                "## System Health: Critical\n\n"
                f"Active issue(s) were detected: **{detail}**. "
                "The system must not be reported as healthy while these "
                "incidents/findings remain active."
            )
        if status is HealthStatus.UNAVAILABLE:
            missing = ", ".join(summary.incomplete_evidence) or "health evidence"
            return (
                "## System Health: Incomplete Evidence\n\n"
                f"Health cannot be confirmed because **{missing}** is unavailable, "
                "stale, failed, or contradictory."
            )
        if status is HealthStatus.WARNING:
            warning_types = sorted(
                {
                    finding.type
                    for finding in investigation.findings
                    if finding.decision.value == "supported"
                }
            )
            return (
                "## System Health: Warning\n\n"
                "Supported finding(s): **"
                + ", ".join(warning_types)
                + "**."
            )
        return (
            "## System Health: Healthy\n\n"
            "No active monitoring incident or supported warning was found "
            "within the complete collected evidence scope."
        )

    def _check_zombie_processes(self, pkg: object) -> str | None:
        data = pkg.data if isinstance(pkg.data, dict) else {}
        # DR1-707: process.zombie_count is a canonical Fact (see
        # LinuxFactNormalizer._processes); prefer it over the raw dict key
        # guess. The optional PID listing has no Fact representation yet,
        # so that part still reads pkg.data directly.
        zombies = _first_fact_value(pkg, "process.zombie_count")
        if zombies is None:
            zombies = _first_present(data, "zombie_count", "zombie", "zombies")
        if not isinstance(zombies, (int, float)) or zombies <= 0:
            return None

        truncated = ""
        zombie_processes = data.get("zombie_processes")
        if isinstance(zombie_processes, list) and zombie_processes:
            truncated_list = list(zombie_processes)[:5]
            truncated = f": {', '.join(str(p) for p in truncated_list)}"
            if len(zombie_processes) > 5:
                truncated += f" (+{len(zombie_processes) - 5} more)"

        return (
            f"## Zombie Process Detected\n\n"
            f"There {'are' if zombies > 1 else 'is'} **{int(zombies)} zombie "
            f"process{'es' if zombies > 1 else ''}** on this system{truncated}.\n\n"
            f"Zombie processes consume process table entries (PID) and may indicate "
            f"a parent process that failed to call `wait()`/`waitpid()`. "
            f"Check the parent process or restart the orphaned service."
        )

    _SERVICE_ALIASES = {
        "sshd": ("sshd", "ssh", "openssh-server"),
        "nginx": ("nginx",),
        "docker": ("docker",),
        "apache2": ("apache2", "httpd", "apache"),
        "postgresql": ("postgresql", "postgres"),
        "mysql": ("mysql", "mariadb"),
        "redis": ("redis", "redis-server"),
        "mongod": ("mongod", "mongodb"),
    }

    def _check_service_status_from_facts(
        self, pkg: object, service_name: str
    ) -> str | None:
        lookup_names = self._SERVICE_ALIASES.get(service_name, (service_name,))
        for f in _facts_by_metric(pkg, "service.status"):
            dims = f.dimensions or {}
            fact_service_name = str(dims.get("service_name", "")).casefold()
            if not fact_service_name:
                continue
            if any(name in fact_service_name for name in lookup_names):
                status = str(f.value)
                status_emoji = (
                    "✅" if status in ("active", "running", "enabled") else "❌"
                )
                return (
                    f"## Service: {fact_service_name}\n\n"
                    f"{status_emoji} Status: **{status}**"
                )
        return None

    def _check_service_status(
        self, pkg: object, service_name: str | None = None
    ) -> str | None:
        data = pkg.data if isinstance(pkg.data, dict) else {}

        # DR1-707: when a specific service is asked about, prefer the
        # canonical service.status Fact (subject "service:<name>",
        # dimensions.service_name) over raw dict lookup. Generic
        # failed/disabled-service summaries have no canonical Fact yet
        # (LinuxFactNormalizer only emits service.inventory, not
        # per-service failure/disabled state for the "Services" bulk
        # capability), so that path still reads pkg.data directly.
        if service_name:
            fact_result = self._check_service_status_from_facts(pkg, service_name)
            if fact_result is not None:
                return fact_result

        failed_value = _first_present(data, "failed_services", "failed")
        failed_svcs = failed_value if isinstance(failed_value, list) else []
        failed_count = (
            failed_value if isinstance(failed_value, (int, float)) else None
        )
        services_value = _first_present(data, "services", "service_list")
        all_svcs = services_value if isinstance(services_value, list) else []

        # If user asked about a specific service, look it up.
        if service_name:
            # Normalize common service name variants.
            _svc_map = {
                "sshd": ["sshd", "ssh", "openssh-server"],
                "nginx": ["nginx"],
                "docker": ["docker"],
                "apache2": ["apache2", "httpd", "apache"],
                "postgresql": ["postgresql", "postgres"],
                "mysql": ["mysql", "mariadb"],
                "redis": ["redis", "redis-server"],
                "mongod": ["mongod", "mongodb"],
            }
            lookup_names = _svc_map.get(service_name, [service_name])

            # Search through service lists for a match.
            svc_entry = None
            for svc in all_svcs:
                if isinstance(svc, dict):
                    name = str(svc.get("name", svc.get("service", ""))).lower()
                    status = str(svc.get("status", svc.get("state", ""))).lower()
                    if any(ln in name for ln in lookup_names):
                        svc_entry = {"name": name, "status": status}
                        break
            if svc_entry:
                svc_status = svc_entry.get("status")
                if not svc_status:
                    return None
                status_emoji = (
                    "✅" if svc_status in ("active", "running", "enabled") else "❌"
                )
                return (
                    f"## Service: {svc_entry['name']}\n\n"
                    f"{status_emoji} Status: **{svc_status}**"
                )

            # Check failed list.
            for fs in failed_svcs:
                if any(ln in str(fs).lower() for ln in lookup_names):
                    return (
                        f"## Service: {service_name}\n\n"
                        f"❌ Status: **failed**\n\n"
                        f"Use `systemctl status {service_name}` or "
                        f"`journalctl -u {service_name}` for detailed error logs."
                    )

            # Service not found in data.
            return (
                f"## Service: {service_name}\n\n"
                f"⚠️ Could not find **{service_name}** in the service list. "
                f"It may not be installed or the service name may differ."
            )

        # Generic service status check.
        if isinstance(failed_svcs, list) and failed_svcs:
            f_list = [str(s) for s in failed_svcs[:10]]
            summary = ", ".join(f_list)
            if len(failed_svcs) > 10:
                summary += f" (+{len(failed_svcs) - 10} more)"
            return (
                f"## Failed Services\n\n"
                f"The following **{len(failed_svcs)} service{'s' if len(failed_svcs) > 1 else ''}** "
                f"{'are' if len(failed_svcs) > 1 else 'is'} in a failed state: {summary}\n\n"
                f"Use `systemctl status <service>` or `journalctl -u <service>` "
                f"for detailed error logs."
            )

        if failed_count is not None and failed_count > 0:
            return (
                "## Failed Services\n\n"
                f"The collector reports **{int(failed_count)} failed services**."
            )

        total = _first_present(data, "total", "service_count")
        if total is None and services_value is not None:
            total = len(all_svcs)
        if (
            isinstance(total, (int, float))
            and total >= 0
            and failed_count == 0
        ):
            return (
                f"## Service Status\n\n"
                f"No failed services were detected among **{int(total)} services**."
            )

        disabled_value = _first_present(data, "disabled", "disabled_services")
        disabled = disabled_value if isinstance(disabled_value, list) else []
        if isinstance(disabled, list) and disabled:
            d_list = [str(s) for s in disabled[:10]]
            summary = ", ".join(d_list)
            if len(disabled) > 10:
                summary += f" (+{len(disabled) - 10} more)"
            return (
                f"## Disabled Services\n\n"
                f"The following **{len(disabled)} service{'s' if len(disabled) > 1 else ''}** "
                f"{'are' if len(disabled) > 1 else 'is'} disabled: {summary}"
            )

        return None

    def _check_hostname(self, pkg: object) -> str | None:
        hostname = _first_fact_value(pkg, "system.hostname")
        if not hostname:
            data = pkg.data if isinstance(pkg.data, dict) else {}
            hostname = data.get("hostname") or data.get("name")
        if not hostname:
            return None
        return f"## Hostname\n\n**{hostname}**"

    def _check_kernel(self, pkg: object) -> str | None:
        kernel = _first_fact_value(pkg, "system.kernel")
        if not kernel:
            data = pkg.data if isinstance(pkg.data, dict) else {}
            kernel = (
                data.get("kernel") or data.get("kernel_version") or data.get("release")
            )
        if not kernel:
            return None
        return f"## Kernel Version\n\n**{kernel}**"

    def _check_top_cpu(self, data: dict) -> str | None:
        top_procs = (
            data.get("top_processes")
            or data.get("top_consumers")
            or data.get("heavy_processes")
        )
        if not isinstance(top_procs, list) or not top_procs:
            return None
        lines = []
        for p in top_procs[:5]:
            if isinstance(p, dict):
                name = p.get("name", "?")
                cpu = p.get("cpu", p.get("cpu_percent", "?"))
                lines.append(f"- **{name}**: {cpu}% CPU")
            else:
                lines.append(f"- {p}")
        header = "## Top CPU Processes\n\n"
        return header + "\n".join(lines)

    def _check_ram_available(self, pkg: object) -> str | None:
        # DR1-707: memory.available/memory.total are canonical Facts in
        # bytes (see LinuxFactNormalizer._memory). The legacy dict lookup
        # below expects "available_kb"/"total_kb"-style keys that do not
        # match the real get_memory schema (available_bytes/total_bytes),
        # so it rarely matched real payloads — Facts are the correct and
        # now-primary source.
        available_bytes = _first_fact_value(pkg, "memory.available")
        total_bytes = _first_fact_value(pkg, "memory.total")
        if isinstance(available_bytes, (int, float)):
            available_gb = round(available_bytes / (1024**3), 1)
            response = f"## Available RAM\n\n**{available_gb} GB** available"
            if isinstance(total_bytes, (int, float)) and total_bytes > 0:
                total_gb = round(total_bytes / (1024**3), 1)
                pct = round((available_bytes / total_bytes) * 100, 1)
                response = (
                    f"## Available RAM\n\n"
                    f"**{available_gb} GB** available out of **{total_gb} GB** "
                    f"({pct}% free)"
                )
            return response

        data = pkg.data if isinstance(pkg.data, dict) else {}
        available_kb = _first_present(
            data, "available_kb", "available", "free_kb", "free"
        )
        total_kb = _first_present(data, "total_kb", "total")
        if available_kb is None:
            return None
        if isinstance(available_kb, (int, float)) and isinstance(
            total_kb, (int, float)
        ):
            available_gb = round(available_kb / (1024**2), 1)
            total_gb = round(total_kb / (1024**2), 1)
            response = (
                f"## Available RAM\n\n"
                f"**{available_gb} GB** available out of **{total_gb} GB**"
            )
            if total_kb > 0:
                pct = round((available_kb / total_kb) * 100, 1)
                response += f" ({pct}% free)"
            return response
        return f"## Available RAM\n\n**{available_kb} KB** available"

    def _check_load_average(self, pkg: object) -> str | None:
        # DR1-707: system.load_1m/5m/15m are canonical Facts (see
        # LinuxFactNormalizer._load); prefer them over dict key guessing.
        load_1 = _first_fact_value(pkg, "system.load_1m")
        load_5 = _first_fact_value(pkg, "system.load_5m")
        load_15 = _first_fact_value(pkg, "system.load_15m")
        if load_1 is None and load_5 is None and load_15 is None:
            data = pkg.data if isinstance(pkg.data, dict) else {}
            load_1 = _first_present(data, "load_1min", "load1")
            load_5 = _first_present(data, "load_5min", "load5")
            load_15 = _first_present(data, "load_15min", "load15")
        if load_1 is None and load_5 is None and load_15 is None:
            return None
        parts = []
        if load_1 is not None:
            parts.append(f"1 min: **{load_1}**")
        if load_5 is not None:
            parts.append(f"5 min: **{load_5}**")
        if load_15 is not None:
            parts.append(f"15 min: **{load_15}**")
        return f"## Load Average\n\n{' | '.join(parts)}"

    def _check_uptime(self, data: dict) -> str | None:
        """Extract uptime from CPU or System Information evidence."""
        uptime_sec = _first_present(
            data, "uptime_seconds", "uptime", "uptime_sec"
        )
        if uptime_sec is None:
            return None
        if isinstance(uptime_sec, (int, float)):
            days = int(uptime_sec // 86400)
            hours = int((uptime_sec % 86400) // 3600)
            minutes = int((uptime_sec % 3600) // 60)
            parts = []
            if days > 0:
                parts.append(f"{days} day{'s' if days > 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
            if minutes > 0 or not parts:
                parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
            uptime_str = ", ".join(parts)
            return f"## Uptime\n\n**{uptime_str}**"
        return f"## Uptime\n\n**{uptime_sec}**"

    def _check_swap(self, pkg: object) -> str | None:
        """Extract swap usage from Memory evidence."""
        # DR1-707: swap.total/swap.used are canonical Facts in bytes,
        # emitted by both LinuxFactNormalizer._memory (get_memory) and
        # ._swap (get_swap). The legacy dict lookup below expects
        # "swap_total"/"swap_total_kb"-style keys that do not match either
        # real schema (swap_total_bytes/total_bytes) — Facts are the
        # correct and now-primary source.
        swap_total = _first_fact_value(pkg, "swap.total")
        swap_used = _first_fact_value(pkg, "swap.used")
        divisor = 1024**3
        if swap_total is None and swap_used is None:
            data = pkg.data if isinstance(pkg.data, dict) else {}
            swap_total = _first_present(data, "swap_total", "swap_total_kb")
            swap_used = _first_present(data, "swap_used", "swap_used_kb")
            divisor = 1024**2

        if swap_total is None and swap_used is None:
            return None

        lines = []
        if swap_total is not None:
            if isinstance(swap_total, (int, float)) and swap_total > 0:
                total_gb = round(swap_total / divisor, 1)
                lines.append(f"Total: **{total_gb} GB**")
            else:
                lines.append(f"Total: **{swap_total}**")
        else:
            lines.append("Total: **N/A**")

        if swap_used is not None:
            if isinstance(swap_used, (int, float)):
                used_gb = round(swap_used / divisor, 1)
                lines.append(f"Used: **{used_gb} GB**")
            else:
                lines.append(f"Used: **{swap_used}**")
        else:
            lines.append("Used: **N/A**")

        if (
            isinstance(swap_total, (int, float))
            and isinstance(swap_used, (int, float))
            and swap_total > 0
        ):
            pct = round((swap_used / swap_total) * 100, 1)
            lines.append(f"Usage: **{pct}%**")

        return "## Swap\n\n" + "\n".join(lines)

    def _check_listening_ports(self, pkg: object) -> str | None:
        """Extract listening ports from Network evidence."""
        # DR1-707: network.listening_socket is a canonical Fact per port
        # (see LinuxFactNormalizer._listening_ports); prefer the collected
        # facts over raw dict key guessing when present.
        fact_ports = [f.value for f in _facts_by_metric(pkg, "network.listening_socket")]
        if fact_ports:
            ports: object = fact_ports
        else:
            data = pkg.data if isinstance(pkg.data, dict) else {}
            ports = _first_present(data, "listening_ports", "open_ports", "ports")
            if ports is None:
                return None
        if ports == [] or ports == {}:
            return "## Listening Ports\n\nNo listening ports were detected."

        if isinstance(ports, list):
            port_lines = []
            for p in ports[:20]:
                if isinstance(p, dict):
                    port_num = p.get(
                        "port_number", p.get("port", p.get("number", "?"))
                    )
                    proto = p.get("protocol", p.get("proto", ""))
                    service = p.get(
                        "process", p.get("service", p.get("name", ""))
                    )
                    entry = f"- **{port_num}**/{proto}"
                    if service:
                        entry += f" ({service})"
                    port_lines.append(entry)
                else:
                    port_lines.append(f"- {p}")
            if len(ports) > 20:
                port_lines.append(f"  (+{len(ports) - 20} more)")
            return (
                f"## Listening Ports\n\n"
                f"{len(ports)} port{'s' if len(ports) > 1 else ''} listening:\n\n"
                + "\n".join(port_lines)
            )

        if isinstance(ports, dict):
            port_lines = []
            for port_num, info in list(ports.items())[:20]:
                if isinstance(info, dict):
                    service = info.get("service", info.get("name", ""))
                    entry = f"- **{port_num}**"
                    if service:
                        entry += f" ({service})"
                    port_lines.append(entry)
                else:
                    port_lines.append(f"- **{port_num}**: {info}")
            return (
                f"## Listening Ports\n\n"
                f"{len(ports)} port{'s' if len(ports) > 1 else ''} listening:\n\n"
                + "\n".join(port_lines)
            )

        return f"## Listening Ports\n\n**{ports}**"

    def _check_disk_full(self, pkg: object) -> str | None:
        """Check if any filesystem is near capacity."""
        # DR1-707: filesystem.usage is a canonical Fact per mountpoint (see
        # LinuxFactNormalizer._disk); prefer it over raw dict key guessing
        # when present.
        usage_facts = _facts_by_metric(pkg, "filesystem.usage")
        if usage_facts:
            fs_lines = []
            near_full = []
            for f in usage_facts[:15]:
                mount = (f.dimensions or {}).get("mountpoint", "?")
                pct_val = _safe_parse_pct(f.value)
                if pct_val is None:
                    fs_lines.append(f"- **{mount}**: ?")
                    continue
                if pct_val > 80:
                    near_full.append((mount, pct_val))
                fs_lines.append(f"- **{mount}**: {pct_val:.1f}%")
            if len(usage_facts) > 15:
                fs_lines.append(f"  (+{len(usage_facts) - 15} more)")

            result = "## Disk Usage\n\n" + "\n".join(fs_lines)
            if near_full:
                nf_summary = ", ".join(f"**{m}** ({p:.1f}%)" for m, p in near_full)
                result += (
                    f"\n\n⚠️ **Near capacity**: {nf_summary}\n"
                    f"Consider freeing space or expanding storage."
                )
            return result

        data = pkg.data if isinstance(pkg.data, dict) else {}
        filesystems = _first_present(
            data, "disks", "filesystems", "mounts", "mount_points"
        )
        if not filesystems:
            # Check for single filesystem data.
            total = _first_present(data, "total", "total_kb")
            used = _first_present(data, "used", "used_kb")
            if total is not None and used is not None:
                if not isinstance(total, (int, float)) or total <= 0:
                    return None
                if not isinstance(used, (int, float)):
                    return None
                pct = round((used / total) * 100, 1)
                mount = data.get(
                    "mount", data.get("mount_point", data.get("target", "/"))
                )
                return f"## Disk: {mount}\n\n**{pct}%** used"
            return None

        if isinstance(filesystems, list):
            fs_lines = []
            near_full = []
            has_any_pct = False
            for fs in filesystems[:15]:
                if isinstance(fs, dict):
                    mount = fs.get(
                        "mount",
                        fs.get(
                            "mount_point", fs.get("target", fs.get("mountpoint", "?"))
                        ),
                    )
                    used_pct = fs.get(
                        "use_percent",
                        fs.get("used_pct", fs.get("usage_percent", fs.get("pct"))),
                    )
                    pct_val = _safe_parse_pct(used_pct)
                    if pct_val is not None:
                        has_any_pct = True
                        if pct_val > 80:
                            near_full.append((mount, pct_val))
                        fs_lines.append(f"- **{mount}**: {pct_val:.1f}%")
                    else:
                        fs_lines.append(f"- **{mount}**: ?")
                else:
                    fs_lines.append(f"- {fs}")
            if len(filesystems) > 15:
                fs_lines.append(f"  (+{len(filesystems) - 15} more)")

            # If no entry had any percentage data, return None to let
            # the loop try the next evidence package (e.g., Storage after Filesystem).
            if not has_any_pct:
                return None

            result = "## Disk Usage\n\n" + "\n".join(fs_lines)
            if near_full:
                nf_summary = ", ".join(f"**{m}** ({p:.1f}%)" for m, p in near_full)
                result += (
                    f"\n\n⚠️ **Near capacity**: {nf_summary}\n"
                    f"Consider freeing space or expanding storage."
                )
            return result

        if isinstance(filesystems, dict):
            fs_lines = []
            near_full = []
            for mount, info in list(filesystems.items())[:15]:
                if isinstance(info, dict):
                    used_pct = info.get(
                        "use_percent", info.get("used_pct", info.get("usage_percent"))
                    )
                    pct_val = _safe_parse_pct(used_pct)
                    if pct_val is not None:
                        if pct_val > 80:
                            near_full.append((mount, pct_val))
                        fs_lines.append(f"- **{mount}**: {pct_val:.1f}%")
                    else:
                        fs_lines.append(f"- **{mount}**: ?")
                else:
                    fs_lines.append(f"- **{mount}**: {info}")

            result = "## Disk Usage\n\n" + "\n".join(fs_lines)
            if near_full:
                nf_summary = ", ".join(f"**{m}** ({p:.1f}%)" for m, p in near_full)
                result += (
                    f"\n\n⚠️ **Near capacity**: {nf_summary}\n"
                    f"Consider freeing space or expanding storage."
                )
            return result

        return None
