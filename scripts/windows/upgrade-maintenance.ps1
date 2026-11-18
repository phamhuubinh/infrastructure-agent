param(
    [switch]$MaintenanceWindow,
    [string]$Python = 'F:/Orion-toolchains/refactor-python/Scripts/python.exe'
)
$ErrorActionPreference = 'Stop'
if (!$MaintenanceWindow) { throw 'PENDING_MANUAL: start only in an agreed maintenance window.' }
if (Get-Process Orion,OrionBackend -ErrorAction SilentlyContinue) {
    throw 'PENDING_MANUAL: stop Orion Host cleanly before proceeding.'
}
if (Get-NetTCPConnection -LocalPort 61888 -State Listen -ErrorAction SilentlyContinue) {
    throw 'The Host port is still occupied.'
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$package = Join-Path $repo 'release-work/acceptance-fdfcb15'
$setup = Join-Path $package 'Orion_0.1.5_x64_fdfcb15-preview-setup.exe'
$expected = '9B56E4FFDFB7606EE4F3FF437C91CBC647F61702D4666BDA5442C82DE9A2E24C'
if ((Get-FileHash -LiteralPath $setup).Hash -ne $expected) { throw 'Installer checksum mismatch.' }
$previousPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo 'backend/src'
    $result = & $Python (Join-Path $PSScriptRoot 'upgrade_readiness.py') --snapshot (Join-Path $env:LOCALAPPDATA 'OrionRecovery')
    if ($LASTEXITCODE -ne 0) { throw 'Maintenance snapshot failed. Installation has not started.' }
    $match = [regex]::Match(($result -join "`n"), 'PASS private snapshot and isolated rollback drill: (.+)')
    if (!$match.Success) { throw 'Could not locate the validated maintenance snapshot.' }
    $backup = $match.Groups[1].Value.Trim()
    Write-Output "Validated backup at $backup"
    if (Get-Process Orion,OrionBackend -ErrorAction SilentlyContinue) { throw 'Orion started during backup.' }
    if (Get-NetTCPConnection -LocalPort 61888 -State Listen -ErrorAction SilentlyContinue) {
        throw 'The Host port became occupied during backup.'
    }
    $process = Start-Process -FilePath $setup -ArgumentList '/S' -PassThru -WindowStyle Hidden
    if (!$process.WaitForExit(120000)) { throw 'NSIS is still running. Inspect it before continuing.' }
    if ($process.ExitCode -ne 0) { throw "NSIS returned $($process.ExitCode). Keep the backup for rollback." }
    & $Python (Join-Path $PSScriptRoot 'upgrade_acceptance.py') --backup $backup --payload (Join-Path $package 'extracted')
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance failed. Keep Orion stopped and follow the rollback procedure.' }
    Write-Output 'PASS pre-launch upgrade checks. PENDING_MANUAL: open Orion and verify Owner-authenticated clients.'
} finally {
    $env:PYTHONPATH = $previousPath
}
