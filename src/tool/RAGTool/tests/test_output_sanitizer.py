from app.serving.output_sanitizer import sanitize_model_output


def test_removes_reasoning_blocks_from_analysis_output() -> None:
    raw = "<think>private reasoning</think>\nFinal analysis"
    assert sanitize_model_output(raw) == "Final analysis"


def test_preserves_normal_analysis_output() -> None:
    assert sanitize_model_output("System is healthy.") == "System is healthy."
