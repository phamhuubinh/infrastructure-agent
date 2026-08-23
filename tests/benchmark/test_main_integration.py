"""Integration coverage for the canonical benchmark CLI."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from benchmark.__main__ import main


class FakeCanonicalAgent:
    def run_with_steps(
        self,
        request: str,
    ) -> dict[str, object]:
        del request

        return {
            "response": (
                "Summary Assessment Risks "
                "Recommendations CPU Memory "
                "Disk Services."
            ),
            "steps": [],
            "execution_trace": {
                "runtime_metrics": {
                    "canonical_runtime": {
                        "model_calls": 1,
                        "action_attempts": 0,
                    }
                }
            },
        }


def _run_json(
    tmp_path: Path,
) -> dict[str, object]:
    output = StringIO()

    metadata = {
        "model": "fixture-model",
        "server": "fixture-server",
        "provider": "fixture",
        "captured_at": 1,
    }

    with (
        mock.patch(
            "benchmark.__main__."
            "create_canonical_session_agent",
            return_value=(
                FakeCanonicalAgent()
            ),
        ),
        mock.patch(
            "benchmark.__main__."
            "collect_benchmark_metadata",
            return_value=metadata,
        ),
        mock.patch(
            "benchmark.__main__."
            "_timestamped_log_path",
            return_value=(
                tmp_path
                / "benchmark.log"
            ),
        ),
        redirect_stdout(output),
    ):
        main(
            [
                "--domain",
                "assessment",
                "--json",
            ]
        )

    rendered = output.getvalue()

    start = rendered.find("{")
    end = rendered.rfind("}") + 1

    assert start >= 0
    assert end > start

    value = json.loads(
        rendered[start:end]
    )

    assert isinstance(
        value,
        dict,
    )

    return value


def test_main_json_output_contains_benchmark_metadata(
    tmp_path: Path,
) -> None:
    data = _run_json(
        tmp_path
    )

    assert "benchmark" in data

    metadata = data["benchmark"]

    assert isinstance(
        metadata,
        dict,
    )

    assert metadata["model"] == (
        "fixture-model"
    )
    assert metadata["server"] == (
        "fixture-server"
    )
    assert metadata["captured_at"] == 1


def test_main_json_structure(
    tmp_path: Path,
) -> None:
    data = _run_json(
        tmp_path
    )

    assert "overall" in data
    assert "domain_scores" in data
    assert "scenarios" in data
    assert "results" in data
    assert len(data["results"]) == 4
    assert "benchmark" in data
