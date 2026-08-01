# Docker Guide

> Build, run, and troubleshoot Orion with Docker Compose.

## Prerequisites

- Docker Engine 24+
- Docker Compose v2+
- OpenSSL (for self-signed cert generation, installed automatically)

## Quick Start

```bash
# Generate self-signed certificates (first time only)
make certs

# Start all services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f api
docker compose logs -f ui
```

Services and ports:

| Service | Internal Port | Exposed | Description |
|---------|--------------|---------|-------------|
| `reverse-proxy` | 80/443 | 80/443 | HTTP redirect and HTTPS reverse proxy |
| `api` | 61888 | — | FastAPI backend |
| `ui` | 80 | — | Built React frontend |
| `postgres` | 5432 | — | PostgreSQL database |
| `rag-service` | 8080 | 8080 | RAG microservice |

## Service Details

### API Service

```bash
# Rebuild API after code changes
docker compose build api
docker compose up -d api

# Run tests inside container
docker compose exec api pytest tests/ -q
```

### Database

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U orion -d orion

# Reset database (WARNING: deletes all data)
docker compose down -v postgres
docker compose up -d postgres
```

### RAG Service

```bash
# Check RAG health
curl http://localhost:8080/health

# Rebuild RAG service
docker compose build rag-service
docker compose up -d rag-service
```

## Configuration

### Environment Variables

Create a `.env` file (or export before `docker compose up`):

```bash
# API Key (optional, disables auth when empty)
ORION_API_KEY=your-secret-key

# Database
ORION_DATABASE_URL=postgresql://orion:orion@postgres:5432/orion
ORION_DB_POOL_SIZE=5
ORION_DB_SSL=0

# RAG Service
RAG_SERVICE_URL=http://rag-service:8080

# Logging
ORION_LOG_FORMAT=json
ORION_LOG_LEVEL=INFO

# Frontend
ORION_FRONTEND_PORT=5173

# Conversation
ORION_CONVERSATION_THRESHOLD=4
```

### Secrets

Secrets (Grafana tokens, Zabbix credentials, LLM keys) are stored in `config/secrets.local.json` — never in `.env` or committed to git.

## Troubleshooting

### API won't start

```bash
# Check if port 61888 is already in use
lsof -i :61888

# Check API logs for database connection errors
docker compose logs api | grep -i error
```

### Database connection refused

```bash
# Verify PostgreSQL is accepting connections
docker compose exec postgres pg_isready -U orion

# Check API can reach the database
docker compose exec api python -c "
from src.backend.db import _get_dsn, _import_driver
dsn = _get_dsn()
print(f'DSN: {dsn}')
driver, err = _import_driver()
if err:
    print(f'Import error: {err}')
else:
    try:
        conn = driver.connect(dsn)
        print('Connected successfully')
        conn.close()
    except Exception as e:
        print(f'Connection error: {e}')
"
```

### Nginx returns 502

```bash
# Check if backend services are running
docker compose ps api ui

# Check nginx config
docker compose exec reverse-proxy nginx -t

# Reload nginx
docker compose exec reverse-proxy nginx -s reload
```

### Reset everything

```bash
docker compose down -v
docker compose up -d --build
