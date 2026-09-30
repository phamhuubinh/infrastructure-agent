# Installation

Orion is installed as one local web application: FastAPI serves both the API and the
packaged Orion UI. The normal Linux installation and launch flow is:

```bash
./install.sh
orion
```

On native Windows PowerShell, run from the repository root:

```powershell
.\install.ps1
orion
```

Both installers require Python 3.12 or newer, Node.js 22.12 or newer, and npm. They build and
install the UI with the API as one local application, then invoke the installed venv's Orion CLI
to provision and verify the pinned ~487 MB E5 embeddings asset. A first install needs network
access when the model is absent. A verified model is reused on rerun without downloading it.
Provisioning failure fails installation before a success message. The installed runtime has no
Node/npm dependency. An editable source checkout rebuilds its static UI when `orion web` starts.

Installation does not run `orion knowledge semantic-index`, enable hybrid semantic retrieval,
start Orion, or move model weights into the repository. `orion model install embeddings` remains
the administrative repair/reprovision command. The default model data directory follows
`orion.paths`: `~/.local/share/orion/models/embeddings/<profile_id>/` on Linux and
`%USERPROFILE%\.local\share\orion\models\embeddings\<profile_id>\` on Windows. `ORION_DATA_DIR`
overrides the data root; `XDG_DATA_HOME` is used when set and `ORION_DATA_DIR` is absent.

`ORION_PYTHON` selects an explicit Python interpreter. If it is unset, an existing valid
`PREFIX/.venv/bin/python` is reused before system Python candidates are considered. A
failure reports every candidate and its version; the installer never changes system Python.

On Windows, `ORION_PYTHON` also takes precedence. Otherwise the installer reuses a valid
`PREFIX\.venv\Scripts\python.exe`, tries the Windows `py -3.12` launcher, then a suitable
`python` command. An unsupported or broken existing venv fails with a clear error. The Windows
equivalents of `--prefix`, `--no-dev`, and `--global-launcher` are `-Prefix`, `-NoDev`, and
`-GlobalLauncher`.

By default, installation manages `~/.local/bin/orion`. The managed launcher points at the
new virtual-environment CLI, replaces the known legacy `scripts/orion` launcher, and refuses
to overwrite an unrelated executable. It is safe to run the installer repeatedly.

On Windows, the default installer writes the managed `%LOCALAPPDATA%\Orion\bin\orion.cmd`
launcher, which quotes and delegates to `<prefix>\.venv\Scripts\orion.exe`. It adds that
directory to the user PATH only when absent and updates the current PowerShell process PATH for
immediate `orion` use. A rerun may replace only a launcher with Orion's managed marker; unrelated
content causes a failure. A custom `-Prefix` leaves the user launcher and PATH untouched unless
`-GlobalLauncher` is supplied.

For isolated installer testing, use a custom prefix without altering the global command:

```bash
./install.sh --prefix /tmp/orion-smoke --no-dev
/tmp/orion-smoke/.venv/bin/orion help
```

Add `--global-launcher` only when that custom prefix should become the managed global
launcher. The installer does not create, delete, or print Orion data or credentials.
