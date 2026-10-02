param([switch]$ParseOnly)

$ErrorActionPreference = 'Stop'
if ($ParseOnly) {
    foreach ($path in @('install.ps1', 'scripts/release/install.ps1', 'scripts/windows/installer-check.ps1', 'scripts/windows/test-launcher.ps1')) {
        $tokens = $null
        $errors = $null
        [Management.Automation.Language.Parser]::ParseFile(
            (Join-Path (Split-Path (Split-Path $PSScriptRoot)) $path),
            [ref]$tokens, [ref]$errors
        ) | Out-Null
        if ($errors.Count) { throw ($errors | Out-String) }
        Write-Host "Parsed $path"
    }
    exit 0
}

# The Python parent also snapshots/restores the registry value in case an
# installer exits this PowerShell process before finally can finish.
$originalUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$launcherDir = Join-Path $env:LOCALAPPDATA 'Orion\bin'
$sentinel = Join-Path $env:LOCALAPPDATA 'unrelated path'
$duplicates = "$sentinel;`"$launcherDir\`";$($launcherDir.ToUpperInvariant());%LOCALAPPDATA%\Orion\bin\"
try {
    [Environment]::SetEnvironmentVariable('Path', $duplicates, 'User')
    $env:PATH = "$duplicates;$env:PATH"
    $options = @{ Prefix = $env:ORION_SMOKE_PREFIX; GlobalLauncher = $true }
    if ($env:ORION_SMOKE_SOURCE -eq '1') { $options.NoDev = $true }
    $LASTEXITCODE = 0
    . $env:ORION_SMOKE_INSTALLER @options
    if ($LASTEXITCODE -ne 0) { throw "Installer failed with exit code $LASTEXITCODE" }

    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $matches = @($userPath -split ';' | Where-Object {
        [Environment]::ExpandEnvironmentVariables($_.Trim().Trim('"')).TrimEnd('\', '/') -ieq $launcherDir
    })
    if ($matches.Count -ne 1) { throw 'User PATH was not deduplicated.' }
    if (($userPath -split ';')[0] -cne $sentinel) { throw 'Unrelated user PATH entry changed.' }
    $processMatches = @($env:PATH -split ';' | Where-Object {
        [Environment]::ExpandEnvironmentVariables($_.Trim().Trim('"')).TrimEnd('\', '/') -ieq $launcherDir
    })
    if ($processMatches.Count -ne 1 -or ($env:PATH -split ';')[0] -cne $launcherDir) {
        throw 'Current-process PATH was not updated/deduplicated.'
    }
    $resolved = Get-Command orion.cmd -CommandType Application
    if ($resolved.Source -ine (Join-Path $launcherDir 'orion.cmd')) { throw 'Wrong launcher resolved.' }
    & $resolved.Source help
    if ($LASTEXITCODE -ne 0) { throw 'Managed launcher help failed.' }
    Write-Host 'PASS: native installer, user/process PATH, launcher help'
} finally {
    [Environment]::SetEnvironmentVariable('Path', $originalUserPath, 'User')
}
