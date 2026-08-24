# Installation

This page documents the repository's current installer.

## Requirements

- Docker Engine
- Docker Compose
- Git
- `curl` recommended

## Standard installation

```bash
cd /path/to/infrastructure-agent
./install.sh
```

The installer currently:

- checks Docker/Compose;
- creates `.env` from `.env.example` if needed;
- generates missing local API/database secrets;
- builds/starts Docker services;
- installs the `orion` CLI under `${ORION_INSTALL_PREFIX:-$HOME/.local}/bin`;
- performs a health check.

## Non-interactive

```bash
./install.sh --non-interactive
```

## Build without starting

Where supported by the current installer:

```bash
./install.sh --skip-up
```

## Development dependencies

```bash
make install-dev
```

or:

```bash
uv sync --extra dev
```

## After install

```bash
orion web
```

See `LOCAL_RUN.md` and `DOCKER.md`.
