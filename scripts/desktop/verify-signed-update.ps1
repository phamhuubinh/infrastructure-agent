$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if ($env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'Use a disposable GitHub-hosted runner.' }
if (!$env:ORION_SIGNING_PFX_B64 -or !$env:ORION_SIGNING_PFX_PASSWORD) { throw 'The desktop signing environment is not provisioned.' }
$out = (Resolve-Path -LiteralPath 'release-work/desktop-update').Path
$name = "Orion_${env:ORION_DESKTOP_VERSION}_x64-setup.exe"
$installer = Join-Path $out $name
$pfx = Join-Path $env:RUNNER_TEMP ('orion-' + [guid]::NewGuid() + '.pfx')
$cert = $null
try {
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:ORION_SIGNING_PFX_B64))
    $password = ConvertTo-SecureString -String $env:ORION_SIGNING_PFX_PASSWORD -AsPlainText -Force
    $cert = @(Import-PfxCertificate -FilePath $pfx -Password $password -CertStoreLocation 'Cert:\CurrentUser\My' |
        Where-Object { $_.HasPrivateKey -and $_.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -eq $env:ORION_UPDATE_SIGNER_SHA256 })
    if ($cert.Count -ne 1) { throw 'Signing certificate does not match the configured publisher pin.' }
    $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin'
    $signTool = Get-ChildItem -Path "$kits/*/x64/signtool.exe" | Sort-Object FullName -Descending | Select-Object -First 1
    if (!$signTool) { throw 'Windows SDK SignTool is unavailable.' }
    & $signTool.FullName sign /fd SHA256 /td SHA256 /tr https://timestamp.digicert.com /sha1 $cert[0].Thumbprint $installer
    & $signTool.FullName verify /pa $installer
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or
        $signature.SignerCertificate.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $env:ORION_UPDATE_SIGNER_SHA256) {
        throw 'The signed installer did not pass Windows trust and publisher verification.'
    }
} finally {
    if (Test-Path -LiteralPath $pfx) { Remove-Item -LiteralPath $pfx }
    if ($cert.Count -eq 1) { Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($cert[0].Thumbprint)" }
    Remove-Item Env:ORION_SIGNING_PFX_B64,Env:ORION_SIGNING_PFX_PASSWORD -ErrorAction SilentlyContinue
}
& ./scripts/desktop/exercise-signed-update.ps1 -Installer $installer
$digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $out 'DESKTOP-SHA256SUMS'), "$digest  $name`n", [Text.UTF8Encoding]::new($false))
