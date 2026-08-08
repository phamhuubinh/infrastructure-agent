"""GA2-E08: deterministic provenance answering from session/evidence metadata.

Questions such as "Nguồn dữ liệu nào vừa được dùng?" or "Did you use Grafana
or SSH?" are answered from the structured session/evidence metadata, never by
asking the model to guess from prose.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.request_semantics import SourceConstraint


@dataclass(frozen=True, slots=True)
class ProvenanceAnswer:
    sources: tuple[str, ...]
    target: str | None = None
    concepts: tuple[str, ...] = ()
    relevant_facts: tuple[str, ...] = ()

    def render(self, lang: str = "vi") -> str:
        if not self.sources:
            if lang == "en":
                return "No investigation evidence has been used in this session yet."
            return "Chưa có bằng chứng điều tra nào được dùng trong phiên này."
        source_labels = ", ".join(sorted(self.sources))
        target_label = f" trên {self.target}" if self.target else ""
        if lang == "en":
            base = (
                f"The most recent evidence sources used{target_label}: "
                f"{source_labels}."
            )
        else:
            base = (
                f"Các nguồn dữ liệu vừa được dùng{target_label}: " f"{source_labels}."
            )
        if self.relevant_facts:
            facts = ", ".join(sorted(self.relevant_facts)[:10])
            return f"{base} Bằng chứng liên quan: {facts}."
        return base


class ProvenanceResponder:
    """Render deterministic answers to provenance questions from metadata."""

    _PROVENANCE_MARKERS = (
        "nguồn dữ liệu nào",
        "nguon du lieu nao",
        "lấy số liệu từ đâu",
        "lay so lieu tu dau",
        "số liệu từ đâu",
        "did you use",
        "which source",
        "what source",
        "where did the data come from",
        "where did you get",
        "data source used",
    )

    @classmethod
    def is_provenance_question(cls, raw_request: str) -> bool:
        lower = raw_request.casefold()
        return any(marker in lower for marker in cls._PROVENANCE_MARKERS)

    def respond(
        self,
        answer: ProvenanceAnswer,
        lang: str = "vi",
    ) -> str:
        return answer.render(lang=lang)

    @classmethod
    def sources_from_constraints(
        cls,
        constraints: tuple[SourceConstraint, ...],
    ) -> tuple[str, ...]:
        label = {
            SourceConstraint.LINUX: "Linux",
            SourceConstraint.SSH: "SSH",
            SourceConstraint.GRAFANA: "Grafana",
            SourceConstraint.ZABBIX: "Zabbix",
            SourceConstraint.INTERNET: "Internet",
            SourceConstraint.URL_ONLY: "URL",
        }
        return tuple(
            dict.fromkeys(label[item] for item in constraints if item in label)
        )


__all__ = [
    "ProvenanceAnswer",
    "ProvenanceResponder",
]
