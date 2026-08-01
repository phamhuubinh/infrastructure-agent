"""Provider selection config.

Kept intentionally simple (no pydantic-settings dependency) — reads from
environment variables with offline-testable retrieval defaults so the service
can boot and ingest documents before a model is selected. Analysis still
requires a configured LLM and never returns a retrieval-only answer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass
class RagServiceConfig:
    embedding_provider: str = "hash"  # hash | openai_compatible | qwen3 | bge_m3
    embedding_base_url: str = "http://localhost:8001/v1"
    embedding_model: str = "qwen3-embedding"
    embedding_api_key: str = ""

    vector_store: str = "memory"  # memory | qdrant
    qdrant_url: str = "http://localhost:6333"

    reranker: str = "noop"  # noop | bge_v2
    ocr_provider: str = "noop"  # noop | paddleocr

    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""

    collection: str = "documents"
    data_dir: str = "/tmp/orion-rag"


def load_config() -> RagServiceConfig:
    return RagServiceConfig(
        embedding_provider=_env("RAG_EMBEDDING_PROVIDER", "hash"),
        embedding_base_url=_env("RAG_EMBEDDING_BASE_URL", "http://localhost:8001/v1"),
        embedding_model=_env("RAG_EMBEDDING_MODEL", "qwen3-embedding"),
        embedding_api_key=_env("RAG_EMBEDDING_API_KEY", ""),
        vector_store=_env("RAG_VECTOR_STORE", "memory"),
        qdrant_url=_env("RAG_QDRANT_URL", "http://localhost:6333"),
        reranker=_env("RAG_RERANKER", "noop"),
        ocr_provider=_env("RAG_OCR_PROVIDER", "noop"),
        llm_base_url=_env("RAG_LLM_BASE_URL", ""),
        llm_model=_env("RAG_LLM_MODEL", ""),
        llm_api_key=_env("RAG_LLM_API_KEY", ""),
        collection=_env("RAG_COLLECTION", "documents"),
        data_dir=_env("RAG_DATA_DIR", "/tmp/orion-rag"),
    )


def build_embedder(config: RagServiceConfig):
    if config.embedding_provider == "hash":
        from app.embedding.hash_provider import HashEmbeddingProvider

        return HashEmbeddingProvider()
    if config.embedding_provider == "openai_compatible":
        from app.embedding.openai_compatible_provider import (
            OpenAICompatibleEmbeddingProvider,
        )

        return OpenAICompatibleEmbeddingProvider(
            base_url=config.embedding_base_url,
            model=config.embedding_model,
            api_key=config.embedding_api_key,
        )
    if config.embedding_provider == "qwen3":
        from app.embedding.qwen3_embedding_provider import Qwen3EmbeddingProvider

        return Qwen3EmbeddingProvider()
    if config.embedding_provider == "bge_m3":
        from app.embedding.bge_m3_embedding_provider import BgeM3EmbeddingProvider

        return BgeM3EmbeddingProvider()
    msg = f"Unknown embedding provider: {config.embedding_provider}"
    raise ValueError(msg)


def build_vector_store(config: RagServiceConfig):
    if config.vector_store == "memory":
        from app.vectordb.memory_store import InMemoryVectorStore

        data_dir = Path(config.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        return InMemoryVectorStore(persist_path=str(data_dir / "vectors.json"))
    if config.vector_store == "qdrant":
        from app.vectordb.qdrant_store import QdrantVectorStore

        return QdrantVectorStore(url=config.qdrant_url)
    msg = f"Unknown vector store: {config.vector_store}"
    raise ValueError(msg)


def build_reranker(config: RagServiceConfig):
    if config.reranker == "noop":
        from app.rerank.noop_reranker import NoOpReranker

        return NoOpReranker()
    if config.reranker == "bge_v2":
        from app.rerank.bge_reranker_provider import BgeRerankerV2Provider

        return BgeRerankerV2Provider()
    msg = f"Unknown reranker: {config.reranker}"
    raise ValueError(msg)


def build_ocr_provider(config: RagServiceConfig):
    if config.ocr_provider == "noop":
        from app.ocr.noop_provider import NoOpOcrProvider

        return NoOpOcrProvider()
    if config.ocr_provider == "paddleocr":
        from app.ocr.paddleocr_provider import PaddleOcrProvider

        return PaddleOcrProvider()
    msg = f"Unknown OCR provider: {config.ocr_provider}"
    raise ValueError(msg)


def build_llm_client(config: RagServiceConfig):
    if not config.llm_base_url.strip() or not config.llm_model.strip():
        return None
    from app.serving.llm_client import LlmClient

    return LlmClient(
        base_url=config.llm_base_url, model=config.llm_model, api_key=config.llm_api_key
    )
