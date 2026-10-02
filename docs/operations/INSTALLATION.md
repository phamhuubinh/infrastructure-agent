# Installation

## Normal installation from a release

Download the archive for your platform from the matching GitHub Release. Orion needs
Python 3.12 or newer. No Git, Node.js, npm, or source checkout is needed on the target.

Linux x86_64:

```bash
tar -xzf orion-<version>-linux-x86_64.tar.gz
cd orion-<version>-linux-x86_64
./install.sh
orion
```

Native Windows x64 PowerShell:

```powershell
Expand-Archive .\orion-<version>-windows-x64.zip -DestinationPath .
cd .\orion-<version>-windows-x64
.\install.ps1
orion
```

The release installers verify the bundled wheel and every packaged UI file against
`release-manifest.json` before installing anything. They create or reuse an install-owned
virtual environment, install the bundled wheel, copy the prebuilt UI, and call the installed
`orion model install embeddings` command. First installation needs network access for Python
dependencies and, unless a verified cache exists, the pinned ~487 MB E5 model. E5 is never
included in release archives. A verified cache is reused; corrupt data is repaired by the
existing model installer. Provisioning failure fails installation.

The default Linux prefix is `~/.local/share/orion-install`; Windows uses
`%LOCALAPPDATA%\Orion\install`. Use `./install.sh --prefix /path/to/install` or
`.\install.ps1 -Prefix 'C:\Path With Spaces\Orion'` for another location. A custom prefix
does not change the user launcher unless `--global-launcher` or `-GlobalLauncher` is also
specified. The Linux launcher is `~/.local/bin/orion` (or `XDG_BIN_HOME/orion`). The Windows
launcher is `%LOCALAPPDATA%\Orion\bin\orion.cmd` and that directory is added once to the
user PATH. Existing unrelated launchers are never overwritten. Repeating installation is safe.

`ORION_PYTHON` chooses Python explicitly. `ORION_DATA_DIR` and `XDG_DATA_HOME` keep their
normal application-data meanings; model data stays outside the installation prefix. Installing
does not enable hybrid retrieval, run semantic indexing, or start the server. Remote Access v1
retains loopback by default and its normal authentication and non-loopback checks.

The release manifest records the version, exact source commit, platform, wheel SHA-256, and
individual UI file SHA-256 digests. `SHA256SUMS` covers both final archives. Compare an archive
with that checksum file before extracting when transferring it outside GitHub Releases.

## Source/developer installation

From a repository checkout, use `./install.sh` on Linux or `.\install.ps1` in Windows
PowerShell. These source installers require Python 3.12+, Node.js 22.12+, and npm. They
install the backend editable and build the UI locally. `--no-dev`/`-NoDev` omits developer
dependencies. Source installation uses the same model provisioning and application runtime.

## Publishing a release

Set the release version once in `backend/src/orion/_version.py`, merge that change to `main`,
then manually dispatch the **Release bundles** workflow with the same version. The workflow
requires a clean checkout of that commit, builds one wheel and one UI, assembles both archives,
checks the full backend and UI suites, exercises each extracted archive on its native runner,
and publishes the GitHub Release only after all checks pass. An existing release tag must point
to the same source commit before its assets can be updated.
