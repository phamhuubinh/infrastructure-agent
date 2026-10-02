param(
    [string]$Prefix,
    [switch]$GlobalLauncher
)

$ErrorActionPreference = 'Stop'

function Invoke-Required {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable" }
}

function Test-Python {
    param([string]$Executable, [string[]]$Leading = @())
    try {
        & $Executable @Leading -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' *> $null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Test-PathEntry {
    param([string]$Entry, [string]$Directory)
    $expanded = [Environment]::ExpandEnvironmentVariables($Entry.Trim().Trim('"'))
    $trim = [char[]]@('\', '/')
    return $expanded.TrimEnd($trim) -ieq $Directory.TrimEnd($trim)
}

try {
    $bundle = [IO.Path]::GetFullPath($PSScriptRoot)
    $explicit = $PSBoundParameters.ContainsKey('Prefix')
    if ($explicit -and [string]::IsNullOrWhiteSpace($Prefix)) { throw '-Prefix requires a directory.' }
    if (-not $explicit) {
        $base = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath('LocalApplicationData') }
        $Prefix = Join-Path $base 'Orion\install'
    }
    $prefixPath = [IO.Path]::GetFullPath($Prefix)
    $venv = Join-Path $prefixPath '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $venvOrion = Join-Path $venv 'Scripts\orion.exe'

    $python = $null
    $leading = @()
    if ($env:ORION_PYTHON) {
        if (-not (Test-Python $env:ORION_PYTHON)) { throw 'ORION_PYTHON must be Python 3.12+.' }
        $python = $env:ORION_PYTHON
    } elseif (Test-Path -LiteralPath $venvPython) {
        if (-not (Test-Python $venvPython)) { throw 'Existing Orion environment requires Python 3.12+.' }
        $python = $venvPython
    } else {
        $py = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
        if ($py -and (Test-Python $py.Source @('-3.12'))) {
            $python = $py.Source
            $leading = @('-3.12')
        } elseif ($py -and (Test-Python $py.Source @('-3'))) {
            $python = $py.Source
            $leading = @('-3')
        } else {
            $fallback = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
            if ($fallback -and (Test-Python $fallback.Source)) { $python = $fallback.Source }
        }
    }
    if (-not $python) { throw 'Python 3.12 or newer is required; set ORION_PYTHON if necessary.' }
    Invoke-Required $python ($leading + @((Join-Path $bundle 'payload.py'), 'verify', '--root', $bundle, '--platform', 'windows-x64'))
    $manifest = Get-Content -LiteralPath (Join-Path $bundle 'release-manifest.json') -Raw | ConvertFrom-Json
    $wheel = Join-Path $bundle $manifest.wheel

    New-Item -ItemType Directory -Path $prefixPath -Force | Out-Null
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Invoke-Required $python ($leading + @('-m', 'venv', $venv))
    }
    if (-not (Test-Python $venvPython)) { throw 'Orion environment requires Python 3.12+.' }
    Invoke-Required $venvPython @('-m', 'pip', 'install', $wheel)
    $copyCode = 'import orion.ui_package,sys; from pathlib import Path; orion.ui_package.replace_ui_bundle(Path(sys.argv[1]),Path(sys.argv[2]))'
    Invoke-Required $venvPython @('-c', $copyCode, (Join-Path $bundle 'ui'), (Join-Path $prefixPath '.orion-ui'))
    Invoke-Required $venvOrion @('model', 'install', 'embeddings')

    if (-not $explicit -or $GlobalLauncher) {
        $base = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath('LocalApplicationData') }
        $launcherDir = Join-Path $base 'Orion\bin'
        $launcher = Join-Path $launcherDir 'orion.cmd'
        New-Item -ItemType Directory -Path $launcherDir -Force | Out-Null
        if (Test-Path -LiteralPath $launcher) {
            $first = [IO.File]::ReadLines($launcher) | Select-Object -First 1
            if ($first -cne '@REM Orion managed launcher') { throw "Refusing to overwrite unrelated launcher: $launcher" }
        }
        $escaped = $venvOrion.Replace('%', '%%')
        $content = "@REM Orion managed launcher`r`n@echo off`r`nsetlocal DisableDelayedExpansion`r`n`"$escaped`" %*`r`n"
        $temporary = Join-Path $launcherDir ('.orion-launcher-' + [Guid]::NewGuid().ToString('N') + '.cmd')
        try {
            [IO.File]::WriteAllText($temporary, $content, [Text.Encoding]::Default)
            if (Test-Path -LiteralPath $launcher) {
                # Pass a true null backup filename; PowerShell coerces $null to ''.
                [IO.File]::Replace($temporary, $launcher, [NullString]::Value)
            } else {
                [IO.File]::Move($temporary, $launcher)
            }
        } finally {
            if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        }
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        $entries = [Collections.Generic.List[string]]::new()
        $found = $false
        foreach ($entry in ($userPath -split ';')) {
            if (-not $entry.Trim()) { continue }
            if (Test-PathEntry $entry $launcherDir) {
                if ($found) { continue }
                $found = $true
            }
            $entries.Add($entry)
        }
        if (-not $found) { $entries.Add($launcherDir) }
        $updated = $entries -join ';'
        if ($updated -cne $userPath) { [Environment]::SetEnvironmentVariable('Path', $updated, 'User') }
        $env:PATH = (@($launcherDir) + @(($env:PATH -split ';') | Where-Object { $_.Trim() -and -not (Test-PathEntry $_ $launcherDir) })) -join ';'
        Write-Host "Installed Orion $($manifest.version). Run: orion"
    } else {
        Write-Host "Installed Orion $($manifest.version). Run: `"$venvOrion`""
    }
} catch {
    [Console]::Error.WriteLine("Orion installation failed: $($_.Exception.Message)")
    exit 1
}
