# Orion Project RAG Service

This directory is the **current standalone Project/document-analysis service** used by the Web UI. It is not currently registered as a canonical Chat capability. ADR-0003 defines the target: Project knowledge becomes a normal READ capability in the same agent loop.

## Deployment/security boundary

The root Orion Compose stack keeps RAG internal. The standalone Compose in this directory is a development stack and currently publishes the RAG API and Qdrant ports without a hardened public auth boundary.

**Do not expose the standalone stack to an untrusted network.** Prefer loopback-only bindings or add explicit auth/mTLS and secured vector-store administration.

Analysis requests can carry request-scoped `model_config` (`base_url`, `model`, `api_key`, `timeout`). That is intended for trusted Orion-internal configuration; it must not remain an unrestricted unauthenticated SSRF/token-forwarding surface in a hardened deployment. Enforce destination allowlisting/private-IP/DNS/rebinding/redirect policy before untrusted clients can control it.

## Isolation/persistence

Each Project has document files, dense collection, BM25 index, and project metadata. Per-project locking prevents concurrent interleaving in one process, but **does not make filesystem/vector/BM25/metadata mutation transactional**. Multi-store crash/failure consistency is tracked as F-19.

Corrupt metadata must be preserved/quarantined rather than treated as empty and overwritten (F-07).

## Running locally

```bash
uv sync --group dev
RAG_DATA_DIR=/tmp/orion-rag \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
uv run pytest tests -q
```

Analysis requires a model. Standalone trusted-local environment variables can configure the model.

## API

```text
GET    /health
POST   /projects
GET    /projects
GET    /projects/{project_id}
DELETE /projects/{project_id}
POST   /projects/{project_id}/documents
DELETE /projects/{project_id}/documents/{doc_id}
POST   /projects/{project_id}/analyses
```

Upload limit: 50 MiB.

Typical analysis:

```json
{"query":"Compare the proposals and list risks","top_k":5}
```

Internal/request-scoped form may additionally contain:

```json
{
  "query": "Compare the proposals and list risks",
  "top_k": 5,
  "model_config": {
    "base_url": "http://model.example/v1",
    "model": "model-name",
    "api_key": "...",
    "timeout": 180
  }
}
```

Legacy `/ingest` and `/query` remain isolated in the built-in `default` Project for older clients; canonical Chat does not use them.
