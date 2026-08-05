from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.evidence_correlation import EvidenceCorrelation
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import FindingDecision
from tests.pipeline.reasoning_fact_factory import fact


@dataclass
class _FakePkg:
    success: bool = True
    data: dict | None = None
    evidence_name: str = "CPU"


def test_no_correlation() -> None:
    ec = EvidenceCorrelation()
    findings = ec.correlate([], {})
    assert findings == []


def test_cpu_memory_correlation() -> None:
    ec = EvidenceCorrelation()
    findings = ec.correlate([], {"CPU": "warning", "Memory": "warning"})
    assert len(findings) >= 1


def test_disk_cpu_correlation() -> None:
    ec = EvidenceCorrelation()
    findings = ec.correlate([], {"Storage": "critical", "CPU": "critical"})
    assert any(f["type"] == "system_overload" for f in findings)


def test_findings_have_required_keys() -> None:
    ec = EvidenceCorrelation()
    findings = ec.correlate([], {"Memory": "warning"})
    for f in findings:
        assert "type" in f
        assert "items" in f
        assert "description" in f


def test_single_issue_no_multi_correlation() -> None:
    ec = EvidenceCorrelation()
    findings = ec.correlate([], {"CPU": "warning"})
    # Single CPU warning should not trigger a "system_overload" alone
    assert not any(f["type"] == "system_overload" for f in findings)


def test_canonical_correlation_returns_findings_used_by_pipeline() -> None:
    facts = FactSet(
        (
            fact("cpu.usage", 92.0),
            fact("system.load_1m", 8.0, unit="load"),
            fact("cpu.logical_cores", 4, unit="count"),
            fact("cpu.iowait", 25.0),
        )
    )

    findings = EvidenceCorrelation().correlate_facts(facts)

    cpu = next(finding for finding in findings if finding.type == "cpu_saturation")
    assert cpu.decision is FindingDecision.SUPPORTED
    assert cpu.source_links
