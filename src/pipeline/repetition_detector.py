"""GA2-H12: pathological repetition/degeneration detection for final output.

Before final output, detect obvious pathological repetition such as:

- same sentence/paragraph repeated many times,
- looping fragments,
- large duplicated blocks.

The detector safely truncates to a useful non-repeated prefix when possible
and never exposes hidden reasoning while recovering.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepetitionFinding:
    kind: str  # repeated_sentence | repeated_paragraph | looping_fragment
    count: int
    span: str = ""


@dataclass(frozen=True, slots=True)
class RepetitionResult:
    pathological: bool
    findings: tuple[RepetitionFinding, ...] = ()
    recovered_text: str | None = None


class RepetitionDetector:
    """Deterministic detector for pathological output repetition."""

    _MIN_SENTENCE_REPEATS = 4
    _MIN_PARAGRAPH_REPEATS = 3
    _MIN_FRAGMENT_REPEATS = 6
    _MIN_FRAGMENT_LENGTH = 12

    @classmethod
    def detect(cls, text: str) -> RepetitionResult:
        if not text or len(text) < 40:
            return RepetitionResult(False)

        findings: list[RepetitionFinding] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1. Repeated identical non-trivial lines (sentences/paragraphs).
        counts: dict[str, int] = {}
        for line in lines:
            if len(line) >= 8:
                counts[line] = counts.get(line, 0) + 1

        prefix_lines: list[str] = []
        seen_once: set[str] = set()
        for line in lines:
            count = counts.get(line, 0)
            if count >= cls._MIN_SENTENCE_REPEATS and len(line) >= 8:
                findings.append(
                    RepetitionFinding("repeated_sentence", count, line[:100])
                )
            if line in seen_once:
                # Stop at the first repeated sentence; recover the prefix.
                break
            seen_once.add(line)
            prefix_lines.append(line)

        # 2. Paragraph-level duplication (multi-line block repeated).
        blocks = cls._paragraphs(lines)
        block_counts: dict[str, int] = {}
        for block in blocks:
            if len(block) >= 40:
                block_counts[block] = block_counts.get(block, 0) + 1
        for block, count in block_counts.items():
            if count >= cls._MIN_PARAGRAPH_REPEATS:
                findings.append(
                    RepetitionFinding("repeated_paragraph", count, block[:100])
                )

        # 3. Looping fragment (same short token repeated).
        fragments = cls._looping_fragments(text)
        for fragment, count in fragments.items():
            if count >= cls._MIN_FRAGMENT_REPEATS:
                findings.append(RepetitionFinding("looping_fragment", count, fragment))

        if not findings:
            return RepetitionResult(False)

        pathological = any(
            finding.count >= cls._MIN_SENTENCE_REPEATS
            or finding.count >= cls._MIN_PARAGRAPH_REPEATS
            for finding in findings
        )
        recovered = "\n".join(prefix_lines) if prefix_lines else None
        return RepetitionResult(
            pathological=pathological,
            findings=tuple(findings),
            recovered_text=recovered,
        )

    @staticmethod
    def _paragraphs(lines: list[str]) -> list[str]:
        groups: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if not line:
                if current:
                    groups.append(current)
                    current = []
                continue
            current.append(line)
        if current:
            groups.append(current)
        return ["\n".join(group) for group in groups if group]

    @staticmethod
    def _looping_fragments(text: str) -> dict[str, int]:
        """Detect a short fragment repeated back-to-back many times."""
        fragments: dict[str, int] = {}
        for window in (8, 12, 16):
            for i in range(len(text) - window):
                fragment = text[i : i + window]
                if not fragment.strip():
                    continue
                # Consecutive repeats.
                count = 1
                j = i + window
                while text[j : j + window] == fragment:
                    count += 1
                    j += window
                if count >= 3:
                    fragments[fragment] = max(fragments.get(fragment, 0), count)
        return fragments


__all__ = ["RepetitionDetector", "RepetitionResult"]
