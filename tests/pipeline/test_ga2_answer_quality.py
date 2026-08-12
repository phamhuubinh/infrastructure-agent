"""GA2-H06/H07/H08/H12: deterministic config validation + repetition detection."""

from __future__ import annotations

from src.pipeline.config_validator import ConfigValidator
from src.pipeline.repetition_detector import RepetitionDetector

# ---------------------------------------------------------------------------
# GA2-H07 — GitHub Actions/YAML validation
# ---------------------------------------------------------------------------


def test_valid_github_actions_workflow() -> None:
    workflow = """
name: CI
on:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run test
        run: pytest
"""
    result = ConfigValidator.validate("github_actions", workflow)
    assert result.valid is True


def test_invalid_schedule_syntax_rejected() -> None:
    workflow = """
name: CI
on:
  schedule:
    - cron: '0 * * * * * *'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
    result = ConfigValidator.validate("github_actions", workflow)
    assert result.valid is False
    assert any("cron" in issue.message for issue in result.issues)


def test_nonexistent_step_output_rejected() -> None:
    workflow = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
      - run: echo ${{ steps.setup.outputs.python-version }}
"""
    result = ConfigValidator.validate("github_actions", workflow)
    assert result.valid is False
    assert any("nonexistent output" in issue.message for issue in result.issues)


def test_invalid_yaml_rejected() -> None:
    result = ConfigValidator.validate("github_actions", "name: [unclosed")
    assert result.valid is False


def test_valid_matrix_workflow_passes() -> None:
    workflow = """
name: matrix CI
on: [push]
jobs:
  matrix-test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python: ['3.12', '3.13']
    steps:
      - run: python --version
"""
    assert ConfigValidator.validate("github_actions", workflow).valid is True


def test_matrix_named_job_without_strategy_matrix_is_rejected() -> None:
    workflow = """
name: CI
on: [push]
jobs:
  matrix-test:
    runs-on: ubuntu-latest
    steps:
      - name: Test Python 3.12 then Python 3.13 sequentially
        run: pytest
"""
    result = ConfigValidator.validate("github_actions", workflow)
    assert result.valid is False
    assert any("claims a matrix" in issue.message for issue in result.issues)


def test_duplicate_job_key_is_rejected_before_yaml_overwrite() -> None:
    workflow = """
name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps: [{run: pytest}]
  test:
    runs-on: macos-latest
    steps: [{run: pytest}]
"""
    result = ConfigValidator.validate("github_actions", workflow)
    assert result.valid is False
    assert any("Duplicate YAML key 'test'" in issue.message for issue in result.issues)


def test_contradictory_reusable_workflow_job_is_rejected() -> None:
    workflow = """
name: CI
on: [push]
jobs:
  call:
    uses: org/repo/.github/workflows/reusable.yml@main
    runs-on: ubuntu-latest
    steps: [{run: pytest}]
"""
    result = ConfigValidator.validate("github_actions", workflow)
    assert result.valid is False
    assert any("mixes reusable" in issue.message for issue in result.issues)


def test_malformed_jobs_and_steps_are_rejected() -> None:
    jobs_result = ConfigValidator.validate("github_actions", "name: CI\njobs: []")
    steps_result = ConfigValidator.validate(
        "github_actions",
        "name: CI\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps: echo hi",
    )
    assert jobs_result.valid is False
    assert steps_result.valid is False


# ---------------------------------------------------------------------------
# GA2-H08 — Shell syntax validation
# ---------------------------------------------------------------------------


def test_valid_shell_passes_without_execution() -> None:
    result = ConfigValidator.validate("shell", "echo hello\nls -la /tmp")
    assert result.valid is True


def test_malformed_shell_detected() -> None:
    result = ConfigValidator.validate("shell", "echo 'unclosed")
    assert result.valid is False


def test_malformed_shell_conditional_and_pipeline_detected() -> None:
    conditional = ConfigValidator.validate("shell", "if true; then\n  echo ok\n")
    pipeline = ConfigValidator.validate("shell", "printf ok |")
    assert conditional.valid is False
    assert pipeline.valid is False


def test_valid_multiline_shell_is_parse_checked_without_execution() -> None:
    result = ConfigValidator.validate(
        "shell",
        "if printf '%s\\n' ok | grep -q ok; then\n  echo passed\nfi",
    )
    assert result.valid is True


def test_mutating_shell_warns_but_is_not_executed() -> None:
    result = ConfigValidator.validate("shell", "rm -rf /tmp/x\nsystemctl stop nginx")
    assert result.valid is True  # syntax is fine
    assert any(issue.kind == "warning" for issue in result.issues)


# ---------------------------------------------------------------------------
# GA2-H12 — Repetition/degeneration detector
# ---------------------------------------------------------------------------


def test_repeated_sentence_detected_and_truncated() -> None:
    text = (
        "Kết quả CPU ổn định.\n" * 6
        + "Kết quả kiểm tra ban đầu cho thấy hệ thống hoạt động bình thường."
    )
    result = RepetitionDetector.detect(text)
    assert result.pathological is True
    assert any(f.kind == "repeated_sentence" for f in result.findings)
    assert result.recovered_text == "Kết quả CPU ổn định."


def test_normal_output_not_pathological() -> None:
    text = (
        "Hệ thống đang chạy ổn định. CPU sử dụng 40%. RAM dùng 60%. "
        "Disk còn 80% trống. Không phát hiện sự cố nghiêm trọng nào trong "
        "phạm vi bằng chứng đã thu thập."
    )
    result = RepetitionDetector.detect(text)
    assert result.pathological is False


def test_looping_fragment_detected() -> None:
    text = "lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi lỗi"
    result = RepetitionDetector.detect(text)
    assert result.pathological is True
    assert any(
        f.kind in {"looping_fragment", "repeated_sentence"} for f in result.findings
    )


def test_empty_and_short_output_not_pathological() -> None:
    assert RepetitionDetector.detect("").pathological is False
    assert RepetitionDetector.detect("ngắn").pathological is False
