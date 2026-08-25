# Installation

Orion is installed as one local web application: FastAPI serves both the API and the
packaged Orion UI. The normal installation and launch flow is:

```bash
./install.sh
orion
```

The installer requires Python 3.12 or newer, Node.js 22.12 or newer, and npm. It uses
`npm ci` and a production Vite build, then copies the resulting client bundle into the
install-owned `.orion-ui` directory. No Vite development server is needed after install.

`ORION_PYTHON` selects an explicit Python interpreter. If it is unset, an existing valid
`PREFIX/.venv/bin/python` is reused before system Python candidates are considered. A
failure reports every candidate and its version; the installer never changes system Python.

By default, installation manages `~/.local/bin/orion`. The managed launcher points at the
new virtual-environment CLI, replaces the known legacy `scripts/orion` launcher, and refuses
to overwrite an unrelated executable. It is safe to run the installer repeatedly.

Use an isolated prefix without altering the global command:

```bash
./install.sh --prefix /tmp/orion-smoke --no-dev
/tmp/orion-smoke/.venv/bin/orion web --no-open
```

Add `--global-launcher` only when that custom prefix should become the managed global
launcher. The installer does not create, delete, or print Orion data or credentials.
