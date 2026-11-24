$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if ($env:ORION_DESKTOP_VERSION -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -or
    $env:ORION_UPDATE_SIGNER_SHA256 -notmatch '^[0-9a-fA-F]{64}$' -or
    $env:ORION_RELEASE_CHANNEL -notin @('stable', 'preview')) {
    throw 'An explicit version, channel and publisher pin are required.'
}
$source = (git rev-parse HEAD).Trim()
if ($source -ne $env:GITHUB_SHA -or (git status --porcelain)) { throw 'Expected the exact clean CI source.' }
$base = python -c "import runpy; print(runpy.run_path('backend/src/orion/_version.py')['__version__'])"
python -m pip install --require-hashes -r scripts/refactor/locks/core.txt -r scripts/refactor/locks/dev.txt
python -m build --no-isolation --wheel backend --outdir release-work/update-wheel
python scripts/desktop/build_sidecar.py --wheel "release-work/update-wheel/orion-$base-py3-none-any.whl" --output release-work/managed-backend
python scripts/worker/portable.py --output release-work/update-worker
python scripts/worker/portable.py --output release-work/update-worker --stage-desktop release-work/managed-backend --version $base --source-sha $source
$config = Join-Path $env:RUNNER_TEMP 'orion-update-tauri.json'
@{ version = $env:ORION_DESKTOP_VERSION } | ConvertTo-Json | Set-Content -LiteralPath $config -Encoding utf8NoBOM
Push-Location ui
try {
    npm ci
    npm run desktop:build -- --ci --bundles nsis --no-sign --config $config
} finally {
    Pop-Location
}
$name = "Orion_${env:ORION_DESKTOP_VERSION}_x64-setup.exe"
$binary = Join-Path 'ui/src-tauri/target/release/bundle/nsis' $name
if (!(Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'NSIS output name does not match the release.' }
$null = New-Item -ItemType Directory -Path 'release-work/desktop-update'
Copy-Item -LiteralPath $binary -Destination 'release-work/desktop-update'
