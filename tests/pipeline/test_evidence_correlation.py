from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.evidence_correlation import EvidenceCorrelation


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
