from __future__ import annotations

from src.pipeline.capability_planner import CapabilityPlanner
from src.pipeline.semantic_request import SemanticRequest


def test_plan_cpu_inspect() -> None:
    """Test that cpu inspect returns CPU + CPU Hardware."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="cpu", action="inspect")
    plan = cp.plan(semantic)
    assert "CPU" in plan
    assert "CPU Hardware" in plan


def test_plan_cpu_diagnose() -> None:
    """Test that cpu diagnose returns more capabilities than inspect."""
    cp = CapabilityPlanner()
    inspect_semantic = SemanticRequest(concept="cpu", action="inspect")
    diagnose_semantic = SemanticRequest(concept="cpu", action="diagnose")
    inspect_plan = cp.plan(inspect_semantic)
    diagnose_plan = cp.plan(diagnose_semantic)
    assert len(diagnose_plan) >= len(inspect_plan)


def test_plan_memory_inspect() -> None:
    """Test memory inspect returns Memory + Swap."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="memory", action="inspect")
    plan = cp.plan(semantic)
    assert "Memory" in plan
    assert "Swap" in plan


def test_plan_memory_diagnose() -> None:
    """Test that memory diagnose returns more capabilities."""
    cp = CapabilityPlanner()
    inspect_semantic = SemanticRequest(concept="memory", action="inspect")
    diagnose_semantic = SemanticRequest(concept="memory", action="diagnose")
    inspect_plan = cp.plan(inspect_semantic)
    diagnose_plan = cp.plan(diagnose_semantic)
    assert len(diagnose_plan) >= len(inspect_plan)


def test_plan_disk_inspect() -> None:
    """Test disk inspect returns Storage + Filesystem."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="disk", action="inspect")
    plan = cp.plan(semantic)
    assert "Storage" in plan
    assert "Filesystem" in plan


def test_plan_disk_diagnose() -> None:
    """Test that disk diagnose returns more capabilities."""
    cp = CapabilityPlanner()
    inspect_semantic = SemanticRequest(concept="disk", action="inspect")
    diagnose_semantic = SemanticRequest(concept="disk", action="diagnose")
    inspect_plan = cp.plan(inspect_semantic)
    diagnose_plan = cp.plan(diagnose_semantic)
    assert len(diagnose_plan) >= len(inspect_plan)


def test_plan_machine_inspect() -> None:
    """Test machine inspect gives a broad but not full set."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="machine", action="inspect")
    plan = cp.plan(semantic)
    assert "System Information" in plan
    assert "CPU" in plan


def test_plan_machine_diagnose() -> None:
    """Test machine diagnose returns many capabilities."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="machine", action="diagnose")
    plan = cp.plan(semantic)
    # Diagnose should have a comprehensive set
    assert len(plan) >= 8
    assert "System Information" in plan
    assert "Network" in plan
    assert "Processes" in plan


def test_plan_alerts_inspect() -> None:
    """Test alerts inspect returns Active Problems."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="alerts", action="inspect")
    plan = cp.plan(semantic)
    assert "Active Problems" in plan


def test_plan_service_inspect() -> None:
    """Test service inspect returns Services."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="service", action="inspect")
    plan = cp.plan(semantic)
    assert "Services" in plan


def test_plan_hostname_inspect() -> None:
    """Test hostname inspect returns System Information."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="hostname", action="inspect")
    plan = cp.plan(semantic)
    assert "System Information" in plan


def test_plan_kernel_inspect() -> None:
    """Test kernel inspect returns System Information."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="kernel", action="inspect")
    plan = cp.plan(semantic)
    assert "System Information" in plan


def test_plan_uptime_inspect() -> None:
    """Test uptime inspect uses the dedicated read-only uptime collector."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="uptime", action="inspect")
    plan = cp.plan(semantic)
    assert plan == ["System Uptime"]


def test_plan_load_inspect() -> None:
    """Test load inspect returns CPU."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="load", action="inspect")
    plan = cp.plan(semantic)
    assert "CPU" in plan


def test_plan_unknown_concept_falls_back_to_machine() -> None:
    """Test that an unknown concept falls back to machine plan."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="nonexistent_xyz", action="inspect")
    plan = cp.plan(semantic)
    assert len(plan) > 0
    # Should fall back to machine inspect
    assert "System Information" in plan


def test_plan_unknown_action_falls_back_to_inspect() -> None:
    """Test that unknown action falls back to inspect plan."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="cpu", action="unknown_action_xyz")
    plan = cp.plan(semantic)
    assert len(plan) > 0
    # Should fall back to cpu inspect
    assert "CPU" in plan


def test_plan_completely_unknown_falls_back_to_default() -> None:
    """Test that completely unknown (concept, action) gives reasonable fallback."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="nonexistent", action="nonexistent")
    plan = cp.plan(semantic)
    # Falls back to machine.inspect (since concept not found → machine, action not found → inspect)
    assert len(plan) >= 3
    assert "System Information" in plan
    assert "CPU" in plan


def test_plan_summarize_action() -> None:
    """Test that summarize returns fewer capabilities than inspect."""
    cp = CapabilityPlanner()
    inspect_semantic = SemanticRequest(concept="machine", action="inspect")
    summarize_semantic = SemanticRequest(concept="machine", action="summarize")
    inspect_plan = cp.plan(inspect_semantic)
    summarize_plan = cp.plan(summarize_semantic)
    # Summarize should be more lightweight than inspect
    assert len(summarize_plan) <= len(inspect_plan)


def test_plan_firewall_inspect() -> None:
    """Test firewall inspect returns Firewall."""
    cp = CapabilityPlanner()
    semantic = SemanticRequest(concept="firewall", action="inspect")
    plan = cp.plan(semantic)
    assert "Firewall" in plan
