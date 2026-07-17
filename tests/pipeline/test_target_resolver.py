from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.target_resolver import TargetResolver, UnknownTargetError
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


def _resolver_with_targets(*targets: str) -> TargetResolver:
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write('{"targets": {}}')
    tmp.close()
    store = TargetStore(path=tmp.name)
    registry = TargetRegistry(store=store)
    for t in targets:
        try:
            registry.add(t)
        except ValueError:
            pass
    result = TargetResolver(target_registry=registry)
    Path(tmp.name).unlink(missing_ok=True)
    return result


def test_known_target_resolves() -> None:
    resolver = _resolver_with_targets("localhost", "zabbix")
    req = InvestigationRequest(raw_request="check cpu on localhost")
    resolver.resolve(req)
    assert req.target == "localhost"


def test_on_preposition_detects_unknown_target() -> None:
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check cpu on server01")
    with pytest.raises(UnknownTargetError) as exc:
        resolver.resolve(req)
    assert "server01" in str(exc.value)


def test_for_preposition_detects_unknown_target() -> None:
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check disks for database")
    with pytest.raises(UnknownTargetError) as exc:
        resolver.resolve(req)
    assert "database" in str(exc.value)


def test_at_preposition_detects_unknown_target() -> None:
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check at zabbix01")
    with pytest.raises(UnknownTargetError) as exc:
        resolver.resolve(req)
    assert "zabbix01" in str(exc.value)


def test_no_unknown_target_for_common_words() -> None:
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check alerts")
    resolver.resolve(req)
    assert req.target == "localhost"


def test_no_unknown_target_when_target_exists() -> None:
    resolver = _resolver_with_targets("zabbix")
    req = InvestigationRequest(raw_request="check on zabbix")
    resolver.resolve(req)
    assert req.target == "zabbix"


def test_unknown_target_error_contains_available_list() -> None:
    resolver = _resolver_with_targets("localhost", "zabbix", "grafana")
    req = InvestigationRequest(raw_request="check cpu on nonexistent")
    with pytest.raises(UnknownTargetError) as exc:
        resolver.resolve(req)
    assert "nonexistent" in str(exc.value)
    assert "localhost" in str(exc.value)
    assert "zabbix" in str(exc.value)


def test_localhost_fallback_when_no_explicit_target() -> None:
    resolver = _resolver_with_targets("localhost", "zabbix")
    req = InvestigationRequest(raw_request="check cpu usage")
    resolver.resolve(req)
    assert req.target == "localhost"


def test_monitoring_assignment_falls_back_to_zabbix() -> None:
    from src.pipeline.intent_resolver import IntentResolver

    resolver = _resolver_with_targets("localhost", "zabbix")
    intent_resolver = IntentResolver()
    req = intent_resolver.resolve("show alerts")
    resolver.resolve(req)
    assert req.target == "zabbix"
