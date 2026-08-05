from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.target_resolver import (
    AmbiguousTargetError,
    TargetResolver,
    UnknownTargetError,
)
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
    req = InvestigationRequest(raw_request="check disks for somehost")
    with pytest.raises(UnknownTargetError) as exc:
        resolver.resolve(req)
    assert "somehost" in str(exc.value)


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


def test_close_fuzzy_targets_require_clarification() -> None:
    resolver = _resolver_with_targets("localhost", "server01", "server02")
    req = InvestigationRequest(raw_request="check cpu on server0")

    with pytest.raises(AmbiguousTargetError) as exc:
        resolver.resolve(req)

    assert exc.value.candidates[:2] == ("server01", "server02")
    assert req.target is None


def test_unknown_alphabetic_hostname_never_falls_back_to_localhost() -> None:
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check cpu on webserver")

    with pytest.raises(UnknownTargetError):
        resolver.resolve(req)

    assert req.target is None


def test_target_resolution_exposes_score_candidates_and_margin() -> None:
    resolver = _resolver_with_targets("localhost", "server01")
    req = InvestigationRequest(raw_request="check cpu on server01")

    resolver.resolve(req)

    assert req.target == "server01"
    assert req.target_score == 1.0
    assert req.target_margin == 1.0
    assert req.target_candidates[0].target == "server01"
