from __future__ import annotations

import argparse
import sys
from typing import Any

from benchmark.dataset import BENCHMARKS
from benchmark.report import generate_human_report, generate_json_report
from benchmark.scoring import score


def _build_deterministic_runtime():
    """Build and return a DeterministicAgent for benchmark execution.

    This is the production runtime. Benchmarks must validate the same
    runtime used by CLI (default mode).
    """
    from src.pipeline.capability_resolver import CapabilityResolver
    from src.pipeline.evidence_merge import EvidenceMerge
    from src.pipeline.evidence_planner import EvidencePlanner
    from src.pipeline.execution_engine import ExecutionEngine
    from src.pipeline.execution_graph import ExecutionGraphBuilder
    from src.pipeline.execution_planner import ExecutionPlanner
    from src.pipeline.intent_resolver import IntentResolver
    from src.pipeline.target_resolver import TargetResolver
    from src.tool.grafana_tool import GrafanaTool
    from src.tool.knowledge_tool import KnowledgeTool
    from src.tool.target_registry import TargetRegistry
    from src.tool.target_store import TargetStore
    from src.tool.zabbix_tool import ZabbixTool

    store = TargetStore()
    registry = TargetRegistry(store=store)
    registry.register_tool(
        name="zabbix",
        tool=ZabbixTool(
            url="http://192.168.10.222/zabbix",
            token="7456fa347e17ce81f8f9d7429c8d4b8c2161b9fe62596d629ad390fdfb7e4eb7",
        ),
    )
    registry.register_tool(
        name="grafana",
        tool=GrafanaTool(),
    )
    kt = KnowledgeTool(target_registry=registry)

    engine = ExecutionEngine(
        intent_resolver=IntentResolver(),
        target_resolver=TargetResolver(),
        evidence_planner=EvidencePlanner(),
        capability_resolver=CapabilityResolver(),
        execution_planner=ExecutionPlanner(),
        graph_builder=ExecutionGraphBuilder(),
        knowledge_tool=kt,
        evidence_merge=EvidenceMerge(),
    )

    from src.agent.deterministic_agent import DeterministicAgent
    from src.model.mock_assessment_adapter import MockAssessmentAdapter

    return DeterministicAgent(
        execution_engine=engine,
        assessment_model=MockAssessmentAdapter(),
    )


def _build_legacy_runtime():
    """Build and return a legacy ReAct Agent for benchmark compatibility."""
    from src.agent.agent import Agent
    from src.model.mock_model_adapter import MockModelAdapter
    from src.tool.grafana_tool import GrafanaTool
    from src.tool.knowledge_tool import KnowledgeTool
    from src.tool.shell_tool import ShellTool
    from src.tool.target_registry import TargetRegistry
    from src.tool.target_store import TargetStore
    from src.tool.tool_registry import ToolRegistry
    from src.tool.zabbix_tool import ZabbixTool

    store = TargetStore()
    registry = TargetRegistry(store=store)
    registry.register_tool(
        name="zabbix",
        tool=ZabbixTool(
            url="http://192.168.10.222/zabbix",
            token="7456fa347e17ce81f8f9d7429c8d4b8c2161b9fe62596d629ad390fdfb7e4eb7",
        ),
    )
    registry.register_tool(
        name="grafana",
        tool=GrafanaTool(),
    )
    tool_registry = ToolRegistry()
    tool_registry.register(tool_id="shell", tool=ShellTool())
    tool_registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(target_registry=registry),
    )
    kt = KnowledgeTool(target_registry=registry)
    return Agent(
        model=MockModelAdapter(),
        tool_registry=tool_registry,
        available_resources=registry.target_names() and kt.get_available_resources(),
        capability_metadata=registry.target_names() and kt.get_capability_metadata(),
    )


def _run_benchmarks(
    domain: str | None,
    export_json: bool,
    use_legacy: bool = False,
) -> list[dict[str, Any]]:
    if use_legacy:
        agent = _build_legacy_runtime()
    else:
        agent = _build_deterministic_runtime()

    benchmarks = [b for b in BENCHMARKS if domain is None or b.domain == domain]

    results: list[dict[str, Any]] = []

    for bm in benchmarks:
        print(f"  [{bm.domain}] {bm.name}... ", end="", flush=True)
        try:
            import time

            t0 = time.perf_counter()
            response = agent.run(bm.request)
            elapsed = time.perf_counter() - t0
            errors: list[str] = []

            scores_dict = score(bm, [], 1, response, errors)
            results.append({
                "benchmark": bm.name,
                "domain": bm.domain,
                "request": bm.request,
                "response": response,
                "iterations": 1,
                "elapsed": round(elapsed, 3),
                "capability_sequence": [],
                "errors": errors,
                "scores": scores_dict,
                "exception": None,
            })
            total = scores_dict["total"]
            status = "PASS" if total >= 0.7 else "FAIL" if total < 0.4 else "WARN"
            print(f"{status} ({total:.2f})")
        except Exception as exc:
            print(f"ERROR: {exc}")
            results.append({
                "benchmark": bm.name,
                "domain": bm.domain,
                "request": bm.request,
                "response": "",
                "iterations": 0,
                "elapsed": 0,
                "capability_sequence": [],
                "errors": [str(exc)],
                "scores": {"total": 0, "reasoning": 0, "efficiency": 0, "evidence": 0, "safety": 0},
                "exception": str(exc),
            })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Agent Benchmark Suite")
    parser.add_argument(
        "--domain", type=str, default=None,
        help="Run only benchmarks for a specific domain"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Export report as JSON"
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Model name for comparison (not yet implemented)"
    )
    parser.add_argument(
        "--legacy", action="store_true",
        help="Use legacy ReAct runtime instead of deterministic pipeline"
    )
    args = parser.parse_args()

    runtime_label = "legacy ReAct" if args.legacy else "deterministic"
    print(f"\nBenchmark Suite ({runtime_label} runtime)")
    print("=" * 60)

    results = _run_benchmarks(args.domain, args.json, use_legacy=args.legacy)

    print()
    if args.json:
        print(generate_json_report(results))
    else:
        print(generate_human_report(results))

    if args.domain:
        all_in_domain = [b for b in BENCHMARKS if b.domain == args.domain]
        print(f"\nDomain '{args.domain}': {len(results)}/{len(all_in_domain)} executed")

    print("\nDone.")


if __name__ == "__main__":
    main()
