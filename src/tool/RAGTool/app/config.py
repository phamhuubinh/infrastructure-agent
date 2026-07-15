"""Provider selection config.

Kept intentionally simple (no pydantic-settings dependency) — reads from
environment variables with sane offline-testable defaults so the service
boots even with nothing configured (using the hash embedding fallback +
in-memory vector store + no-op reranker/OCR). Point every *_PROVIDER env
var at "real" and fill in the matching URL/model vars to go to production.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


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

    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "default"
    llm_api_key: str = ""
    llm_enabled: bool = False

    collection: str = "documents"


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
        llm_base_url=_env("RAG_LLM_BASE_URL", "http://localhost:8000/v1"),
        llm_model=_env("RAG_LLM_MODEL", "default"),
        llm_api_key=_env("RAG_LLM_API_KEY", ""),
        llm_enabled=_env("RAG_LLM_ENABLED", "false").lower() == "true",
        collection=_env("RAG_COLLECTION", "documents"),
    )


def build_embedder(config: RagServiceConfig):
    if config.embedding_provider == "hash":
        from app.embedding.hash_provider import HashEmbeddingProvider

        return HashEmbeddingProvider()
    if config.embedding_provider == "openai_compatible":
        from app.embedding.openai_compatible_provider import OpenAICompatibleEmbeddingProvider

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
    raise ValueError(f"Unknown embedding provider: {config.embedding_provider}")


def build_vector_store(config: RagServiceConfig):
    if config.vector_store == "memory":
        from app.vectordb.memory_store import InMemoryVectorStore

        return InMemoryVectorStore()
    if config.vector_store == "qdrant":
        from app.vectordb.qdrant_store import QdrantVectorStore

        return QdrantVectorStore(url=config.qdrant_url)
    raise ValueError(f"Unknown vector store: {config.vector_store}")


def build_reranker(config: RagServiceConfig):
    if config.reranker == "noop":
        from app.rerank.noop_reranker import NoOpReranker

        return NoOpReranker()
    if config.reranker == "bge_v2":
        from app.rerank.bge_reranker_provider import BgeRerankerV2Provider

        return BgeRerankerV2Provider()
    raise ValueError(f"Unknown reranker: {config.reranker}")


def build_ocr_provider(config: RagServiceConfig):
    if config.ocr_provider == "noop":
        from app.ocr.noop_provider import NoOpOcrProvider

        return NoOpOcrProvider()
    if config.ocr_provider == "paddleocr":
        from app.ocr.paddleocr_provider import PaddleOcrProvider

        return PaddleOcrProvider()
    raise ValueError(f"Unknown OCR provider: {config.ocr_provider}")


def build_llm_client(config: RagServiceConfig):
    if not config.llm_enabled:
        return None
    from app.serving.llm_client import LlmClient

    return LlmClient(base_url=config.llm_base_url, model=config.llm_model, api_key=config.llm_api_key)
