# Installation

This page documents the repository's **current** `install.sh` behavior.

## Host assumptions

The installer is currently Linux-oriented because it configures a system group and external credential file for tool secrets.

Required/expected utilities include:

- Docker Engine;
- Docker Compose;
- `getent`;
- `groupadd`;
- `sudo` when the current user lacks the required privileges.

## Standard installation

```bash
cd /path/to/infrastructure-agent
./install.sh
```

## What the installer currently does

The script:

1. verifies Docker Engine and Docker Compose;
2. creates `.env` if it does not exist;
3. ensures `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `ORION_API_KEY` exist;
4. ensures `ORION_TOOL_SECRETS_FILE` and `ORION_TOOL_SECRETS_GID` exist;
5. creates/configures the `orion-tool-secrets` group when needed;
6. creates or secures the external tool-credentials JSON file;
7. installs the `orion` CLI through `scripts/install-cli`;
8. when stdin is interactive, optionally prompts for an existing OpenAI-compatible model endpoint;
9. starts the full Compose application with:

```bash
docker compose up -d --build --remove-orphans
```

10. reports Grafana/Zabbix credential readiness;
11. if a model was configured interactively, adds/tests the model connection.

## Current flags

The current script does not implement documented installer flags such as:

```text
--non-interactive
--skip-up
```

Do not document or rely on such flags unless they are added to the script.

For automation/non-interactive execution, run the installer with non-TTY stdin; the model setup prompt is skipped because the script only prompts when stdin is interactive.

## `.env`

The installer does not copy `.env.example` as its primary mechanism. It creates/touches `.env` and fills required values directly.

`.env.example` exists mainly as an operator reference for intentionally running Compose by hand.

## Tool credentials

Default external secret file:

```text
/etc/orion/tool-credentials.json
```

The exact path can be overridden with `ORION_TOOL_SECRETS_FILE`.

Grafana/Zabbix credentials can be added later. After changing the credentials file, recreate the API container as instructed by the installer output, for example:

```bash
docker compose up -d --force-recreate api
```

## After installation

```bash
orion web
```

Useful diagnostics:

```bash
docker compose ps
orion log
```

See `LOCAL_RUN.md`, `DOCKER.md`, and `CONFIGURATION.md`.
