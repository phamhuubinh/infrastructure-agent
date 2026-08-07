from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from src.model.config_store import FeatureFlagStore
from src.shared.config_schema import ConfigValidationError, validate_all_configs


def test_missing_feature_flag_file_uses_migration_defaults(tmp_path: Path) -> None:
    flags = FeatureFlagStore(tmp_path / "missing.yaml").load()

    assert flags.structured_command_result is False
    assert flags.canonical_facts is False
    assert flags.composite_rules is False
    assert flags.claim_guard is False


def test_feature_flag_file_loads_all_reviewed_flags(tmp_path: Path) -> None:
    path = tmp_path / "feature_flags.yaml"
    path.write_text(
        """schema_version: rollout.v1
structured_command_result: true
canonical_facts: true
composite_rules: true
claim_guard: true
"""
    )

    flags = FeatureFlagStore(path).load()

    assert flags.model_dump() == {
        "schema_version": "rollout.v1",
        "structured_command_result": True,
        "canonical_facts": True,
        "composite_rules": True,
        "claim_guard": True,
    }


def test_environment_override_can_roll_back_one_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "feature_flags.yaml"
    path.write_text("canonical_facts: true\ncomposite_rules: true\n")
    monkeypatch.setenv("ORION_FEATURE_CANONICAL_FACTS", "off")

    flags = FeatureFlagStore(path).load()

    assert flags.canonical_facts is False
    assert flags.composite_rules is True


def test_unknown_or_invalid_flag_value_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "feature_flags.yaml"
    path.write_text("not_a_flag: true\n")

    with pytest.raises(ValueError, match="Invalid feature flag configuration"):
        FeatureFlagStore(path).load()


def test_invalid_flag_environment_value_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORION_FEATURE_CLAIM_GUARD", "sometimes")

    with pytest.raises(ValueError, match="ORION_FEATURE_CLAIM_GUARD"):
        FeatureFlagStore(tmp_path / "missing.yaml").load()


def test_named_lookup_rejects_unknown_flag(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="Unknown feature flag"):
        FeatureFlagStore(tmp_path / "missing.yaml").is_enabled("anything_else")


def test_startup_validation_rejects_invalid_feature_flag_file(tmp_path: Path) -> None:
    flags_dir = tmp_path / "config"
    flags_dir.mkdir()
    (flags_dir / "feature_flags.yaml").write_text("canonical_fact: true\n")

    with mock.patch("src.shared.config_schema._project_root", return_value=tmp_path):
        with pytest.raises(ConfigValidationError, match="feature_flags.yaml"):
            validate_all_configs()
