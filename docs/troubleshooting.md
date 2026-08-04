# Troubleshooting & FAQ

Common issues encountered when running Orion and how to resolve them.

## Table of Contents

- [Vite Dev Server Issues](#vite-dev-server-issues)
- [Database Connection Issues](#database-connection-issues)
- [Certificate/SSL Warnings](#certificatessl-warnings)
- [LLM / Assessment Model Issues](#llm--assessment-model-issues)
- [Docker Compose Issues](#docker-compose-issues)
- [SSH / Linux Tool Issues](#ssh--linux-tool-issues)
- [API Authentication Issues](#api-authentication-issues)
- [Performance & Resources](#performance--resources)
- [General FAQ](#general-faq)

---

## Vite Dev Server Issues

### Frontend dev server fails to start

**Symptom:** `ERROR: Frontend dev server did not start in time.`

**Causes:**
- Node.js/npm not installed or wrong version.
- Port 5173 already in use by another process.
- `node_modules` not installed in the `ui/` directory.

**Resolution:**
1. Ensure Node.js 18+ is installed: `node --version`.
2. Run `cd ui && npm install` to install frontend dependencies.
3. Check if port 5173 is in use: `lsof -i :5173` and kill the process if needed.
4. Use a different frontend port: `ORION_FRONTEND_PORT=5174 python3 -m src.cli web`.

### Vite port conflict

**Symptom:** Vite fails with `Port 5173 is already in use`.

**Resolution:**
Set a different port:
```bash
ORION_FRONTEND_PORT=5174 python3 -m src.cli web
```

---

## Database Connection Issues

### PostgreSQL connection refused

**Symptom:** `Failed to connect to database after 3 attempts: ...`

**Causes:**
- PostgreSQL service not running.
- Wrong credentials in `ORION_DATABASE_URL` or env vars.
- Docker Compose services not started.

**Resolution:**
1. In Docker Compose: `docker compose up -d postgres` and wait for health check.
2. Direct connection: verify `psql` can connect with the same DSN.
3. Check `POSTGRES_PASSWORD`, `POSTGRES_USER`, `POSTGRES_HOST` env vars.
4. Verify the PostgreSQL port (5432) is accessible.

### Database connection times out from pool

**Symptom:** `Timed out waiting for database connection from pool`.

**Resolution:**
1. Increase pool size: `ORION_DB_POOL_SIZE=10`.
2. Check for connection leaks — ensure `_put_conn` is always called.
3. Restart the application to reset the pool.

---

## TLS

The root Compose stack serves local HTTP at `http://localhost`; it no longer requires generated self-signed certificates. Production deployments should terminate TLS in their external ingress or reverse proxy.

---

## LLM / Assessment Model Issues

### Model health check fails

**Symptom:** `/api/status` shows `llm: error` or `/api/check-model` returns `{"status": "error"}`.

**Causes:**
- LLM server (Ollama, vLLM, OpenAI) not running.
- Wrong saved base URL, API key, or model name.
- Model not pulled/loaded on the LLM server.

**Resolution:**
1. Open Web UI **Cài đặt**, then press **Kiểm tra** for the saved connection.
2. From Compose, run `docker compose exec api orion model test <connection-name>`.
3. Check the saved base URL and model with `docker compose exec api orion model list`.
4. Check the independently managed model runtime and install/load the requested model there if necessary.
5. Orion still starts without a model; Chat assessment and RAG analysis report that setup is required.

### Assessment returns empty or error

**Symptom:** API query returns error status or empty assessment.

**Resolution:**
1. Check LLM server logs for rate limiting or token quota issues.
2. Verify the model supports the request format (OpenAI-compatible `/v1/chat/completions`).
3. Save the connection with a larger timeout in the Web UI or `orion model add ... --timeout 300`.

---

## Docker Compose Issues

### Containers fail to start

**Symptom:** `docker compose up` exits with errors.

**Resolution:**
1. Ensure Docker Engine is running (Docker Desktop or `dockerd`).
2. Rebuild images: `docker compose build --no-cache`.
3. Check logs: `docker compose logs <service-name>`.
4. For a first install, run `./install.sh`; it creates required secrets automatically. Operators invoking Compose directly must create `.env` with nonblank `POSTGRES_PASSWORD` and `ORION_API_KEY`.

### Port conflicts

**Symptom:** `Bind for 0.0.0.0:80 failed: port is already allocated`.

**Resolution:**
Stop the conflicting process or change the port mapping in `docker-compose.yml`:
```yaml
ports:
  - "8081:80"  # Map host port 8081 instead of 80
```

### Database migrations not running

**Symptom:** Tables don't exist after first startup.

**Resolution:**
Orion auto-creates tables on first connection. Verify:
1. `ORION_DATABASE_URL` is correctly set.
2. The PostgreSQL user has CREATE TABLE permissions.
3. Check API logs: `docker compose logs api`.

---

## SSH / Linux Tool Issues

### SSH connection fails

**Symptom:** Linux tool returns `SSH connection failed` or timeout.

**Resolution:**
1. Verify the target is reachable: `ssh user@target echo ok`.
2. Check `targets.json` has correct credentials.
3. Host key checking is disabled by default for local trusted networks — if connecting to an untrusted network, set `strict_host_key_checking: true` in `targets.json`.

### Command timeout

**Symptom:** Linux tool commands timeout.

**Resolution:**
1. Increase per-command timeout in `targets.json`.
2. Check target server load.
3. Verify network latency between agent and target.

---

## API Authentication Issues

### 401 Unauthorized for all requests

**Symptom:** Every API endpoint except `/api/health` returns 401.

**Causes:**
- `ORION_API_KEY` is set but not provided in requests.
- Wrong key format.

**Resolution:**
1. If auth is unwanted in local dev, unset `ORION_API_KEY`: `unset ORION_API_KEY`.
2. Provide the key via header:
   ```bash
   curl -H "X-API-Key: your-key" http://localhost:61888/api/status
   # or
   curl -H "Authorization: Bearer your-key" http://localhost:61888/api/status
   ```
3. Check audit logs for auth failures — look for `auth_failure` events.

---

## Performance & Resources

### High memory usage

**Symptom:** Docker containers or local process using excessive RAM.

**Resolution:**
1. Docker Compose services now have resource limits (`mem_limit`, `cpus`).
2. For local dev without Docker, the Python process typically uses 200-500MB.
3. RAG service memory depends on embedding provider — `hash` embedding uses minimal memory.

### Slow query response

**Symptom:** Investigation queries take >30 seconds.

**Resolution:**
1. Check LLM latency — this is usually the bottleneck.
2. Reduce `max_tokens` in the model config.
3. Use deterministic responder where possible (service status checks skip LLM).
4. Check target server response times.

---

## General FAQ

### How do I run Orion without Docker?

```bash
pip install -e ".[test]"
python3 -m src.cli web
```

This starts the API + Vite frontend in development mode on localhost, stays attached to the terminal, and stops both when you press `Ctrl+C`. The installed `orion web` command instead controls the packaged Docker Web services.

### How do I add a new target server?

Edit `targets.json`:
```json
{
  "targets": {
    "myserver": {
      "host": "192.168.1.100",
      "username": "admin",
      "auth_method": "key",
      "key_path": "~/.ssh/id_rsa"
    }
  }
}
```

### How do I set up API key authentication?

```bash
export ORION_API_KEY="your-secure-random-key"
python3 -m src.cli web
```

Requests must include the key in the `X-API-Key` or `Authorization: Bearer` header.

### What's the difference between source Web mode and Docker Compose?

`python3 -m src.cli web` runs the backend + Vite dev server directly on your machine. The installed `orion web` launcher controls the Docker Web services and shows their logs until `Ctrl+C`; `orion log` shows logs for the complete stack without stopping it on `Ctrl+C`. Docker Compose runs Nginx (local HTTP), API, UI, PostgreSQL, and RAG as separate containers. RAG is reachable only from the internal Compose network.

### How do I view the OpenAPI docs?

When running: `http://localhost:61888/docs` directly or `http://localhost/docs` through Docker Compose.

### Where are logs stored?

- Installed Docker stack: `orion log` follows all service logs.
- Console: printed to stderr by default.
- File rotation: enabled with `ORION_LOG_FILE=/path/to/logs/orion.log`, rotates at 10MB with 5 backups.
- Structured JSON: set `ORION_LOG_FORMAT=json` for machine-readable logs.

> **Last updated:** 2026-08-02
