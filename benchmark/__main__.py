from __future__ import annotations

import argparse
import sys
from typing import Any

from benchmark.dataset import BENCHMARKS, Benchmark
from benchmark.report import generate_human_report, generate_json_report
from benchmark.scoring import score


def _mock_model_run(request: str) -> str:
    """
    Mock agent execution for benchmark testing.
    In production this would call the real Agent.
    """
    from src.shared.discovery.observation import Observation
    from src.shared.reasoning.action import Action
    from src.shared.reasoning.final_response import FinalResponse
    from src.agent.agent import Agent
    from src.model.mock_model_adapter import MockModelAdapter
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
    tool_registry = ToolRegistry()
    tool_registry.register(tool_id="shell", tool=ShellTool())
    tool_registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(target_registry=registry),
    )
    agent = Agent(
        model=MockModelAdapter(),
        tool_registry=tool_registry,
        available_resources=registry.target_names()
        and KnowledgeTool(target_registry=registry).get_available_resources(),
    )
    return agent.run(request)


def _run_benchmarks(
    domain: str | None,
    export_json: bool,
) -> list[dict[str, Any]]:
    benchmarks = [b for b in BENCHMARKS if domain is None or b.domain == domain]

    results: list[dict[str, Any]] = []

    for bm in benchmarks:
        print(f"  [{bm.domain}] {bm.name}... ", end="", flush=True)
        try:
            import time
            t0 = time.perf_counter()
            response = _mock_model_run(bm.request)
            elapsed = time.perf_counter() - t0
            iterations = 0
            cap_sequence: list[str] = []
            errors: list[str] = []

            import json as _json
            try:
                action_or_final = _json.loads(response) if isinstance(response, str) else None
            except Exception:
                pass

            scores_dict = score(bm, cap_sequence, iterations, response, errors)
            results.append({
                "benchmark": bm.name,
                "domain": bm.domain,
                "request": bm.request,
                "response": response,
                "iterations": iterations,
                "elapsed": round(elapsed, 3),
                "capability_sequence": cap_sequence,
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
        choices=["linux", "remote", "zabbix", "safety", "generic"],
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
    args = parser.parse_args()

    print("\nBenchmark Suite")
    print("=" * 60)

    results = _run_benchmarks(args.domain, args.json)

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
