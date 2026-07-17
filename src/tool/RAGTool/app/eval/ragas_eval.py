"""Ragas evaluation (github.com/explodinggpt/ragas — retrieval-augmented
generation assessment). Requires `pip install ragas datasets`. Computes
the standard RAG metrics: faithfulness (is the answer grounded in the
retrieved context), answer_relevancy, context_precision, context_recall.

Use this offline against a labeled eval set (question, ground_truth,
contexts, answer) — not per production request; it makes its own LLM
calls to judge faithfulness/relevancy, so it's for CI/regression testing
of the pipeline (mirrors the "benchmark-driven development" rule already
in this project's docs/ai/07_DEVELOPMENT_RULES.md).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RagasEvalCase:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None


class RagasEvaluator:
    def __init__(self, llm=None, embeddings=None) -> None:
        """llm/embeddings: ragas-wrapped model clients (LangchainLLMWrapper
        etc.) — pass None to use Ragas' default OpenAI-based judge, which
        requires OPENAI_API_KEY, or wrap your own OpenAI-compatible
        endpoint (vLLM) via ragas.llms.LangchainLLMWrapper."""
        self._llm = llm
        self._embeddings = embeddings

    def evaluate(self, cases: list[RagasEvalCase]) -> dict:
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import (
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )
        except ImportError as exc:
            msg = "ragas is not installed (`pip install ragas datasets`)"
            raise RuntimeError(msg) from exc

        data = {
            "question": [c.question for c in cases],
            "answer": [c.answer for c in cases],
            "contexts": [c.contexts for c in cases],
        }
        metrics = [faithfulness, answer_relevancy, context_precision]
        if all(c.ground_truth for c in cases):
            data["ground_truth"] = [c.ground_truth for c in cases]
            metrics.append(context_recall)

        dataset = Dataset.from_dict(data)
        kwargs = {}
        if self._llm is not None:
            kwargs["llm"] = self._llm
        if self._embeddings is not None:
            kwargs["embeddings"] = self._embeddings

        result = evaluate(dataset, metrics=metrics, **kwargs)
        return result.to_pandas().mean(numeric_only=True).to_dict()
