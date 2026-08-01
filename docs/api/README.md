# API Reference

> Orion Platform API — all endpoints with curl examples and expected responses.

Base URL: `http://localhost:61888`

When `ORION_API_KEY` is configured, all endpoints except `/api/health` require `X-API-Key: <key>` or a Bearer token.

---

## Health & Status

### GET /api/health

Check if the API is running.

```bash
curl http://localhost:61888/api/health
```

**Response:**
```json
{"status": "ok", "version": "1.0.0"}
```

---

### GET /api/status

Full service status with component health checks.

```bash
curl http://localhost:61888/api/status
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": 1720000000.0,
  "components": {
    "app": {"status": "ok", "version": "1.0.0"},
    "database": {"status": "ok"},
    "llm": {"status": "ok"},
    "rag": {"status": "ok"}
  }
}
```

---

### GET /api/metrics

Runtime metrics counters.

```bash
curl http://localhost:61888/api/metrics
```

**Response:**
```json
{
  "metrics": {
    "execution_count": 42,
    "evidence_count": 156,
    "error_count": 2,
    "tool_call_count": 98,
    "active_sessions": 3
  }
}
```

---

### GET /api/check-model

Check LLM model availability.

```bash
curl http://localhost:61888/api/check-model
```

**Response:**
```json
{"status": "ok"}
```

---

## Model Configuration

Orion accepts an empty model registry. The API below is also used by Web UI **Cài đặt**; secrets are never returned by list responses.

### GET /api/models

```json
{"active_server": "", "models": []}
```

### POST /api/models

Save and optionally activate an OpenAI-compatible, Ollama, or vLLM connection. A base URL ending in `/v1` is accepted and normalized.

```bash
curl -X POST http://localhost:61888/api/models \
  -H "Content-Type: application/json" \
  -d '{"name":"primary","provider":"openai","base_url":"https://api.openai.com/v1","model":"gpt-4.1","api_key":"...","activate":true}'
```

### POST /api/models/{name}/test

Runs a real chat-completions request against the saved connection. Returns HTTP 503 with diagnostic detail when the test fails.

### POST /api/models/{name}/activate

Select a saved connection as the default for Chat and RAG.

### DELETE /api/models/{name}

Delete a saved connection. If it was active, Orion selects the next saved connection or returns to setup mode.

## Query & Investigation

### POST /api/query

Submit an infrastructure investigation query.

```bash
curl -X POST http://localhost:61888/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Check disk usage on webserver01"}'
```

**Response:**
```json
{
  "session_id": "f39a84f716c2",
  "assessment": "The disk on webserver01 is healthy. / is at 45% usage (32GB/80GB).",
  "steps": [
    {
      "stage": "intent",
      "intent": "disk_usage",
      "confidence": 0.95
    },
    {
      "stage": "evidence",
      "items": [
        {
          "evidence_name": "disk",
          "target": "webserver01",
          "success": true
        }
      ]
    },
    {
      "stage": "assessment",
      "prompt": "...",
      "tokens": {"input": 512, "output": 128}
    }
  ]
}
```

---

## Project RAG Analysis

These endpoints are separate from `/api/query`. Chat does not call RAG.

### GET /api/rag/health

Check RAG service health.

```bash
curl http://localhost:61888/api/rag/health
```

**Response:**
```json
{"status": "ok", "project_count": 3, "llm_configured": true, "llm_scope": "request"}
```

---

### POST /api/rag/projects

Create an isolated document project.

```bash
curl -X POST http://localhost:61888/api/rag/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Nginx migration", "description": "Compare migration plans"}'
```

**Response:**
```json
{
  "id": "a1b2c3d4e5f6",
  "name": "Nginx migration",
  "description": "Compare migration plans",
  "documents": [],
  "analyses": [],
  "created_at": "2026-08-02T00:00:00Z",
  "updated_at": "2026-08-02T00:00:00Z"
}
```

### POST /api/rag/projects/{project_id}/documents

```bash
curl -X POST http://localhost:61888/api/rag/projects/a1b2c3d4e5f6/documents \
  -F "file=@migration-plan.pdf"
```

Supported Web UI uploads: PDF, TXT, Markdown, CSV, JSON, YAML, and log files; maximum 50 MiB.

### POST /api/rag/projects/{project_id}/analyses

```bash
curl -X POST http://localhost:61888/api/rag/projects/a1b2c3d4e5f6/analyses \
  -H "Content-Type: application/json" \
  -d '{"query": "Compare the rollout options and identify risks", "top_k": 5}'
```

```json
{
  "answer": "...",
  "retrieved": [
    {
      "id": "...",
      "text": "...",
      "score": 0.92,
      "payload": {"project_id": "a1b2c3d4e5f6", "filename": "migration-plan.pdf"}
    }
  ]
}
```

Analysis requires an active Orion model and returns HTTP 503 when none is configured. Project list/get responses include document metadata and the latest 100 analyses. Delete endpoints exist for both documents and projects. The old `/api/knowledge/query` alias uses the built-in `default` project only.

---

## Documents

### POST /api/documents/upload

Upload a document.

```bash
curl -X POST http://localhost:61888/api/documents/upload \
  -H "Content-Type: application/json" \
  -d '{"filename": "guide.pdf", "content": "<base64>", "session_id": "abc123"}'
```

**Response:**
```json
{"doc_id": "abc-def-123", "status": "uploaded"}
```

---

### GET /api/documents

List uploaded documents.

```bash
curl http://localhost:61888/api/documents
curl "http://localhost:61888/api/documents?session_id=abc123&limit=10"
```

**Response:**
```json
{
  "documents": [
    {
      "doc_id": "abc-def-123",
      "filename": "guide.pdf",
      "created_at": "2026-07-23T08:00:00Z",
      "size_bytes": 1048576,
      "session_id": "abc123"
    }
  ]
}
```

---

### GET /api/documents/{doc_id}

Get document metadata.

```bash
curl http://localhost:61888/api/documents/abc-def-123
```

---

### GET /api/documents/{doc_id}/download

Download document content.

```bash
curl -O http://localhost:61888/api/documents/abc-def-123/download
```

---

### DELETE /api/documents/{doc_id}

Delete a document.

```bash
curl -X DELETE http://localhost:61888/api/documents/abc-def-123
```

---

## Sessions

### GET /api/sessions

List all sessions.

```bash
curl http://localhost:61888/api/sessions
```

**Response:**
```json
{
  "sessions": [
    {"id": "abc123", "turns": 5, "updated": "2026-07-23T08:00:00Z", "preview": "..."}
  ]
}
```

---

### DELETE /api/sessions/{session_id}

Delete a session.

```bash
curl -X DELETE http://localhost:61888/api/sessions/abc123
```

---

### PATCH /api/sessions/{session_id}

Rename a session.

```bash
curl -X PATCH http://localhost:61888/api/sessions/abc123 \
  -H "Content-Type: application/json" \
  -d '{"title": "Production Debugging"}'
```

---

## Authentication

When `ORION_API_KEY` is set, all endpoints except `/api/health` require authentication:

```bash
curl -H "X-API-Key: $ORION_API_KEY" http://localhost:61888/api/status
# or
curl -H "Authorization: Bearer $ORION_API_KEY" http://localhost:61888/api/status
```

**Error response (401):**
```json
{"detail": "Unauthorized"}
