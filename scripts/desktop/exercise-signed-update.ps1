[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Installer,
    [switch]$DisposableGuest,
    [string]$Certificate,
    [string]$Evidence
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$hosted = $env:RUNNER_ENVIRONMENT -eq 'github-hosted'
if (!$hosted -and (!$DisposableGuest -or !$Certificate -or !$Evidence)) {
    throw 'Run in a disposable Windows guest with the public Preview CER and an evidence path.'
}
$installation = Join-Path $env:LOCALAPPDATA 'Orion'
$applicationData = Join-Path $env:LOCALAPPDATA 'io.orion.desktop'
if ((Test-Path -LiteralPath $installation) -or (Test-Path -LiteralPath $applicationData) -or
    (Test-Path -LiteralPath 'HKCU:/Software/Orion/DesktopHost') -or
    (Get-Process Orion,OrionBackend,tailscale,tailscaled -ErrorAction SilentlyContinue)) {
    throw 'The release exercise requires a fresh profile without Orion or Tailscale.'
}
$repo = (Resolve-Path -LiteralPath "$PSScriptRoot/../..").Path
$Installer = (Get-Item -LiteralPath $Installer).FullName
if (!$hosted) {
    $out = Split-Path -Parent $Installer
    $build = Get-Content -LiteralPath (Join-Path $out 'build.json') -Raw | ConvertFrom-Json
    if ($build.source -cne (git -C $repo rev-parse HEAD).Trim() -or (git -C $repo status --porcelain) -or
        (Split-Path -Leaf $Installer) -cne "Orion_$($build.version)_x64-setup.exe" -or
        (Test-Path -LiteralPath $Evidence)) {
        throw 'Use the exact clean release commit, its signed installer, and a new evidence path.'
    }
    $checksum = Get-Content -LiteralPath (Join-Path $out 'DESKTOP-SHA256SUMS') -Raw
    if ($checksum.TrimEnd("`r", "`n") -cnotmatch '^([a-f0-9]{64})  (Orion_\d+\.\d+\.\d+_x64-setup\.exe)$' -or
        $Matches[2] -cne (Split-Path -Leaf $Installer)) { throw 'Invalid installer checksum file.' }
    $approvedHash = $Matches[1]
    & "$PSScriptRoot/test-preview-bootstrap.ps1" -Installer $Installer -Certificate $Certificate `
        -SignerSha256 $build.signer -InstallerSha256 $approvedHash -TrustPreviewCertificate
    $env:ORION_DESKTOP_VERSION = $build.version
    $env:ORION_UPDATE_SIGNER_SHA256 = $build.signer
    $env:ORION_DISPOSABLE_UPDATE_FIXTURE = '1'
}

$initial = Start-Process -FilePath $Installer -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
if ($initial.ExitCode -ne 0) { throw 'Initial fixture install failed.' }
$env:PYTHONPATH = (Join-Path $repo 'backend/src')
python "$PSScriptRoot/signed_update_fixture.py"
$exe = Join-Path $installation 'Orion.exe'
$sidecar = Join-Path $installation 'backend/OrionBackend.exe'
$source = Get-Content -LiteralPath (Join-Path $repo 'ui/src-tauri/src/updates.rs') -Raw
$verify = [regex]::Match($source, '(?s)const CHECK_SIGNATURE: &str = r#"(.*?)"#;').Groups[1].Value
$handoff = [regex]::Match($source, '(?s)const HANDOFF: &str = r#"(.*?)"#;').Groups[1].Value
if (!$verify -or !$handoff) { throw 'Missing production update handoff scripts.' }
$windowsPowerShell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$env:ORION_UPDATE_EXE = $exe
$env:ORION_UPDATE_PARENT = '2147483647'
$env:ORION_UPDATE_VERIFY = $verify
$env:ORION_UPDATE_VERSION = $env:ORION_DESKTOP_VERSION
$env:ORION_UPDATE_SIGNER = $env:ORION_UPDATE_SIGNER_SHA256
$env:ORION_UPDATE_HASH = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash
$env:ORION_UPDATE_ACTIVE = Join-Path $applicationData 'update-active.txt'

function Stop-Fixture {
    foreach ($process in @(Get-Process Orion -ErrorAction SilentlyContinue)) {
        if ($process.Path -ne $exe) { throw 'Unexpected Orion process on clean runner.' }
        $deadline = [DateTime]::UtcNow.AddSeconds(15)
        while (!$process.CloseMainWindow() -and !$process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 100
        }
        if (!$process.WaitForExit(18000)) { throw 'Fixture window did not stop cleanly.' }
    }
}

foreach ($scenario in @('Installed', 'Rolled back')) {
    $directory = Join-Path $applicationData ('update-' + [guid]::NewGuid())
    $null = New-Item -ItemType Directory -Path $directory
    $receipt = Join-Path $directory 'snapshot.json'
    $env:ORION_UPDATE_FILE = Join-Path $directory 'OrionSetup.exe'
    Copy-Item -LiteralPath $Installer -Destination $env:ORION_UPDATE_FILE
    $snapshot = Start-Process -FilePath $sidecar -ArgumentList "--snapshot-for-update `"$installation`" `"$receipt`" client" -Wait -PassThru -WindowStyle Hidden
    if ($snapshot.ExitCode -ne 0) { throw 'The exact frozen snapshot helper failed.' }
    if ($scenario -eq 'Rolled back') {
        # Inject failure on this disposable copy so the new sidecar cannot reach health.
        [IO.File]::WriteAllText((Join-Path $applicationData 'managed/orion.db'), 'injected test failure')
    }
    [IO.File]::WriteAllText($env:ORION_UPDATE_ACTIVE, (Split-Path -Leaf $directory))
    & $windowsPowerShell -NoLogo -NoProfile -NonInteractive -Command $handoff
    $actual = (Get-Content -LiteralPath (Join-Path $directory 'outcome.txt') -Raw).Trim()
    if ($actual -ne $scenario) { throw "Update outcome was '$actual'. Expected '$scenario'." }
    Stop-Fixture
    python "$PSScriptRoot/signed_update_fixture.py" --verify-receipt $receipt
}

if (!$hosted) {
    if ((Get-FileHash -LiteralPath $Installer).Hash -ne $approvedHash) { throw 'The accepted installer changed.' }
    [ordered]@{
        source = $build.source
        version = $build.version
        signer = $build.signer
        sha256 = $approvedHash
        outcomes = @('Installed', 'Rolled back')
    } | ConvertTo-Json | Set-Content -LiteralPath $Evidence -Encoding utf8NoBOM
}
