#!/usr/bin/env python3
"""Dump complete AssessmentRequest for every test case."""

import sys, json
from src.agent.runtime_factory import create_deterministic_agent
from src.pipeline.assessment_adapter import AssessmentAdapter
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt

agent = create_deterministic_agent()
adapter = AssessmentAdapter()

tests = [
    ("TEST 1", "Đánh giá toàn bộ sức khỏe của localhost."),
    ("TEST 2", "Đánh giá security baseline của localhost."),
    ("TEST 3", "Đánh giá hiệu năng của localhost."),
    ("TEST 4", "Đánh giá network của localhost."),
    ("TEST 5", "Đánh giá storage của localhost."),
    ("TEST 6", "Đánh giá monitoring của hệ thống."),
    ("TEST 7", "Kiểm tra Zabbix có vấn đề gì."),
    ("TEST 8", "Dashboard Grafana có monitor đầy đủ không."),
    ("TEST 9", "Có service nào đang gặp sự cố không."),
    ("TEST 10", "Máy này có vấn đề gì nghiêm trọng không."),
]

for label, question in tests:
    print(f"\n{'='*80}")
    print(f"  {label}: {question}")
    print(f"{'='*80}")

    investigation = agent.execute_pipeline_only(question)
    assessment_req = adapter.build(investigation)
    prompt = build_assessment_prompt(assessment_req)
    prompt_size = len(prompt)

    print(f"\n  Intent: {investigation.intent.name if investigation.intent else 'N/A'}")
    print(f"  Target: {investigation.target or 'N/A'}")
    print(f"  Evidence required: {len(investigation.required_evidence)}")
    print(f"  Evidence optional: {len(investigation.optional_evidence)}")
    print(f"  Evidence collected: {len(assessment_req.evidence)}")
    print(f"  Complete: {assessment_req.evidence_complete}")
    print(f"  Missing: {assessment_req.missing_evidence}")
    print(f"  Prompt size: {prompt_size} bytes")
    print()

    success_count = 0
    fail_count = 0
    for pkg in assessment_req.evidence:
        if pkg.success:
            success_count += 1
        else:
            fail_count += 1

        print(f"  {'─'*70}")
        status = "SUCCESS" if pkg.success else "FAIL"
        print(f"  [{status}] {pkg.capability_name}")
        print(f"  Evidence name: {pkg.evidence_name}")
        if not pkg.success:
            print(f"  Error: {pkg.error}")
            continue

        data = pkg.data or {}
        if isinstance(data, dict):
            for key, value in sorted(data.items()):
                if isinstance(value, list):
                    print(f"    {key}: list[{len(value)}]")
                    if value and isinstance(value[0], dict):
                        print(f"      fields: {list(value[0].keys())}")
                elif isinstance(value, dict):
                    print(f"    {key}: dict -> {json.dumps(value)[:200]}")
                elif value is None:
                    print(f"    {key}: None")
                else:
                    print(f"    {key}: {value}")
        elif isinstance(data, list):
            print(f"  list[{len(data)}]")
            if data and isinstance(data[0], dict):
                print(f"    fields: {list(data[0].keys())}")
        else:
            print(f"  {data}")

    print()
    print(f"  Total evidence: {len(assessment_req.evidence)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Complete: {assessment_req.evidence_complete}")

    # Detect duplicates
    cap_names = [p.capability_name for p in assessment_req.evidence if p.success]
    seen = set()
    duplicates = []
    for name in cap_names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        print(f"  DUPLICATE capabilities: {duplicates}")

    # Evidence required but not collected
    required_names = {e.name for e in investigation.required_evidence}
    collected_names = {p.evidence_name for p in assessment_req.evidence if p.success}
    missing_required = required_names - collected_names
    if missing_required:
        print(f"  MISSING required evidence: {missing_required}")
PYEOF