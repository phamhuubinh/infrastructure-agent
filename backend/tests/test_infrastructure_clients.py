from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.integrations.infrastructure import InfrastructureError, TargetCatalog


@pytest.mark.parametrize("targets_key", ["targets", "integrations"])
@pytest.mark.parametrize("flat", [False, True])
def test_catalog_loads_only_linux_targets_and_their_credentials(
    targets_key: str, flat: bool
) -> None:
    linux = {
        "target_ref": "linux-one",
        "display_name": "Linux One",
        "ssh_alias": "private-ssh-alias",
        "credential_ref": "ssh",
    }
    grafana = {"target_ref": "grafana", "credential_ref": "grafana-token"}
    zabbix = {"target_ref": "zabbix", "credential_ref": "zabbix-token"}
    targets: object = (
        [
            {"family": "linux", **linux},
            {"family": "grafana", **grafana},
            {"family": "zabbix", **zabbix},
        ]
        if flat
        else {"linux": linux, "grafana": [grafana], "zabbix": [zabbix]}
    )
    catalog = TargetCatalog.from_mapping(
        {
            "credentials": {
                "ssh": "private-ssh-credential",
                "grafana-token": "retired-grafana-credential",
                "zabbix-token": "retired-zabbix-credential",
            },
            targets_key: targets,
        }
    )
    target = catalog.resolve("linux", "linux-one")

    assert catalog.model_context() == (("linux", "linux-one", "Linux One"),)
    assert target.connection["ssh_alias"] == "private-ssh-alias"
    assert catalog.credentials.resolve(target.credential_ref) == "private-ssh-credential"
    for family in ("grafana", "zabbix"):
        assert not catalog.configured(family)
        with pytest.raises(InfrastructureError, match="Configured credentials are unavailable"):
            catalog.credentials.resolve(f"{family}-token")


def test_catalog_prefers_explicit_config_and_uses_ssh_fallback_without_monitoring_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssh_config = tmp_path / "ssh_config"
    ssh_config.write_text("Host fallback\n", encoding="utf-8")
    monkeypatch.setenv("ORION_SSH_CONFIG_PATH", str(ssh_config))
    monkeypatch.setenv("ORION_SSH_TARGET_REFS", "fallback,invalid alias,")
    monkeypatch.delenv("ORION_INFRASTRUCTURE_CONFIG", raising=False)

    fallback = TargetCatalog.from_environment()
    assert fallback.model_context() == (("linux", "fallback", "fallback"),)
    target = fallback.resolve("linux", "fallback")
    assert target.connection["ssh_alias"] == "fallback"
    assert fallback.credentials.resolve(target.credential_ref) == "ssh-config"

    config = tmp_path / "infrastructure.json"
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    config.write_text(
        json.dumps({"targets": {"linux": [{"target_ref": "explicit", "ssh_alias": "configured"}]}}),
        encoding="utf-8",
    )
    assert TargetCatalog.from_environment().model_context() == (("linux", "explicit", "explicit"),)

    config.write_text("{invalid JSON", encoding="utf-8")
    assert TargetCatalog.from_environment().model_context() == ()
