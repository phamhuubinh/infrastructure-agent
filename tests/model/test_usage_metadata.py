from __future__ import annotations

from types import SimpleNamespace

from src.model.usage_metadata import (
    ModelCallUsage,
    normalize_anthropic_usage,
    normalize_openai_usage,
    normalize_usage_mapping,
)


class TestNormalizeOpenAIUsage:
    def test_reasoning_breakdown_splits_visible_output(self) -> None:
        usage = normalize_openai_usage(
            {
                "prompt_tokens": 120,
                "completion_tokens": 300,
                "completion_tokens_details": {"reasoning_tokens": 200},
            },
            model="deepseek-v4-pro",
            provider="openai",
            purpose="assessment",
            latency_ms=512.5,
        )

        assert usage.input_tokens == 120
        assert usage.reasoning_tokens == 200
        assert usage.visible_output_tokens == 100
        assert usage.total_output_tokens == 300
        assert usage.model == "deepseek-v4-pro"
        assert usage.provider == "openai"
        assert usage.purpose == "assessment"
        assert usage.latency_ms == 512.5

    def test_missing_reasoning_details_treat_total_as_visible(self) -> None:
        usage = normalize_openai_usage(
            {"prompt_tokens": 10, "completion_tokens": 50},
        )

        assert usage.input_tokens == 10
        assert usage.reasoning_tokens is None
        assert usage.visible_output_tokens == 50
        assert usage.total_output_tokens == 50

    def test_missing_usage_stays_explicitly_unknown(self) -> None:
        usage = normalize_openai_usage(
            None,
            model="m",
            provider="p",
            latency_ms=7.0,
        )

        assert usage.input_tokens is None
        assert usage.reasoning_tokens is None
        assert usage.visible_output_tokens is None
        assert usage.total_output_tokens is None
        assert usage.model == "m"
        assert usage.provider == "p"
        assert usage.latency_ms == 7.0

    def test_malformed_payload_is_unknown_not_zero(self) -> None:
        payloads: tuple[object, ...] = (
            "nope",
            [],
            {"prompt_tokens": "12"},
        )
        for payload in payloads:
            usage = normalize_openai_usage(payload)
            assert usage.input_tokens is None
            assert usage.total_output_tokens is None

    def test_bool_and_float_values_are_normalized(self) -> None:
        usage = normalize_openai_usage(
            {"prompt_tokens": True, "completion_tokens": 42.0},
        )

        assert usage.input_tokens is None
        assert usage.total_output_tokens == 42

    def test_reasoning_larger_than_total_clamps_visible_to_zero(self) -> None:
        usage = normalize_openai_usage(
            {
                "prompt_tokens": 5,
                "completion_tokens": 10,
                "completion_tokens_details": {"reasoning_tokens": 40},
            },
        )

        assert usage.visible_output_tokens == 0

    def test_to_dict_keeps_unknown_fields_null(self) -> None:
        assert ModelCallUsage().to_dict() == {
            "input_tokens": None,
            "estimated_input_tokens": None,
            "reasoning_tokens": None,
            "visible_output_tokens": None,
            "total_output_tokens": None,
            "model": None,
            "provider": None,
            "purpose": None,
            "latency_ms": None,
        }


class TestNormalizeAnthropicUsage:
    def _usage(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    def test_hidden_reasoning_keeps_visible_output_unknown(self) -> None:
        usage = normalize_anthropic_usage(
            self._usage(input_tokens=30, output_tokens=90),
            has_hidden_reasoning=True,
            model="claude-sonnet-5",
            latency_ms=12.3,
        )

        assert usage.input_tokens == 30
        assert usage.reasoning_tokens is None
        assert usage.visible_output_tokens is None
        assert usage.total_output_tokens == 90
        assert usage.model == "claude-sonnet-5"
        assert usage.provider == "anthropic"
        assert usage.latency_ms == 12.3

    def test_no_reasoning_blocks_treat_total_as_visible(self) -> None:
        usage = normalize_anthropic_usage(
            self._usage(input_tokens=8, output_tokens=21),
            has_hidden_reasoning=False,
        )

        assert usage.visible_output_tokens == 21

    def test_uninspected_content_keeps_visible_unknown(self) -> None:
        usage = normalize_anthropic_usage(
            self._usage(input_tokens=8, output_tokens=21),
        )

        assert usage.visible_output_tokens is None

    def test_missing_usage_stays_unknown(self) -> None:
        usage = normalize_anthropic_usage(None, has_hidden_reasoning=False)

        assert usage.input_tokens is None
        assert usage.total_output_tokens is None
        assert usage.visible_output_tokens is None


class TestNormalizeUsageMapping:
    def test_openai_style_mapping_keeps_the_visible_split(self) -> None:
        usage = normalize_usage_mapping(
            {
                "prompt_tokens": 11,
                "completion_tokens": 12,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
            purpose="planner",
        )

        assert usage.input_tokens == 11
        assert usage.reasoning_tokens == 3
        assert usage.visible_output_tokens == 9
        assert usage.total_output_tokens == 12
        assert usage.purpose == "planner"

    def test_anthropic_style_mapping_never_assumes_all_output_was_visible(self) -> None:
        """A raw usage mapping alone does not prove there was no hidden
        thinking content, so visible output must stay unknown."""
        usage = normalize_usage_mapping(
            {"input_tokens": 7, "output_tokens": 9},
            purpose="response",
            provider="anthropic",
        )

        assert usage.input_tokens == 7
        assert usage.total_output_tokens == 9
        assert usage.reasoning_tokens is None
        assert usage.visible_output_tokens is None
        assert usage.provider == "anthropic"

    def test_unknown_payload_keeps_every_token_field_unknown(self) -> None:
        usage = normalize_usage_mapping(None, purpose="planner")

        assert usage.input_tokens is None
        assert usage.reasoning_tokens is None
        assert usage.visible_output_tokens is None
        assert usage.total_output_tokens is None
        assert usage.purpose == "planner"
