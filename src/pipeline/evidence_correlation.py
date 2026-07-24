from __future__ import annotations


class EvidenceCorrelation:
    """Cross-evidence correlation — detect co-occurring issues.

    When multiple pieces of evidence point to the same root cause
    (e.g., high CPU + high load + high memory usage), flag the
    correlation for the assessment to consider.
    """

    def correlate(
        self, evidence_list: list, threshold_eval: dict[str, str]
    ) -> list[dict[str, str]]:
        """Find correlated issues across evidence packages.

        Args:
            evidence_list: List of EvidencePackage objects.
            threshold_eval: Dict mapping evidence_name → severity from
                            ThresholdEvaluator.

        Returns:
            List of correlation findings, each with type, items, and
            description.
        """
        findings: list[dict[str, str]] = []
        severity_names = set(threshold_eval.keys())

        # CPU + Load correlation: high CPU + high load = bottleneck
        if "CPU" in severity_names and "CPU" in severity_names:
            findings.append(
                {
                    "type": "resource_bottleneck",
                    "items": "CPU, Load",
                    "description": "High CPU usage combined with elevated "
                    "load average may indicate a CPU-bound bottleneck.",
                }
            )

        # Memory + Swap correlation: high memory + swap usage = memory pressure
        mem_severity = threshold_eval.get("Memory")
        swap_severity = threshold_eval.get("Swap")
        if mem_severity or swap_severity:
            findings.append(
                {
                    "type": "memory_pressure",
                    "items": "Memory, Swap",
                    "description": "High memory or swap usage indicates "
                    "potential memory pressure. Consider increasing RAM "
                    "or reducing application footprint.",
                }
            )

        # Disk + Memory correlation: both high = system under heavy load
        if ("Storage" in severity_names or "Disk" in severity_names) and (
            "Memory" in severity_names or "CPU" in severity_names
        ):
            findings.append(
                {
                    "type": "system_overload",
                    "items": "Storage, Memory",
                    "description": "Multiple subsystems under pressure "
                    "suggests overall system overload.",
                }
            )

        return findings
