"""Regression contracts for the GA1 revised smoke and external QA sets."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "scripts" / "qa" / "orion_qa_runner.py"
CASES = PROJECT_ROOT / "tests" / "qa" / "cases"


def _default_questions() -> list[str]:
    module = ast.parse(RUNNER.read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_QUESTIONS"
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        assert isinstance(value, list)
        assert all(isinstance(question, str) for question in value)
        return value
    raise AssertionError("DEFAULT_QUESTIONS assignment not found")


def _questions(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_default_general_agent_smoke_matrix_has_exactly_193_unique_questions() -> None:
    questions = _default_questions()

    assert len(questions) == 193
    assert len(questions) == len(set(questions))
    assert all("\n" not in question for question in questions)


def test_external_suites_preserve_historic_case_counts_and_one_line_contract() -> None:
    expected = {
        "cauhoi_kiemtra_v2.txt": 66,
        "cauhoi_phanb.txt": 28,
        "cauhoi_v4_adversarial.txt": 61,
        "cauhoi_v5_workflow.txt": 38,
    }

    observed = {name: _questions(CASES / name) for name in expected}

    assert {name: len(questions) for name, questions in observed.items()} == expected
    assert sum(len(questions) for questions in observed.values()) == 193
    assert all(
        question and "\n" not in question
        for questions in observed.values()
        for question in questions
    )


def test_smoke_and_external_suites_are_not_a_copy_of_each_other() -> None:
    defaults = set(_default_questions())
    external = {
        question
        for path in CASES.glob("cauhoi_*.txt")
        for question in _questions(path)
    }

    assert external - defaults
    assert defaults - external
