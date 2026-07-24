from __future__ import annotations

from src.pipeline.investigation_request import InvestigationRequest


class DeterministicResponder:
    """Generate deterministic responses without LLM when evidence is simple.

    Handles cases like zombie process counts and service status checks
    where the evidence itself contains enough information to answer.
    """

    def try_response(self, investigation: InvestigationRequest) -> str | None:
        raw = investigation.raw_request.lower()
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
        ) and any(kw in raw for kw in ("service", "dịch vụ", "sshd", "nginx"))

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

        for pkg in investigation.evidence:
            if not pkg.success or not isinstance(pkg.data, dict):
                continue

            if pkg.evidence_name == "Processes":
                result = self._check_zombie_processes(pkg.data)
                if result is not None:
                    return result

            if pkg.evidence_name == "Service Status" and is_service_status:
                result = self._check_service_status(pkg.data)
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

            if pkg.evidence_name in ("CPU", "CPU Information") and is_load:
                result = self._check_load_average(pkg.data)
                if result is not None:
                    return result

        return None

    def _check_zombie_processes(self, data: dict) -> str | None:
        zombies = (
            data.get("zombie_count") or data.get("zombie") or data.get("zombies") or 0
        )
        if not isinstance(zombies, (int, float)) or zombies <= 0:
            return None

        truncated = ""
        zombie_processes = data.get("zombie_processes") or []
        if zombie_processes:
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

    def _check_service_status(self, data: dict) -> str | None:
        failed_svcs = data.get("failed") or data.get("failed_services") or []
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

        all_svcs = data.get("services") or data.get("service_list") or []
        total = data.get("total") or data.get("service_count")
        if total is None:
            total = len(all_svcs)
        if isinstance(total, (int, float)) and total > 0:
            return (
                f"## Service Status\n\n"
                f"All **{int(total)} services** are running normally. "
                f"No failed or degraded services detected."
            )

        disabled = data.get("disabled") or data.get("disabled_services") or []
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

        return (
            "## Service Status\n\n"
            "No service status data available. Could not determine service state."
        )

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
        available_kb = (
            data.get("available_kb")
            or data.get("available")
            or data.get("free_kb")
            or data.get("free")
        )
        total_kb = data.get("total_kb") or data.get("total")
        if available_kb is None:
            return None
        if isinstance(available_kb, (int, float)) and isinstance(
            total_kb, (int, float)
        ):
            available_gb = round(available_kb / (1024**2), 1)
            total_gb = round(total_kb / (1024**2), 1)
            pct = round((available_kb / total_kb) * 100, 1) if total_kb else 0
            return (
                f"## Available RAM\n\n"
                f"**{available_gb} GB** available out of **{total_gb} GB** "
                f"({pct}% free)"
            )
        return f"## Available RAM\n\n**{available_kb} KB** available"

    def _check_load_average(self, data: dict) -> str | None:
        load_1 = data.get("load_1min") or data.get("load1")
        load_5 = data.get("load_5min") or data.get("load5")
        load_15 = data.get("load_15min") or data.get("load15")
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
