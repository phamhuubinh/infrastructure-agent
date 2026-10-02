param(
    [string]$Prefix,
    [switch]$NoDev,
    [switch]$GlobalLauncher
)

$ErrorActionPreference = 'Stop'

function Invoke-RequiredCommand {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$Failure
    )

    try {
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Exit code $LASTEXITCODE."
        }
    } catch {
        throw "${Failure} $($_.Exception.Message)"
    }
}

function Test-PythonVersion {
    param([string]$Executable, [string[]]$LeadingArguments = @())

    try {
        & $Executable @LeadingArguments -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Test-PathEntryMatchesDirectory {
    param([string]$Entry, [string]$Directory)

    $expanded = [Environment]::ExpandEnvironmentVariables($Entry.Trim().Trim([char[]]@('"')))
    return ($expanded.TrimEnd([char[]]@('\', '/')) -ieq $Directory.TrimEnd([char[]]@('\', '/')))
}

function Install-Launcher {
    param([string]$OrionExecutable)

    $localAppData = $env:LOCALAPPDATA
    if (-not $localAppData) {
        $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    }
    if (-not $localAppData) {
        throw 'LOCALAPPDATA is unavailable; cannot create the user-owned Orion launcher.'
    }

    $launcherDirectory = Join-Path $localAppData 'Orion\bin'
    $launcher = Join-Path $launcherDirectory 'orion.cmd'
    New-Item -ItemType Directory -Path $launcherDirectory -Force | Out-Null
    if (Test-Path -LiteralPath $launcher) {
        $firstLine = [IO.File]::ReadLines($launcher) | Select-Object -First 1
        if ($firstLine -cne '@REM Orion managed launcher') {
            throw "Refusing to overwrite unrelated launcher: $launcher. Move it aside or use a custom -Prefix without -GlobalLauncher."
        }
    }

    $escapedExecutable = $OrionExecutable.Replace('%', '%%')
    $content = "@REM Orion managed launcher`r`n@echo off`r`nsetlocal DisableDelayedExpansion`r`n`"$escapedExecutable`" %*`r`n"
    $temporary = Join-Path $launcherDirectory ('.orion-launcher-' + [Guid]::NewGuid().ToString('N') + '.cmd')
    try {
        [IO.File]::WriteAllText($temporary, $content, [Text.Encoding]::Default)
        if (Test-Path -LiteralPath $launcher) {
            # Pass a true null backup filename; PowerShell coerces $null to ''.
            [IO.File]::Replace($temporary, $launcher, [NullString]::Value)
        } else {
            [IO.File]::Move($temporary, $launcher)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }

    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $userEntries = [Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($entry in ($userPath -split ';')) {
        if (-not $entry.Trim()) { continue }
        if (Test-PathEntryMatchesDirectory $entry $launcherDirectory) {
            if ($found) { continue }
            $found = $true
        }
        $userEntries.Add($entry)
    }
    if (-not $found) { $userEntries.Add($launcherDirectory) }
    $updatedUserPath = $userEntries -join ';'
    if ($updatedUserPath -cne $userPath) {
        [Environment]::SetEnvironmentVariable('Path', $updatedUserPath, 'User')
    }
    $processEntries = [Collections.Generic.List[string]]::new()
    foreach ($entry in ($env:PATH -split ';')) {
        if ($entry.Trim() -and -not (Test-PathEntryMatchesDirectory $entry $launcherDirectory)) {
            $processEntries.Add($entry)
        }
    }
    $env:PATH = (@($launcherDirectory) + $processEntries.ToArray()) -join ';'
}

try {
    $sourceRoot = [IO.Path]::GetFullPath($PSScriptRoot)
    $prefixWasExplicit = $PSBoundParameters.ContainsKey('Prefix')
    if ($prefixWasExplicit -and [string]::IsNullOrWhiteSpace($Prefix)) {
        throw '-Prefix requires a directory.'
    }
    $installPrefix = if ($prefixWasExplicit) { [IO.Path]::GetFullPath($Prefix) } else { $sourceRoot }
    New-Item -ItemType Directory -Path $installPrefix -Force | Out-Null
    $venv = Join-Path $installPrefix '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $venvOrion = Join-Path $venv 'Scripts\orion.exe'

    $pythonExecutable = $null
    $pythonLeadingArguments = @()
    if ($env:ORION_PYTHON) {
        if (-not (Test-PythonVersion $env:ORION_PYTHON)) {
            throw 'Python 3.12 or newer is required. ORION_PYTHON does not point to a working Python 3.12+ interpreter.'
        }
        $pythonExecutable = $env:ORION_PYTHON
    } elseif (Test-Path -LiteralPath $venvPython) {
        if (-not (Test-PythonVersion $venvPython)) {
            throw "Python 3.12 or newer is required. Existing virtual environment is too old or broken: $venvPython. Replace that environment or choose another -Prefix."
        }
        $pythonExecutable = $venvPython
    } else {
        $launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
        if ($launcher -and (Test-PythonVersion $launcher.Source @('-3.12'))) {
            $pythonExecutable = $launcher.Source
            $pythonLeadingArguments = @('-3.12')
        } else {
            $fallback = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
            if ($fallback -and (Test-PythonVersion $fallback.Source)) {
                $pythonExecutable = $fallback.Source
            }
        }
    }
    if (-not $pythonExecutable) {
        throw 'Python 3.12 or newer is required. Set ORION_PYTHON, install Python 3.12+, or create a supported .venv.'
    }

    $node = Get-Command node -CommandType Application -ErrorAction SilentlyContinue
    $npm = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue
    if (-not $npm) {
        $npm = Get-Command npm -CommandType Application -ErrorAction SilentlyContinue
    }
    if (-not $node -or -not $npm) {
        throw "Node.js >=22.12 and npm are required to build Orion's packaged UI. Install both and retry."
    }
    $nodeVersion = (& $node.Source --version | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(\d+)\.(\d+)\.') {
        throw "Node.js >=22.12 is required to build Orion's packaged UI (found $nodeVersion)."
    }
    if ([int]$Matches[1] -lt 22 -or ([int]$Matches[1] -eq 22 -and [int]$Matches[2] -lt 12)) {
        throw "Node.js >=22.12 is required to build Orion's packaged UI (found $nodeVersion)."
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Invoke-RequiredCommand $pythonExecutable ($pythonLeadingArguments + @('-m', 'venv', $venv)) 'Could not create the Orion virtual environment.'
    }
    if (-not (Test-PythonVersion $venvPython)) {
        throw "Python 3.12 or newer is required in the Orion virtual environment: $venvPython"
    }

    $backend = Join-Path $sourceRoot 'backend'
    $package = if ($NoDev) { $backend } else { $backend + '[dev]' }
    Invoke-RequiredCommand $venvPython @('-m', 'pip', 'install', '-e', $package) 'Could not install the Orion backend.'
    Invoke-RequiredCommand $venvPython @('-m', 'orion.ui_package', '--repository', $sourceRoot, '--destination', (Join-Path $installPrefix '.orion-ui'), '--npm-ci') 'Could not build and package the Orion UI. Check Node.js and npm.'
    Invoke-RequiredCommand $venvOrion @('model', 'install', 'embeddings') 'Could not provision the pinned embeddings model. Check network access and retry.'

    if (-not $prefixWasExplicit -or $GlobalLauncher) {
        Install-Launcher $venvOrion
        Write-Host "Installed Orion in $venv. Run: orion"
    } else {
        Write-Host "Installed Orion in $venv. Run: `"$venvOrion`""
        Write-Host 'A custom -Prefix does not change your user launcher; add -GlobalLauncher to manage it.'
    }
} catch {
    [Console]::Error.WriteLine("Orion installation failed: $($_.Exception.Message)")
    exit 1
}
