# API Reference

> Orion Platform API — all endpoints with curl examples and expected responses.

Base URL: `http://localhost:61888`

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
  "response": "The disk on webserver01 is healthy. / is at 45% usage (32GB/80GB).",
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

## Knowledge Base

### GET /api/knowledge/health

Check RAG service health.

```bash
curl http://localhost:61888/api/knowledge/health
```

**Response:**
```json
{"status": "ok", "service": "rag"}
```

---

### POST /api/knowledge/query

Query the knowledge base.

```bash
curl -X POST http://localhost:61888/api/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{"query": "nginx configuration", "top_k": 5}'
```

**Response:**
```json
{
  "query": "nginx configuration",
  "results": [
    {
      "chunk_id": "...",
      "text": "...",
      "score": 0.92,
      "metadata": {"doc_id": "nginx-guide", "source": "nginx-guide.pdf"}
    }
  ]
}
```

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