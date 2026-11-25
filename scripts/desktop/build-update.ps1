[CmdletBinding()]
param(
    [string]$Source = $env:GITHUB_SHA,
    [string]$Version = $env:ORION_DESKTOP_VERSION,
    [string]$SignerSha256 = $env:ORION_UPDATE_SIGNER_SHA256,
    [ValidateSet('preview', 'stable')][string]$Channel = $env:ORION_RELEASE_CHANNEL
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -or
    $SignerSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $Channel -notin @('stable', 'preview')) {
    throw 'An explicit version, channel and publisher pin are required.'
}
Push-Location (Join-Path $PSScriptRoot '../..')
try {
    if ($Source -notmatch '^[a-f0-9]{40}$' -or $Source -cne (git rev-parse HEAD).Trim() -or (git status --porcelain)) {
        throw 'Build from the expected clean Git commit.'
    }
    $env:ORION_DESKTOP_VERSION = $Version
    $env:ORION_UPDATE_SIGNER_SHA256 = $SignerSha256
    $env:ORION_RELEASE_CHANNEL = $Channel
    $work = Join-Path (Get-Location).Path 'release-work'
    foreach ($directory in @('desktop-update', 'managed-backend', 'update-wheel', 'update-worker')) {
        if (Test-Path -LiteralPath (Join-Path $work $directory)) {
            throw 'Use a fresh checkout or move the previous release-work build directories aside.'
        }
    }
    $base = python -c "import runpy; print(runpy.run_path('backend/src/orion/_version.py')['__version__'])"
    python -m pip install --require-hashes -r scripts/refactor/locks/core.txt -r scripts/refactor/locks/dev.txt
    python -m build --no-isolation --wheel backend --outdir release-work/update-wheel
    python scripts/desktop/build_sidecar.py --wheel "release-work/update-wheel/orion-$base-py3-none-any.whl" --output release-work/managed-backend
    python scripts/worker/portable.py --output release-work/update-worker
    python scripts/worker/portable.py --output release-work/update-worker --stage-desktop release-work/managed-backend --version $base --source-sha $Source
    $config = Join-Path $work 'orion-update-tauri.json'
    @{ version = $Version } | ConvertTo-Json | Set-Content -LiteralPath $config -Encoding utf8NoBOM
    Push-Location ui
    try {
        npm ci
        npm run desktop:build -- --ci --bundles nsis --no-sign --config $config
    } finally {
        Pop-Location
    }
    $name = "Orion_${Version}_x64-setup.exe"
    $target = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { 'ui/src-tauri/target' }
    $binary = Join-Path $target "release/bundle/nsis/$name"
    if (!(Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'NSIS output name does not match the release.' }
    if (git status --porcelain) { throw 'Build modified tracked source or generated untracked files.' }
    $out = New-Item -ItemType Directory -Path (Join-Path $work 'desktop-update')
    Copy-Item -LiteralPath $binary -Destination $out.FullName
    if ($Channel -eq 'preview') {
        @{
            source = $Source
            version = $Version
            signer = $SignerSha256.ToLowerInvariant()
            unsignedSha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out.FullName 'build.json') -Encoding utf8NoBOM
    }
} finally {
    Pop-Location
}
