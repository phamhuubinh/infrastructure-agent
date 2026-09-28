"""Deterministic, controllable test adapter. It never claims language understanding."""

from __future__ import annotations

from orion.embeddings import EmbeddingProfile, Vector, validate_vector


class FakeEmbeddingPort:
    def __init__(
        self,
        profile: EmbeddingProfile,
        *,
        passages: dict[str, Vector],
        queries: dict[str, Vector],
        fail_passage_call: int | None = None,
    ) -> None:
        self._profile = profile
        self._passages = passages
        self._queries = queries
        self._fail_passage_call = fail_passage_call
        self.passage_batches: list[tuple[str, ...]] = []
        self.query_batches: list[tuple[str, ...]] = []

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    @property
    def dimension(self) -> int:
        return self._profile.dimension

    @property
    def maximum_input_tokens(self) -> int | None:
        return 512

    def embed_passages(self, texts: tuple[str, ...]) -> tuple[Vector, ...]:
        self.passage_batches.append(texts)
        if self._fail_passage_call == len(self.passage_batches):
            raise RuntimeError("simulated embedding interruption")
        return tuple(validate_vector(self._passages[text], self.dimension) for text in texts)

    def embed_queries(self, texts: tuple[str, ...]) -> tuple[Vector, ...]:
        self.query_batches.append(texts)
        return tuple(validate_vector(self._queries[text], self.dimension) for text in texts)
