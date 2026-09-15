"""Run Orion's reusable model-context benchmark suite.

Default mode is deterministic and network-free. ``--live`` uses the application's
active persisted model profile with synthetic tool fixtures, not live infrastructure
evidence. Use targeted_live_validation.py for the small real-runtime validation set.
"""

from __future__ import annotations

import argparse
import asyncio

from orion.benchmarks.model_context import run_live_benchmark, run_offline_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure Orion model-context regression fixtures.")
    parser.add_argument(
        "--live", action="store_true", help="Run the persisted-profile provider with fixture tools."
    )
    parser.add_argument(
        "--json", action="store_true", help="Print stable JSON instead of a text table."
    )
    args = parser.parse_args()
    report = asyncio.run(run_live_benchmark() if args.live else run_offline_benchmark())
    print(report.to_json() if args.json else report.to_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
