$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if ($env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'Use a disposable GitHub-hosted runner.' }
if (!$env:ORION_SIGNING_PFX_B64 -or !$env:ORION_SIGNING_PFX_PASSWORD) { throw 'The desktop signing environment is not provisioned.' }
if ($env:ORION_RELEASE_CHANNEL -notin @('preview', 'stable')) { throw 'An explicit release channel is required.' }
if ($env:ORION_PREVIEW_CERT_B64 -and $env:ORION_RELEASE_CHANNEL -ne 'preview') { throw 'Private Preview trust is restricted to Preview.' }
. "$PSScriptRoot/preview-certificate.ps1"
$out = (Resolve-Path -LiteralPath 'release-work/desktop-update').Path
$name = "Orion_${env:ORION_DESKTOP_VERSION}_x64-setup.exe"
$installer = Join-Path $out $name
$pfx = Join-Path $env:RUNNER_TEMP ('orion-' + [guid]::NewGuid() + '.pfx')
$cert = $null
$preview = $null
$trust = $null
$trustAdded = $false
try {
    if ($env:ORION_PREVIEW_CERT_B64) {
        $preview = Get-OrionPreviewCertificate ([Convert]::FromBase64String($env:ORION_PREVIEW_CERT_B64)) $env:ORION_UPDATE_SIGNER_SHA256
    }
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:ORION_SIGNING_PFX_B64))
    $password = ConvertTo-SecureString -String $env:ORION_SIGNING_PFX_PASSWORD -AsPlainText -Force
    $leaf = @((Get-PfxData -FilePath $pfx -Password $password).EndEntityCertificates)
    if ($leaf.Count -ne 1 -or
        $leaf[0].GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $env:ORION_UPDATE_SIGNER_SHA256) {
        throw 'Signing certificate does not match the configured publisher pin.'
    }
    $cert = @(Import-PfxCertificate -FilePath $pfx -Password $password -CertStoreLocation 'Cert:\CurrentUser\My' |
        Where-Object HasPrivateKey)
    if ($cert.Count -ne 1 -or $cert[0].Thumbprint -ne $leaf[0].Thumbprint) {
        throw 'The signing PFX must contain one private key for the pinned publisher.'
    }
    $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin'
    $signTool = Get-ChildItem -Path "$kits/*/x64/signtool.exe" | Sort-Object FullName -Descending | Select-Object -First 1
    if (!$signTool) { throw 'Windows SDK SignTool is unavailable.' }
    & $signTool.FullName sign /fd SHA256 /td SHA256 /tr https://timestamp.digicert.com /sha1 $cert[0].Thumbprint $installer
    Remove-Item -LiteralPath $pfx
    Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($cert[0].Thumbprint)" -DeleteKey
    $cert = $null
    Remove-Item Env:ORION_SIGNING_PFX_B64,Env:ORION_SIGNING_PFX_PASSWORD
    if ($preview) {
        # The hosted job is administrative and disposable. Its machine store avoids an interactive user-root prompt.
        $trust = [Security.Cryptography.X509Certificates.X509Store]::new('Root', 'LocalMachine')
        $trust.Open('ReadWrite')
        if ($trust.Certificates.Find('FindByThumbprint', $preview.Thumbprint, $false).Count -ne 0) {
            throw 'Expected a fresh runner without the Preview certificate in its trust store.'
        }
        $trust.Add($preview)
        $trustAdded = $true
    }
    & $signTool.FullName verify /pa $installer
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or !$signature.TimeStamperCertificate -or
        $signature.SignerCertificate.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $env:ORION_UPDATE_SIGNER_SHA256) {
        throw 'The signed installer did not pass Windows trust and publisher verification.'
    }
    $digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
    & "$PSScriptRoot/exercise-signed-update.ps1" -Installer $installer
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $digest) {
        throw 'The installer changed during the Windows release exercise.'
    }
} finally {
    if ($trust) {
        try { if ($trustAdded) { $trust.Remove($preview) } }
        finally { $trust.Dispose() }
    }
    if ($preview) { $preview.Dispose() }
    if (Test-Path -LiteralPath $pfx) { Remove-Item -LiteralPath $pfx }
    foreach ($imported in $cert) { Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($imported.Thumbprint)" -DeleteKey }
    Remove-Item Env:ORION_SIGNING_PFX_B64,Env:ORION_SIGNING_PFX_PASSWORD -ErrorAction SilentlyContinue
}
[IO.File]::WriteAllText((Join-Path $out 'DESKTOP-SHA256SUMS'), "$($digest.ToLowerInvariant())  $name`n", [Text.UTF8Encoding]::new($false))
