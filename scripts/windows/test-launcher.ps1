param([string]$Repository = (Split-Path (Split-Path $PSScriptRoot)))

$ErrorActionPreference = 'Stop'
$originalLocalAppData = $env:LOCALAPPDATA
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('orion launcher test ' + [Guid]::NewGuid().ToString('N'))
try {
    foreach ($installer in @('install.ps1', 'scripts/release/install.ps1')) {
        $tokens = $null
        $errors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $Repository $installer), [ref]$tokens, [ref]$errors
        )
        if ($errors.Count) { throw ($errors | Out-String) }

        # Execute the actual launcher filesystem statements from each installer.
        # Stop before PATH handling, so no user registry state or dependency/model
        # installation is involved in these deterministic regression tests.
        if ($installer -eq 'install.ps1') {
            $function = $ast.Find({ param($node)
                $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Install-Launcher'
            }, $true)
            $statements = $function.Body.EndBlock.Statements
        } else {
            $block = $ast.Find({ param($node)
                $node -is [Management.Automation.Language.IfStatementAst] -and
                $node.Clauses[0].Item1.Extent.Text -eq '-not $explicit -or $GlobalLauncher'
            }, $true)
            $statements = $block.Clauses[0].Item2.Statements
        }
        $filesystem = @()
        $foundPathBoundary = $false
        foreach ($statement in $statements) {
            if ($statement -is [Management.Automation.Language.AssignmentStatementAst] -and
                $statement.Left.Extent.Text -eq '$userPath') {
                $foundPathBoundary = $true
                break
            }
            $filesystem += $statement.Extent.Text
        }
        if (-not $foundPathBoundary) { throw "Missing launcher/PATH boundary in $installer" }
        $writeLauncher = [scriptblock]::Create($filesystem -join "`n")

        $env:LOCALAPPDATA = Join-Path $testRoot ($installer.Replace('/', '-'))
        $launcherDirectory = Join-Path $env:LOCALAPPDATA 'Orion\bin'
        $launcher = Join-Path $launcherDirectory 'orion.cmd'
        $OrionExecutable = Join-Path $testRoot 'first install with spaces\.venv\Scripts\orion.exe'
        $venvOrion = $OrionExecutable
        & $writeLauncher
        $first = [IO.File]::ReadAllText($launcher)
        if (-not $first.StartsWith("@REM Orion managed launcher`r`n")) { throw "First install failed: $installer" }
        if (-not $first.Contains('"' + $OrionExecutable + '" %*')) { throw "Wrong launcher target: $installer" }

        & $writeLauncher
        if ([IO.File]::ReadAllText($launcher) -cne $first) { throw "Rerun changed launcher content: $installer" }

        # A changed target proves the existing file was replaced, rather than
        # silently skipped when it already existed.
        $OrionExecutable = Join-Path $testRoot 'replacement install with spaces\.venv\Scripts\orion.exe'
        $venvOrion = $OrionExecutable
        & $writeLauncher
        $replaced = [IO.File]::ReadAllText($launcher)
        if (-not $replaced.Contains('"' + $OrionExecutable + '" %*') -or $replaced -ceq $first) {
            throw "Managed launcher was not replaced: $installer"
        }

        # Ownership remains exact and case-sensitive, including near matches.
        foreach ($unrelated in @("@REM unrelated launcher`r`nkeep me`r`n", "@rem Orion managed launcher`r`n", '')) {
            [IO.File]::WriteAllText($launcher, $unrelated)
            $refused = $false
            try { & $writeLauncher } catch {
                if ($_.Exception.Message -notlike '*Refusing to overwrite unrelated launcher*') { throw }
                $refused = $true
            }
            if (-not $refused -or [IO.File]::ReadAllText($launcher) -cne $unrelated) {
                throw "Unrelated launcher was not preserved: $installer"
            }
        }
        if (@(Get-ChildItem -LiteralPath $launcherDirectory -Filter '.orion-launcher-*.cmd').Count) {
            throw "Temporary launcher was left behind: $installer"
        }
        Write-Host "PASS: $installer first install, rerun, replacement, unrelated launcher refusal"
    }
} finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
