# Running Orion locally

Start the complete local web application with either command:

```bash
orion
orion web
```

Both serve the preserved Orion UI at `http://127.0.0.1:61888/` and the API at
`http://127.0.0.1:61888/api/...`. A browser opens after the loopback server is ready.
For automation or headless use, disable that behavior explicitly:

```bash
orion web --no-open
```

The browser is automatically opened only for loopback hosts (`127.0.0.1`, `localhost`, or
`::1`). `orion web --host HOST --port PORT` (or `ORION_HOST` / `ORION_PORT`) configures the
listener; non-loopback bindings never auto-open a browser. Orion remains loopback-only by
default.

The production UI is built by `./install.sh` and served by the same FastAPI process. Do not
run `npm run dev` for normal installed use. It remains a frontend-development workflow only.

```bash
cd ui
npm run dev
```

Show sanitized local logs with:

```bash
orion log
```

Use `orion log --tail 20` to limit output. Stop the web app with Ctrl-C; restarting it with
the same data directory resumes the same SQLite/WAL database and blob store.
