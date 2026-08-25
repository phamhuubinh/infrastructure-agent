# Running Orion locally

## Web UI

```bash
orion web
```

The command starts the local API at `http://127.0.0.1:61888` by default. It binds to
loopback by default and does not open a browser or manage Docker.

Use `orion web --host HOST --port PORT` (or `ORION_HOST`/`ORION_PORT`) to configure the
listener. `--data-dir DIRECTORY` keeps a test or alternate installation fully isolated.

Run the preserved UI in a second terminal:

```bash
cd ui
npm run dev
```

## Logs

```bash
orion log
```

This prints the database/log locations and the last 100 sanitized public application
events. Use `orion log --tail 20` to limit output.

## CLI commands

Use `orion --help` to inspect the CLI surface. Stop `orion web` with Ctrl-C; starting it
again with the same data directory resumes the same SQLite/WAL database and blob store.

## Target runtime

Running locally does not change Chat/Project semantics:

```text
UI/CLI
→ backend
→ local/remote configured model
→ automatic registered tool calls
→ local integrations/RAG
→ final response
```
