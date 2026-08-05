from __future__ import annotations

import json

from src.pipeline.finding import Finding, FindingDecision


def test_finding_is_json_serializable_and_explicit_about_missing_facts() -> None:
    finding = Finding(
        id="finding:test:server-1",
        type="cpu_saturation",
        score=0.45,
        decision=FindingDecision.INSUFFICIENT_EVIDENCE,
        severity="critical",
        supporting_fact_ids=("fact:one",),
        missing_facts=("cpu.load_per_core",),
        confidence=0.45,
        coverage=0.45,
        maximum_observable_score=0.45,
        maximum_possible_score=1.0,
        rule_id="test",
        rule_version="1.0.0",
    )

    serialized = json.loads(json.dumps(finding.to_dict()))

    assert serialized["decision"] == "insufficient_evidence"
    assert serialized["missing_facts"] == ["cpu.load_per_core"]
    assert finding.missing_fact_ids == ("cpu.load_per_core",)
