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
