# Installation

This page documents the repository's **current M1** `install.sh` behavior.

## Host assumptions

The M1 installer requires Python 3.12 or newer and creates a local `.venv`.

## Standard installation

```bash
cd /path/to/infrastructure-agent
./install.sh
```

## What the installer currently does

The script creates `.venv` and installs Orion with its development checks. Configure a
model through the `/api/models` API or set `ORION_MODEL_BASE_URL` and `ORION_MODEL_ID`
before starting `orion web`.

## Current flags

The M1 installer has no command-line flags and does not alter an existing `.env`.

## After installation

```bash
orion web
orion log
make test
make lint
```

See `LOCAL_RUN.md` and `CONFIGURATION.md`.
