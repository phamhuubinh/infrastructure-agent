"""Provider-neutral dense embedding identity, validation, and storage encoding."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass

type Vector = tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingProfile:
    implementation: str
    model: str
    revision: str
    artifact_digest: str
    tokenizer_digest: str | None
    precision: str
    dimension: int
    pooling: str
    normalization: str
    query_prefix: str
    passage_prefix: str
    windowing_version: str
    maximum_input_tokens: int | None

    def __post_init__(self) -> None:
        if type(self.dimension) is not int or self.dimension <= 0:
            raise ValueError("Embedding dimension must be positive")
        if self.maximum_input_tokens is not None and (
            type(self.maximum_input_tokens) is not int or self.maximum_input_tokens <= 0
        ):
            raise ValueError("Embedding token limit must be positive")
        for key, value in asdict(self).items():
            if (
                key
                not in {
                    "dimension",
                    "maximum_input_tokens",
                    "tokenizer_digest",
                    "query_prefix",
                    "passage_prefix",
                }
                and not value
            ):
                raise ValueError(f"Embedding profile field {key} must be nonempty")

    @property
    def profile_id(self) -> str:
        canonical = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_vector(values: tuple[float, ...], dimension: int) -> Vector:
    if len(values) != dimension:
        raise ValueError(f"Embedding dimension mismatch: expected {dimension}, got {len(values)}")
    vector: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Embedding values must be real numbers")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Embedding values must be finite")
        try:
            packed = struct.pack("<f", number)
        except OverflowError as error:
            raise ValueError("Embedding value exceeds float32 range") from error
        rounded = struct.unpack("<f", packed)[0]
        if not math.isfinite(rounded):
            raise ValueError("Embedding value exceeds float32 range")
        vector.append(rounded)
    return tuple(vector)


def encode_vector(values: tuple[float, ...], dimension: int) -> bytes:
    vector = validate_vector(values, dimension)
    return struct.pack(f"<{dimension}f", *vector)


def decode_vector(blob: bytes, dimension: int) -> Vector:
    if len(blob) != dimension * 4:
        raise ValueError("Embedding BLOB length does not match dimension")
    return validate_vector(struct.unpack(f"<{dimension}f", blob), dimension)
