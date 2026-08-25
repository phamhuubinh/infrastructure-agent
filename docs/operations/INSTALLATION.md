# Installation

This page documents Orion's local-first installation surface.

## Host assumptions

The M1 installer requires Python 3.12 or newer and creates a local `.venv`.

## Standard installation

```bash
cd /path/to/Orion_agent
./install.sh
source .venv/bin/activate
```

## What the installer currently does

The script creates or reuses `.venv` and installs the current Orion package with its
development checks. It does not create, overwrite, or remove Orion data or credentials.
Configure a model through `/api/models` or set `ORION_MODEL_BASE_URL` and `ORION_MODEL_ID`
before starting `orion web`.

## Current flags

Use `--prefix DIRECTORY` for an isolated installation (useful for a smoke test), or
`--no-dev` for a runtime-only virtual environment. The installer never alters `.env`.

## After installation

```bash
orion web
orion log
make test
make lint
```

See `LOCAL_RUN.md` and `CONFIGURATION.md`.
