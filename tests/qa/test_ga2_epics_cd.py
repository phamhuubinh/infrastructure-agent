"""GA2-C07/C08/C10 + GA2-D07/D08/D09 deterministic regression coverage."""

from __future__ import annotations

from src.agent.session_investigation_context import (
    SessionContextResolver,
    SessionInvestigationContext,
)
from src.pipeline.multi_intent_planner import MultiIntentPlanner, StepKind
from src.pipeline.normalizer import Normalizer

# ---------------------------------------------------------------------------
# GA2-C08 — URL literal vs fetch intent
# ---------------------------------------------------------------------------


def test_url_literal_with_no_fetch_directive_is_not_a_fetch_instruction() -> None:
    """'đừng fetch URL' must win; URL is content, not an authorization."""
    frame = Normalizer().normalize(
        "Viết Dockerfile tải https://example.com/app.tar.gz nhưng đừng fetch URL."
    )
    assert frame.url_literal is True
    assert frame.explicit_url is None
    assert frame.request_domain.name == "CONTENT_GENERATION"
    assert frame.external_need.name == "NONE"


def test_url_fetch_request_keeps_explicit_url() -> None:
    frame = Normalizer().normalize("Đọc https://example.com và tóm tắt nội dung chính.")
    assert frame.url_literal is False
    assert frame.explicit_url == "https://example.com"
    assert frame.request_domain.name == "EXTERNAL_INFORMATION"


def test_relevant_english_no_fetch_directive() -> None:
    frame = Normalizer().normalize(
        "Write a config referencing https://example.com/app.tar.gz but do not fetch it."
    )
    assert frame.url_literal is True
    assert frame.explicit_url is None


# ---------------------------------------------------------------------------
# GA2-C07 — current information inside compound generation requests
# ---------------------------------------------------------------------------


def test_compound_generation_preserves_current_external_dependency() -> None:
    frame = Normalizer().normalize(
        "Tìm phiên bản Python mới nhất rồi viết Dockerfile dùng phiên bản đó."
    )
    assert frame.request_domain.name == "EXTERNAL_INFORMATION"
    assert frame.external_need.name == "REQUIRED"
    # The generation intent is preserved for the compound deliverable.
    assert frame.execution_intent.name == "GENERATE_CONTENT"
    assert frame.freshness_phrase == "mới nhất"


def test_plain_generation_without_current_dependency_stays_generation() -> None:
    frame = Normalizer().normalize(
        "Viết Dockerfile cài đặt Python và expose port 8000."
    )
    assert frame.request_domain.name == "CONTENT_GENERATION"
    assert frame.external_need.name == "NONE"


# ---------------------------------------------------------------------------
# GA2-C10 — ordered multi-intent planning
# ---------------------------------------------------------------------------


def test_explain_then_inspect_ordered_plan() -> None:
    planner = MultiIntentPlanner()
    frame = Normalizer().normalize(
        "Giải thích RAM là gì rồi kiểm tra RAM trên monitor."
    )
    plan = planner.plan(frame)
    assert plan is not None
    assert [step.kind for step in plan.steps] == [
        StepKind.EXPLAIN,
        StepKind.INSPECT,
    ]
    assert plan.steps[0].order == 1
    assert plan.steps[1].order == 2


def test_external_then_generate_preserves_dependency() -> None:
    planner = MultiIntentPlanner()
    frame = Normalizer().normalize(
        "Tìm phiên bản hiện tại rồi tạo config dùng phiên bản đó."
    )
    plan = planner.plan(frame)
    assert plan is not None
    assert plan.steps[1].kind is StepKind.GENERATE
    assert plan.steps[1].depends_on == (1,)


def test_comparison_is_not_treated_as_sequenced_plan() -> None:
    planner = MultiIntentPlanner()
    frame = Normalizer().normalize("So sánh CPU từ Grafana và Zabbix trên monitor.")
    assert planner.plan(frame) is None


# ---------------------------------------------------------------------------
# GA2-D07 — correction semantics
# ---------------------------------------------------------------------------


def test_correction_replaces_active_concept() -> None:
    assert SessionContextResolver.is_correction_request("Không phải CPU, RAM.") is True
    corrected = SessionContextResolver.corrected_concept("Không phải CPU, RAM.")
    assert corrected in {"cpu", "ram", "memory", "disk", "network", "service"}

    context = SessionInvestigationContext(active_concept="cpu")
    assert context.with_corrected_concept(corrected or "ram").active_concept == (
        corrected or "ram"
    )


def test_correction_does_not_union_concepts_in_resolver() -> None:
    ctx = SessionInvestigationContext(active_concept="memory")
    resolver = SessionContextResolver()
    frame = Normalizer().normalize("Không phải CPU, RAM.")
    resolved = resolver.resolve(frame, ctx)
    # The corrected concept replaces; both concepts never coexist.
    assert (
        resolved.concepts == ("cpu",)
        or resolved.concepts == ("ram",)
        or (resolved.concepts == ("memory",))
    )
    assert "concept_correction" in resolved.context_applied


# ---------------------------------------------------------------------------
# GA2-D08 — requested answer shape
# ---------------------------------------------------------------------------


def test_answer_shape_detection() -> None:
    assert SessionContextResolver.requested_answer_shape("ngắn thôi") == "SHORT"
    assert SessionContextResolver.requested_answer_shape("short answer") == "SHORT"
    assert SessionContextResolver.requested_answer_shape("raw data only") == "RAW"
    assert (
        SessionContextResolver.requested_answer_shape("giải thích câu trước")
        == "EXPLAIN_PREVIOUS"
    )


def test_answer_shape_persists_in_semantic_state() -> None:
    ctx = SessionInvestigationContext().with_answer_shape("SHORT")
    assert ctx.requested_answer_shape == "SHORT"
    assert ctx.to_dict()["requested_answer_shape"] == "SHORT"
    assert SessionInvestigationContext.from_dict(
        ctx.to_dict()
    ).requested_answer_shape == ("SHORT")


# ---------------------------------------------------------------------------
# GA2-D09 — vague referents
# ---------------------------------------------------------------------------


def test_vague_referent_detection() -> None:
    assert SessionContextResolver.is_vague_referent("máy kia") is True
    assert SessionContextResolver.is_vague_referent("server đó") is True
    assert SessionContextResolver.is_vague_referent("server kia") is True
    assert (
        SessionContextResolver.is_vague_referent("Kiểm tra CPU trên monitor") is False
    )


def test_vague_referent_never_inherits_implicit_target() -> None:
    resolver = SessionContextResolver()
    ctx = SessionInvestigationContext(active_target="monitor", active_concept="cpu")
    frame = Normalizer().normalize("Máy kia có ổn không?")
    resolved = resolver.resolve(frame, ctx)
    # No implicit localhost/target guess for a vague referent.
    assert resolved.target_raw is None
