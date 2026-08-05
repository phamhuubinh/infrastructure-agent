from __future__ import annotations

from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.temporal_evidence_guard import TemporalEvidenceGuard


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

            if (
                pkg.evidence_name in ("Processes", "Processes Information")
                and is_zombie
            ):
                result = self._check_zombie_processes(pkg.data)
                if result is not None:
                    return result

            if pkg.evidence_name == "Processes" and not is_zombie:
                result = self._check_zombie_processes(pkg.data)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("Service Status", "Services")
                and is_service_status
            ):
                result = self._check_service_status(
                    pkg.data, service_name=target_service
                )
                if result is not None:
                    return result

            if pkg.evidence_name == "System Information" and is_hostname:
                result = self._check_hostname(pkg.data)
                if result is not None:
                    return result

            if pkg.evidence_name == "System Information" and is_kernel:
                result = self._check_kernel(pkg.data)
                if result is not None:
                    return result

            if pkg.evidence_name in ("CPU", "CPU Information") and is_top_cpu:
                result = self._check_top_cpu(pkg.data)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("Memory", "Memory Information")
                and is_ram_available
            ):
                result = self._check_ram_available(pkg.data)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("CPU", "CPU Information", "CPU Hardware")
                and is_load
            ):
                result = self._check_load_average(pkg.data)
                if result is not None:
                    return result

            if (
                pkg.evidence_name
                in ("CPU", "CPU Information", "CPU Hardware", "System Information")
                and is_uptime
            ):
                result = self._check_uptime(pkg.data)
                if result is not None:
                    return result

            if pkg.evidence_name in ("Memory", "Memory Information") and is_swap:
                result = self._check_swap(pkg.data)
                if result is not None:
                    return result

            if (
                pkg.evidence_name in ("Network", "Network Information")
                and is_port_listen
            ):
                result = self._check_listening_ports(pkg.data)
                if result is not None:
                    return result

            if pkg.evidence_name in ("Storage", "Filesystem") and is_disk_full:
                result = self._check_disk_full(pkg.data)
                if result is not None:
                    return result

        return None

    def _check_zombie_processes(self, data: dict) -> str | None:
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

    def _check_service_status(
        self, data: dict, service_name: str | None = None
    ) -> str | None:
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

    def _check_hostname(self, data: dict) -> str | None:
        hostname = data.get("hostname") or data.get("name")
        if not hostname:
            return None
        return f"## Hostname\n\n**{hostname}**"

    def _check_kernel(self, data: dict) -> str | None:
        kernel = data.get("kernel") or data.get("kernel_version") or data.get("release")
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

    def _check_ram_available(self, data: dict) -> str | None:
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

    def _check_load_average(self, data: dict) -> str | None:
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

    def _check_swap(self, data: dict) -> str | None:
        """Extract swap usage from Memory evidence."""
        swap_total = _first_present(data, "swap_total", "swap_total_kb")
        swap_used = _first_present(data, "swap_used", "swap_used_kb")

        if swap_total is None and swap_used is None:
            return None

        lines = []
        if swap_total is not None:
            if isinstance(swap_total, (int, float)) and swap_total > 0:
                total_gb = round(swap_total / (1024**2), 1)
                lines.append(f"Total: **{total_gb} GB**")
            else:
                lines.append(f"Total: **{swap_total}**")
        else:
            lines.append("Total: **N/A**")

        if swap_used is not None:
            if isinstance(swap_used, (int, float)):
                used_gb = round(swap_used / (1024**2), 1)
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

    def _check_listening_ports(self, data: dict) -> str | None:
        """Extract listening ports from Network evidence."""
        ports = _first_present(
            data, "listening_ports", "open_ports", "ports"
        )
        if ports is None:
            return None
        if ports == [] or ports == {}:
            return "## Listening Ports\n\nNo listening ports were detected."

        if isinstance(ports, list):
            port_lines = []
            for p in ports[:20]:
                if isinstance(p, dict):
                    port_num = p.get("port", p.get("number", "?"))
                    proto = p.get("protocol", p.get("proto", ""))
                    service = p.get("service", p.get("name", ""))
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

    def _check_disk_full(self, data: dict) -> str | None:
        """Check if any filesystem is near capacity."""
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
