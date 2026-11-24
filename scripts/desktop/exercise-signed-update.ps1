param([Parameter(Mandatory = $true)][string]$Installer)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if ($env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'Use a disposable GitHub-hosted runner.' }
$installation = Join-Path $env:LOCALAPPDATA 'Orion'
$applicationData = Join-Path $env:LOCALAPPDATA 'io.orion.desktop'
if ((Test-Path -LiteralPath $installation) -or (Test-Path -LiteralPath $applicationData) -or
    (Get-Process Orion,OrionBackend -ErrorAction SilentlyContinue)) {
    throw 'The release exercise requires a fresh runner profile.'
}
$initial = Start-Process -FilePath $Installer -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
if ($initial.ExitCode -ne 0) { throw 'Initial fixture install failed.' }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'backend/src').Path
python scripts/desktop/signed_update_fixture.py
$exe = Join-Path $installation 'Orion.exe'
$sidecar = Join-Path $installation 'backend/OrionBackend.exe'
$source = Get-Content -LiteralPath 'ui/src-tauri/src/updates.rs' -Raw
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
    python scripts/desktop/signed_update_fixture.py --verify-receipt $receipt
}
