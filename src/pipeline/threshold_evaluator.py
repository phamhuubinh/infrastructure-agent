from __future__ import annotations


class ThresholdEvaluator:
    """Evaluate evidence against predefined thresholds to determine severity.

    Purely deterministic — no AI.
    """

    # Thresholds: (metric_key, operator, threshold_value) → severity
    # operator: "gt" (>), "lt" (<), "ge" (>=), "le" (<=), "eq" (==), "ne" (!=)
    #
    # Risk levels are calibrated for production servers:
    #   - >90% : critical (imminent risk of failure)
    #   - >80% : warning (needs attention)
    #   - <=80% : ok (normal operating range)
    # Disk thresholds use used_pct which is expected to be 0-100.
    _THRESHOLDS: tuple[tuple[str, str, float, str], ...] = (
        # Disk: any filesystem > 90% is critical, > 80% is warning.
        ("usage_percent", "gt", 90.0, "critical"),
        ("usage_percent", "gt", 80.0, "warning"),
        ("used_pct", "gt", 90.0, "critical"),
        ("used_pct", "gt", 80.0, "warning"),
        # Memory/RAM: > 90% critical, > 80% warning.
        ("memory_usage", "gt", 90.0, "critical"),
        ("memory_usage", "gt", 80.0, "warning"),
        ("memory_usage_pct", "gt", 90.0, "critical"),
        ("memory_usage_pct", "gt", 80.0, "warning"),
        # CPU: > 90% critical, > 80% warning.
        ("cpu_usage", "gt", 90.0, "critical"),
        ("cpu_usage", "gt", 80.0, "warning"),
        # Swap: any swap usage > 50% is warning (indicates memory pressure).
        ("swap_used_pct", "gt", 50.0, "warning"),
        ("swap_used_pct", "gt", 80.0, "critical"),
        ("swap_usage", "gt", 50.0, "warning"),
        ("swap_usage", "gt", 80.0, "critical"),
        # Zombie processes: any zombie is a warning.
        ("zombie_count", "gt", 0.0, "warning"),
        ("zombies", "gt", 0.0, "warning"),
        # Load average: depends on core count. Conservative defaults.
        ("load_1min", "gt", 8.0, "critical"),
        ("load_1min", "gt", 4.0, "warning"),
        ("load_5min", "gt", 6.0, "critical"),
        ("load_5min", "gt", 3.0, "warning"),
        # Failed services: any failed service is at least warning.
        ("failed_services_count", "gt", 0.0, "warning"),
        ("failed_count", "gt", 0.0, "warning"),
    )

    def evaluate(self, data: dict) -> str | None:
        """Evaluate a single evidence data dict against thresholds.

        Returns the highest severity found, or None if no threshold exceeded.

        Priority: critical > warning > info
        """
        highest: str | None = None
        for key, op, threshold, severity in self._THRESHOLDS:
            value = _extract_nested(data, key)
            if value is None:
                continue
            if not isinstance(value, (int, float)):
                continue
            if _compare(value, op, threshold):
                if highest is None or _severity_rank(severity) > _severity_rank(
                    highest
                ):
                    highest = severity
        return highest

    def evaluate_all(self, evidence_list: list) -> dict[str, str]:
        """Evaluate all evidence packages and return severity per evidence.

        Returns a dict mapping evidence_name → severity string.
        """
        result: dict[str, str] = {}
        for pkg in evidence_list:
            if not getattr(pkg, "success", False):
                continue
            data = getattr(pkg, "data", None)
            if not isinstance(data, dict):
                continue
            severity = self.evaluate(data)
            if severity:
                ev_name = getattr(pkg, "evidence_name", "unknown")
                result[ev_name] = severity
        return result


def _severity_rank(severity: str) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(severity, -1)


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == "gt":
        return value > threshold
    if op == "lt":
        return value < threshold
    if op == "ge":
        return value >= threshold
    if op == "le":
        return value <= threshold
    if op == "eq":
        return value == threshold
    if op == "ne":
        return value != threshold
    return False


def _extract_nested(data: dict, key: str) -> object | None:
    """Extract a value from a potentially nested dict using dot notation."""
    parts = key.split(".")
    current: object = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current
