from datetime import datetime, timezone

from src.pipeline.normalizer import Normalizer
from src.pipeline.parameter_extractor import ParameterExtractor
from src.pipeline.request_semantics import (
    ExecutionIntent,
    ExternalNeed,
    InformationScope,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.time_range_resolver import TemporalRequirement, TimeRangeResolver


def test_conceptual_technical_question_is_stable_general_knowledge() -> None:
    frame = Normalizer().normalize("RAM và swap khác nhau thế nào?")

    assert frame.request_domain is RequestDomain.GENERAL
    assert frame.information_scope is InformationScope.STABLE_KNOWLEDGE
    assert frame.external_need is ExternalNeed.NONE
    assert frame.execution_intent is ExecutionIntent.EXPLAIN


def test_live_environment_question_is_not_misclassified_as_general_knowledge() -> None:
    frame = Normalizer().normalize("RAM máy này đang dùng bao nhiêu?")

    assert frame.request_domain is RequestDomain.ENVIRONMENT
    assert frame.information_scope is InformationScope.LIVE_ENVIRONMENT
    assert frame.execution_intent is ExecutionIntent.INSPECT_READ_ONLY


def test_current_hostname_remains_a_live_environment_question() -> None:
    frame = Normalizer().normalize("Hostname hiện tại là gì?")

    assert frame.request_domain is RequestDomain.ENVIRONMENT
    assert frame.information_scope is InformationScope.LIVE_ENVIRONMENT


def test_current_external_question_requires_verification() -> None:
    frame = Normalizer().normalize("Phiên bản Python stable mới nhất hiện tại là gì?")

    assert frame.request_domain is RequestDomain.EXTERNAL_INFORMATION
    assert frame.information_scope is InformationScope.CURRENT_EXTERNAL
    assert frame.external_need is ExternalNeed.REQUIRED
    assert frame.freshness_window == "release_current"


def test_tomorrow_weather_and_current_market_index_require_verification() -> None:
    tomorrow = Normalizer().normalize("Thời tiết Hà Nội ngày mai thế nào?")
    index = Normalizer().normalize("S&P 500 current value?")

    assert tomorrow.external_need is ExternalNeed.REQUIRED
    assert index.external_need is ExternalNeed.REQUIRED


def test_identity_meta_and_supplied_calculation_are_general_not_environment() -> None:
    identity = Normalizer().normalize("Bạn dựa trên model nào?")
    calculation = Normalizer().normalize(
        "Một server có 64 GB RAM, đang dùng 18 GB. Còn lại bao nhiêu GB?"
    )

    assert identity.request_domain is RequestDomain.GENERAL
    assert calculation.request_domain is RequestDomain.GENERAL


def test_external_fact_subject_is_never_kept_as_an_environment_target() -> None:
    frame = Normalizer().normalize("CEO hiện tại của Microsoft là ai?")

    assert frame.request_domain is RequestDomain.EXTERNAL_INFORMATION
    assert frame.target_raw is None


def test_explicit_online_verification_is_not_keyword_tool_selection() -> None:
    frame = Normalizer().normalize("Hãy kiểm tra trên Internet CEO của Microsoft là ai.")

    assert frame.request_domain is RequestDomain.EXTERNAL_INFORMATION
    assert frame.external_need is ExternalNeed.EXPLICIT


def test_public_url_is_typed_independently_from_generic_web_search() -> None:
    frame = Normalizer().normalize("Đọc https://docs.python.org/3/ và tóm tắt.")

    assert frame.information_scope is InformationScope.EXPLICIT_URL
    assert frame.external_need is ExternalNeed.URL
    assert frame.source_constraints == (SourceConstraint.URL_ONLY,)
    assert frame.explicit_url == "https://docs.python.org/3/"
    assert frame.url_error is None


def test_malformed_url_is_a_typed_validation_problem() -> None:
    frame = Normalizer().normalize("Đọc https:// rồi tóm tắt.")

    assert frame.information_scope is InformationScope.EXPLICIT_URL
    assert frame.explicit_url is None
    assert frame.url_error == "Malformed HTTP/HTTPS URL."


def test_source_constraints_preserve_single_source_and_negative_directive() -> None:
    frame = Normalizer().normalize(
        "Chỉ dùng Grafana để lấy CPU; không dùng Internet."
    )

    assert frame.source_constraints == (
        SourceConstraint.GRAFANA,
        SourceConstraint.NO_INTERNET,
    )
    assert frame.excluded_sources == (SourceConstraint.INTERNET,)


def test_equivalent_only_wording_is_a_hard_typed_source_constraint() -> None:
    frame = Normalizer().normalize("Use only Grafana to inspect CPU.")

    assert frame.source_constraints == (SourceConstraint.GRAFANA,)


def test_url_does_not_erase_no_internet_constraint() -> None:
    frame = Normalizer().normalize("Đọc https://example.com nhưng không dùng Internet.")

    assert frame.source_constraints == (
        SourceConstraint.URL_ONLY,
        SourceConstraint.NO_INTERNET,
    )


def test_conflicting_source_directives_are_a_routing_ambiguity() -> None:
    frame = Normalizer().normalize("Chỉ dùng Grafana, nhưng không dùng Grafana.")

    assert "source" in frame.ambiguity


def test_multi_source_comparison_is_a_bounded_allow_set() -> None:
    frame = Normalizer().normalize("So sánh CPU từ Grafana và Zabbix.")

    assert frame.source_constraints == (
        SourceConstraint.GRAFANA,
        SourceConstraint.ZABBIX,
    )


def test_generated_command_is_content_not_environment_mutation() -> None:
    frame = Normalizer().normalize("Viết lệnh restart nginx nhưng không chạy lệnh.")

    assert frame.request_domain is RequestDomain.CONTENT_GENERATION
    assert frame.execution_intent is ExecutionIntent.GENERATE_CONTENT


def test_imperative_restart_is_still_a_mutating_action() -> None:
    frame = Normalizer().normalize("Restart nginx ngay bây giờ.")

    assert frame.request_domain is RequestDomain.ACTION
    assert frame.execution_intent is ExecutionIntent.MUTATE_ENVIRONMENT


def test_descriptive_reboot_word_is_read_only_inspection() -> None:
    frame = Normalizer().normalize("Lần reboot gần nhất khi nào?")

    assert frame.request_domain is RequestDomain.ENVIRONMENT
    assert frame.execution_intent is ExecutionIntent.INSPECT_READ_ONLY


def test_frame_trace_serializes_v2_semantics() -> None:
    serialized = Normalizer().normalize("Giá Bitcoin hiện tại?").to_dict()

    assert serialized["request_domain"] == "EXTERNAL_INFORMATION"
    assert serialized["information_scope"] == "CURRENT_EXTERNAL"
    assert serialized["external_need"] == "REQUIRED"
    assert serialized["source_constraints"] == ["ANY"]


def test_all_scope_and_future_ranges_are_bound_without_clarification() -> None:
    params = ParameterExtractor().extract("Forecast all services next quarter")
    timeframe = TimeRangeResolver().resolve(
        "Forecast all services next quarter",
        now=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
    )

    assert params.scope == "all"
    assert params.time_range == "next_quarter"
    assert timeframe is not None
    assert timeframe.source_phrase == "next_quarter"
    assert timeframe.requirement is TemporalRequirement.FORECAST


def test_next_month_is_a_bounded_future_timeframe() -> None:
    timeframe = TimeRangeResolver().resolve(
        "Dự báo CPU tháng tới",
        now=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
    )

    assert timeframe is not None
    assert timeframe.source_phrase == "next_month"
    assert timeframe.requirement is TemporalRequirement.FORECAST
