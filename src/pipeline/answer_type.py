from __future__ import annotations

from enum import Enum, auto

# Keywords that strongly indicate each answer type.
# Checked deterministically — no AI needed.
_FACT_KEYWORDS: frozenset[str] = frozenset(
    {
        "hostname",
        "tên máy",
        "kernel",
        "phiên bản",
        "uptime",
        "thời gian chạy",
        "zombie",
        "what is",
        "là bao nhiêu",
        "bao nhiêu",
    }
)
_LIST_KEYWORDS: frozenset[str] = frozenset(
    {
        "list",
        "danh sách",
        "liệt kê",
        "all",
        "tất cả",
        "các",
        "những",
        "mọi",
        "top",
        "top 5",
        "top 10",
    }
)
_TABLE_KEYWORDS: frozenset[str] = frozenset(
    {
        "table",
        "bảng",
    }
)
_CHART_KEYWORDS: frozenset[str] = frozenset(
    {
        "chart",
        "graph",
        "plot",
        "biểu đồ",
        "đồ thị",
        "visualize",
        "trực quan",
    }
)
_COMPARISON_KEYWORDS: frozenset[str] = frozenset(
    {
        "compare",
        "diff",
        "versus",
        "vs",
        "so sánh",
        "khác biệt",
        "difference",
    }
)
_ASSESSMENT_KEYWORDS: frozenset[str] = frozenset(
    {
        "assess",
        "analyze",
        "diagnose",
        "troubleshoot",
        "investigate",
        "đánh giá",
        "phân tích",
        "chuẩn đoán",
        "điều tra",
        "kiểm tra",
        "như thế nào",
        "how is",
        "how are",
        "tại sao",
        "why",
    }
)


class AnswerType(Enum):
    """Expected answer format for a user request.

    Determines which response path to use:
    - FACT → deterministic responder (no LLM)
    - LIST → deterministic + table formatting
    - TABLE → formatted table output
    - CHART → Grafana embed/image
    - COMPARISON → comparison assessment
    - ASSESSMENT → full LLM pipeline
    """

    FACT = auto()
    LIST = auto()
    TABLE = auto()
    CHART = auto()
    COMPARISON = auto()
    ASSESSMENT = auto()


class AnswerTypeClassifier:
    """Classify user requests into the expected answer type.

    Purely deterministic — uses keyword matching against known patterns.
    No AI reasoning involved.
    """

    def classify(self, raw_request: str) -> AnswerType:
        """Determine the expected answer format for a user request.

        Priority order (highest wins):
        1. CHART — explicit visualization request
        2. TABLE — explicit table/compare request
        3. COMPARISON — diff/vs request
        4. LIST — explicit list/top request
        5. FACT — simple single-value question
        6. ASSESSMENT — default fallback for everything else

        Args:
            raw_request: The raw user request string.

        Returns:
            The determined AnswerType.
        """
        lower = raw_request.lower()

        # Check in priority order. Each check returns immediately on match
        # because Chart > Table > Comparison > List > Fact > Assessment.

        if self._match_any(lower, _CHART_KEYWORDS):
            return AnswerType.CHART

        if self._match_any(lower, _COMPARISON_KEYWORDS):
            return AnswerType.COMPARISON

        if self._match_any(lower, _TABLE_KEYWORDS):
            return AnswerType.TABLE

        if self._match_any(lower, _LIST_KEYWORDS):
            return AnswerType.LIST

        if self._match_any(lower, _FACT_KEYWORDS):
            return AnswerType.FACT

        if self._match_any(lower, _ASSESSMENT_KEYWORDS):
            return AnswerType.ASSESSMENT

        # Default: assessment — when nothing specific is detected.
        return AnswerType.ASSESSMENT

    @staticmethod
    def _match_any(text: str, keywords: frozenset[str]) -> bool:
        """Check if any keyword appears in the text."""
        return any(kw in text for kw in keywords)
