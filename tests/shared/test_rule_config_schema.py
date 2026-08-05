from __future__ import annotations

from pathlib import Path

import pytest

from src.shared.config_schema import RuleConfigFile, load_rule_configs


def _valid() -> dict:
    return {
        "schema_version": "reasoning.v1",
        "atomic_rules": [
            {
                "id": "cpu.test",
                "metric": "cpu.usage",
                "operator": "gt",
                "threshold": 80,
                "severity": "warning",
                "version": "1.0.0",
                "owner": "qa",
                "rationale": "reviewed threshold",
                "source_cases": ["case-1"],
                "review_status": "approved",
            }
        ],
    }


def test_reviewed_rule_config_converts_to_domain_model() -> None:
    config = RuleConfigFile.model_validate(_valid())

    rule = config.atomic_rules[0].to_domain()

    assert rule.id == "cpu.test"
    assert rule.version == "1.0.0"


def test_unreviewed_or_invalid_rule_fails_config_load_clearly() -> None:
    invalid = _valid()
    del invalid["atomic_rules"][0]["review_status"]

    with pytest.raises(ValueError, match="review_status"):
        RuleConfigFile.model_validate(invalid)


def test_production_rule_files_are_valid_and_have_unique_ids() -> None:
    root = Path(__file__).resolve().parents[2]
    configs = load_rule_configs(root / "config" / "rules")
    ids = [
        rule.id
        for config in configs
        for rule in config.atomic_rules + config.composite_rules
    ]

    assert configs
    assert len(ids) == len(set(ids))
