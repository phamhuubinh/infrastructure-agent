"""Pinned, explicitly provisioned CPU embeddings for experimental semantic indexing."""

from __future__ import annotations

import hashlib
import importlib
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from orion.embeddings import EmbeddingProfile, Vector, validate_vector
from orion.paths import data_directory

MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = {
    "model.onnx": "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665",
    "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
    "tokenizer_config.json": "a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b",
    "special_tokens_map.json": "d05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7",
    "config.json": "bbb7c1333fc4b3e27fbc9cd5d2070aabcc1d4dfb99917c3633e772f97545a6b6",
}
TOKENIZER_DIGEST = hashlib.sha256(
    "".join(
        f"{name}:{digest}\n" for name, digest in sorted(FILES.items()) if name != "model.onnx"
    ).encode()
).hexdigest()
PROFILE = EmbeddingProfile(
    implementation="fastembed-0.8.1/onnxruntime-1.30.0-cpu/numpy-2.5.3",
    model=MODEL,
    revision=REVISION,
    artifact_digest=FILES["model.onnx"],
    tokenizer_digest=TOKENIZER_DIGEST,
    precision="float32",
    dimension=384,
    pooling="attention-mask-mean",
    normalization="l2",
    query_prefix="query: ",
    passage_prefix="passage: ",
    windowing_version="tokenizers-0.23.2-512-overlap-32-v1",
    maximum_input_tokens=512,
)


def model_directory() -> Path:
    return data_directory() / "models" / "embeddings" / PROFILE.profile_id


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_status(directory: Path | None = None) -> str:
    """Check every pinned artifact locally. This function never opens a network connection."""
    root = directory or model_directory()
    if not root.exists():
        return "missing"
    if not root.is_dir() or not (root / ".complete").is_file():
        return "corrupt"
    try:
        marker = (root / ".complete").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return "corrupt"
    if marker != PROFILE.profile_id:
        return "corrupt"
    for name, expected in FILES.items():
        path = root / name
        if not path.is_file() or _file_digest(path) != expected:
            return "corrupt"
    return "installed"


def install_model(directory: Path | None = None) -> str:
    """Download pinned files into a staging directory, verify, then publish atomically."""
    target = directory or model_directory()
    if model_status(target) == "installed":
        return "installed"
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".embeddings-partial-", dir=target.parent))
    try:
        for name, expected in FILES.items():
            url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/onnx/{name}"
            try:
                with urlopen(url, timeout=60) as response, (staging / name).open("wb") as output:  # noqa: S310 - pinned HTTPS artifact.
                    shutil.copyfileobj(response, output, length=1024 * 1024)
            except Exception as error:
                raise RuntimeError(
                    f"Could not download pinned embedding artifact {name}: {error}"
                ) from error
            if _file_digest(staging / name) != expected:
                raise RuntimeError(f"Embedding artifact digest mismatch: {name}")
        (staging / ".complete").write_text(PROFILE.profile_id, encoding="ascii")
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
        return "installed"
    finally:
        if staging.exists():
            shutil.rmtree(staging)


class LocalE5Embeddings:
    """FastEmbed details stay behind the provider-neutral EmbeddingPort."""

    def __init__(self, directory: Path | None = None) -> None:
        root = directory or model_directory()
        status = model_status(root)
        if status != "installed":
            raise RuntimeError(f"Embedding model {status}; run 'orion model install embeddings'")
        try:
            fastembed = importlib.import_module("fastembed")
            descriptions = importlib.import_module("fastembed.common.model_description")
            model_name = f"{MODEL}@{REVISION}"
            if not any(
                x["model"] == model_name for x in fastembed.TextEmbedding.list_supported_models()
            ):
                fastembed.TextEmbedding.add_custom_model(
                    model=model_name,
                    pooling=descriptions.PoolingType.MEAN,
                    normalization=True,
                    sources=descriptions.ModelSource(hf=MODEL),
                    dim=PROFILE.dimension,
                    model_file="model.onnx",
                )
            self._model: Any = fastembed.TextEmbedding(
                model_name=model_name,
                specific_model_path=str(root),
                local_files_only=True,
                providers=["CPUExecutionProvider"],
                cuda=False,
            )
            tokenizers = importlib.import_module("tokenizers")
            self._tokenizer: Any = tokenizers.Tokenizer.from_file(str(root / "tokenizer.json"))
            self._tokenizer.no_truncation()
            self._tokenizer.no_padding()
        except Exception as error:
            raise RuntimeError(f"Could not load local E5 embedding model: {error}") from error

    @property
    def profile(self) -> EmbeddingProfile:
        return PROFILE

    @property
    def dimension(self) -> int:
        return PROFILE.dimension

    @property
    def maximum_input_tokens(self) -> int | None:
        return PROFILE.maximum_input_tokens

    def passage_windows(self, text: str) -> tuple[str, ...]:
        """Slice raw token IDs, preserving the original segment as the citation identity."""
        if not text.strip():
            return ("",)
        prefix_count = len(
            self._tokenizer.encode(PROFILE.passage_prefix, add_special_tokens=False).ids
        )
        special_count = len(self._tokenizer.encode("", add_special_tokens=True).ids)
        capacity = 512 - prefix_count - special_count
        if capacity <= 32:
            raise RuntimeError("E5 prefix consumes the passage token budget")
        ids = self._tokenizer.encode(text, add_special_tokens=False).ids
        if not ids:
            return ("",)
        windows: list[str] = []
        start = 0
        while start < len(ids):
            end = min(start + capacity, len(ids))
            while True:
                window = str(self._tokenizer.decode(ids[start:end], skip_special_tokens=False))
                if (
                    len(
                        self._tokenizer.encode(
                            PROFILE.passage_prefix + window, add_special_tokens=True
                        ).ids
                    )
                    <= 512
                ):
                    break
                end -= 1
                if end <= start:
                    raise RuntimeError("One passage token cannot fit the E5 input budget")
            windows.append(window)
            if end == len(ids):
                break
            start = max(start + 1, end - 32)
        return tuple(windows)

    def _embed(self, texts: tuple[str, ...], prefix: str) -> tuple[Vector, ...]:
        if not texts:
            return ()
        try:
            results = tuple(self._model.embed((prefix + text for text in texts), batch_size=16))
        except Exception as error:
            raise RuntimeError(f"Local E5 inference failed: {error}") from error
        if len(results) != len(texts):
            raise ValueError("Embedding inference returned the wrong vector count")
        vectors: list[Vector] = []
        for result in results:
            vector = validate_vector(tuple(float(value) for value in result), PROFILE.dimension)
            norm = math.sqrt(sum(value * value for value in vector))
            if not 0.999 <= norm <= 1.001:
                raise ValueError(f"Embedding normalization contract failed: norm={norm}")
            vectors.append(vector)
        return tuple(vectors)

    def embed_passages(self, texts: tuple[str, ...]) -> tuple[Vector, ...]:
        return self._embed(texts, PROFILE.passage_prefix)

    def embed_queries(self, texts: tuple[str, ...]) -> tuple[Vector, ...]:
        return self._embed(texts, PROFILE.query_prefix)
