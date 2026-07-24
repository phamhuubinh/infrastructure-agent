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
    # Use the actual repo config path to test loading from config.
    Path(tmp.name).unlink(missing_ok=True)
    return result


def test_normalize_sv01_to_server01() -> None:
    """sv01 → server01 via pattern-based normalization."""
    resolver = _resolver_with_targets("server01", "localhost")
    result = resolver.normalize_target_name("sv01")
    assert result == "server01"


def test_normalize_srv01_to_server01() -> None:
    """srv01 → server01 via pattern-based normalization."""
    resolver = _resolver_with_targets("server01", "localhost")
    result = resolver.normalize_target_name("srv01")
    assert result == "server01"


def test_normalize_mon01_to_monitor() -> None:
    """mon01 → monitor via pattern-based normalization."""
    resolver = _resolver_with_targets("monitor", "localhost")
    result = resolver.normalize_target_name("mon01")
    assert result == "monitor"


def test_normalize_server_dash_01() -> None:
    """server-01 → server01 (strips dash)."""
    resolver = _resolver_with_targets("server01", "localhost")
    result = resolver.normalize_target_name("server-01")
    assert result == "server01"


def test_normalize_server_underscore_01() -> None:
    """server_01 → server01 (strips underscore)."""
    resolver = _resolver_with_targets("server01", "localhost")
    result = resolver.normalize_target_name("server_01")
    assert result == "server01"


def test_server_02_dash_normalization() -> None:
    """server-02 → server02."""
    resolver = _resolver_with_targets("server02", "localhost")
    result = resolver.normalize_target_name("server-02")
    assert result == "server02"


def test_localhost_synonym_may_nay() -> None:
    """'máy này' resolves to localhost."""
    resolver = _resolver_with_targets("localhost", "zabbix")
    req = InvestigationRequest(raw_request="kiểm tra máy này")
    resolver.resolve(req)
    assert req.target == "localhost"


def test_localhost_synonym_host_nay() -> None:
    """'host này' resolves to localhost."""
    resolver = _resolver_with_targets("localhost", "zabbix")
    req = InvestigationRequest(raw_request="check host này")
    resolver.resolve(req)
    assert req.target == "localhost"


def test_localhost_synonym_127_0_0_1() -> None:
    """127.0.0.1 resolves to localhost."""
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check 127.0.0.1")
    resolver.resolve(req)
    assert req.target == "localhost"


def test_localhost_synonym_ipv6() -> None:
    """::1 resolves to localhost."""
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check ::1")
    resolver.resolve(req)
    assert req.target == "localhost"


def test_sv05_resolves_to_server05() -> None:
    """sv05 → server05 via pattern matching in full resolve."""
    resolver = _resolver_with_targets("server05", "localhost")
    req = InvestigationRequest(raw_request="check cpu on sv05")
    # Should normalize sv05 → server05 and find it in known_names
    # at the normalized lookup step (Step 2).
    resolver.resolve(req)
    assert req.target == "server05"


def test_localhost_synonym_no_explicit_target() -> None:
    """'máy' (just the word, with no other target) resolves to localhost."""
    resolver = _resolver_with_targets("localhost", "zabbix")
    req = InvestigationRequest(raw_request="kiểm tra máy")
    # "máy" is a localhost synonym → resolves to localhost
    resolver.resolve(req)
    assert req.target == "localhost"


def test_normalized_name_no_match_raises_error() -> None:
    """If normalized target name doesn't exist, it falls through to
    the preposition check at Step 6 and raises UnknownTargetError."""
    resolver = _resolver_with_targets("localhost")
    req = InvestigationRequest(raw_request="check cpu on sv99")
    with pytest.raises(UnknownTargetError) as exc:
        resolver.resolve(req)
    assert "sv99" in str(exc.value)
