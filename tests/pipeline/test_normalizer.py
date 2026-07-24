from __future__ import annotations

from src.pipeline.normalizer import Normalizer


def test_normalize_cpu_inspect() -> None:
    """Test that 'check cpu usage' normalizes to concept=cpu, action=inspect."""
    n = Normalizer()
    result = n.normalize("check cpu usage")
    assert result.concept == "cpu"
    assert result.action == "inspect"
    assert result.confidence >= 0.5


def test_normalize_memory_inspect() -> None:
    """Test that 'show ram usage' normalizes to concept=memory, action=inspect."""
    n = Normalizer()
    result = n.normalize("show ram usage")
    assert result.concept == "memory"
    assert result.action == "inspect"


def test_normalize_disk_inspect() -> None:
    """Test that 'kiểm tra ổ cứng' normalizes to concept=disk, action=inspect."""
    n = Normalizer()
    result = n.normalize("kiểm tra ổ cứng")
    assert result.concept == "disk"
    assert result.action == "inspect"


def test_normalize_network_diagnose() -> None:
    """Test that 'diagnose network issues' normalizes to concept=network, action=diagnose."""
    n = Normalizer()
    result = n.normalize("diagnose network issues")
    assert result.concept == "network"
    assert result.action == "diagnose"


def test_normalize_service_status() -> None:
    """Test that 'trạng thái dịch vụ' normalizes to concept=service, action=inspect."""
    n = Normalizer()
    result = n.normalize("trạng thái dịch vụ")
    assert result.concept == "service"
    assert result.action == "inspect"


def test_normalize_alerts_check() -> None:
    """Test that 'check alerts' normalizes to concept=alerts, action=inspect."""
    n = Normalizer()
    result = n.normalize("check alerts")
    assert result.concept == "alerts"
    assert result.action == "inspect"


def test_normalize_firewall_diagnose() -> None:
    """Test that 'troubleshoot firewall' normalizes to concept=firewall, action=diagnose."""
    n = Normalizer()
    result = n.normalize("troubleshoot firewall")
    assert result.concept == "firewall"
    assert result.action == "diagnose"


def test_normalize_ssh_config() -> None:
    """Test that 'ssh config' normalizes to concept=ssh (shorter input avoids
    'configuration' matching machine)."""
    n = Normalizer()
    result = n.normalize("ssh config")
    assert result.concept == "ssh"


def test_normalize_machine_overview() -> None:
    """Test that 'system overview' normalizes to concept=machine, action=summarize
    (because 'overview' is a summarize synonym)."""
    n = Normalizer()
    result = n.normalize("system overview")
    assert result.concept == "machine"
    assert result.action == "summarize"


def test_normalize_vietnamese_cpu() -> None:
    """Test Vietnamese input 'kiểm tra bộ xử lý' normalizes to cpu."""
    n = Normalizer()
    result = n.normalize("kiểm tra bộ xử lý")
    assert result.concept == "cpu"
    assert result.action == "inspect"


def test_normalize_vietnamese_memory() -> None:
    """Test Vietnamese input 'xem bộ nhớ' normalizes to memory."""
    n = Normalizer()
    result = n.normalize("xem bộ nhớ")
    assert result.concept == "memory"
    assert result.action == "inspect"


def test_normalize_vietnamese_disk() -> None:
    """Test Vietnamese input 'kiểm tra dung lượng' normalizes to disk."""
    n = Normalizer()
    result = n.normalize("kiểm tra dung lượng")
    assert result.concept == "disk"
    assert result.action == "inspect"


def test_normalize_vietnamese_network() -> None:
    """Test Vietnamese input 'kiểm tra mạng' normalizes to network."""
    n = Normalizer()
    result = n.normalize("kiểm tra mạng")
    assert result.concept == "network"
    assert result.action == "inspect"


def test_normalize_empty_input() -> None:
    """Test that empty input falls back to machine/inspect with zero confidence."""
    n = Normalizer()
    result = n.normalize("")
    assert result.concept == "machine"
    assert result.action == "inspect"
    assert result.confidence == 0.0


def test_normalize_whitespace_only() -> None:
    """Test that whitespace-only input falls back to machine/inspect."""
    n = Normalizer()
    result = n.normalize("   ")
    assert result.concept == "machine"
    assert result.action == "inspect"
    assert result.confidence == 0.0


def test_normalize_unknown_input() -> None:
    """Test that completely unknown input falls back to machine/inspect."""
    n = Normalizer()
    result = n.normalize("blah blah nothing relevant")
    assert result.concept == "machine"
    assert result.action == "inspect"


def test_normalize_with_target_extraction() -> None:
    """Test that 'check cpu on server01' extracts target_raw='server01'."""
    n = Normalizer()
    result = n.normalize("check cpu on server01")
    assert result.concept == "cpu"
    assert result.action == "inspect"
    assert result.target_raw == "server01"


def test_normalize_target_vietnamese() -> None:
    """Test that 'kiểm tra cpu trên server01' extracts target_raw='server01'."""
    n = Normalizer()
    result = n.normalize("kiểm tra cpu trên server01")
    assert result.concept == "cpu"
    assert result.action == "inspect"
    assert result.target_raw == "server01"


def test_normalize_confidence_full_match() -> None:
    """Test that matching both concept and action gives confidence 1.0."""
    n = Normalizer()
    result = n.normalize("diagnose memory leak")
    assert result.concept == "memory"
    assert result.action == "diagnose"
    assert result.confidence == 1.0


def test_normalize_confidence_partial_match() -> None:
    """Test that matching only concept (no action) gives confidence 0.5."""
    n = Normalizer()
    result = n.normalize("memory")
    assert result.concept == "memory"
    assert result.confidence == 0.5


def test_normalize_matched_synonyms() -> None:
    """Test that matched_synonyms contains the matching synonyms."""
    n = Normalizer()
    result = n.normalize("check cpu usage")
    assert "check" in result.matched_synonyms or "cpu" in result.matched_synonyms
    assert len(result.matched_synonyms) >= 1


def test_normalize_dashboards() -> None:
    """Test dashboard concept normalization."""
    n = Normalizer()
    result = n.normalize("show dashboards")
    assert result.concept == "dashboards"
    assert result.action == "inspect"


def test_normalize_diagnose_vietnamese() -> None:
    """Test Vietnamese diagnose patterns."""
    n = Normalizer()
    result = n.normalize("tại sao cpu cao")
    assert result.concept == "cpu"
    assert result.action == "diagnose"


def test_normalize_configure() -> None:
    """Test configure action."""
    n = Normalizer()
    result = n.normalize("cấu hình network")
    assert result.concept == "network"
    assert result.action == "configure"


def test_normalize_summarize() -> None:
    """Test summarize action."""
    n = Normalizer()
    result = n.normalize("tổng quan hệ thống")
    assert result.concept == "machine"
    assert result.action == "summarize"
