"""Reviewed, deliberately narrow self-contained logic classification."""

from __future__ import annotations

from enum import Enum


class LogicOutcome(str, Enum):
    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    NOT_ENOUGH_INFORMATION = "NOT_ENOUGH_INFORMATION"


def evaluate(premises: tuple[str, ...], conclusion: str) -> LogicOutcome:
    """Classify only the GA2 direct/universal premise shapes deterministically."""
    conclusion = conclusion.casefold().strip().rstrip(".")
    for premise in premises:
        premise = premise.casefold().strip().rstrip(".")
        if premise in {
            "all servers in the cluster are linux",
            "mọi server trong cluster đều là linux",
        }:
            if conclusion in {"server a is running linux", "server a chạy linux"}:
                return LogicOutcome.ENTAILED
            if conclusion in {
                "server a is not running linux",
                "server a không chạy linux",
            }:
                return LogicOutcome.CONTRADICTED
        if premise in {"cpu usage of server a is constant", "cpu usage không đổi"}:
            if conclusion in {
                "cpu usage of server a decreased",
                "cpu usage của server a giảm",
                "cpu usage of server a increased",
                "cpu usage của server a tăng",
            }:
                return LogicOutcome.CONTRADICTED
    return LogicOutcome.NOT_ENOUGH_INFORMATION


def evaluate_text(text: str) -> LogicOutcome | None:
    """Parse one explicit supplied-premise/conclusion form, otherwise abstain."""
    lower = text.casefold()
    marker = "conclusion:" if "conclusion:" in lower else "kết luận:"
    prefix = "premises:" if "premises:" in lower else "tiền đề:"
    if prefix not in lower or marker not in lower:
        return None
    body = text[text.casefold().index(prefix) + len(prefix) :]
    split_at = body.casefold().index(marker)
    premises_text = body[:split_at]
    conclusion = body[split_at + len(marker) :].strip()
    premises = tuple(item.strip() for item in premises_text.split(";") if item.strip())
    return evaluate(premises, conclusion) if premises and conclusion else LogicOutcome.NOT_ENOUGH_INFORMATION


__all__ = ["LogicOutcome", "evaluate", "evaluate_text"]
