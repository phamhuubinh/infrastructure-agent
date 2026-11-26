[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Installer,
    [Parameter(Mandatory)][string]$Certificate,
    [Parameter(Mandatory)][string]$SignerSha256,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$InstallerSha256,
    [switch]$TrustPreviewCertificate
)

$ErrorActionPreference = 'Stop'
if (!$IsWindows) { throw 'Use PowerShell 7 on Windows.' }
. "$PSScriptRoot/preview-certificate.ps1"
$file = Get-Item -LiteralPath $Installer
if ($file.Name -notmatch '^Orion_(\d+\.\d+\.\d+)_x64-setup\.exe$') { throw 'Unexpected Orion NSIS filename.' }
$version = $Matches[1]
if ($file.VersionInfo.ProductName -ne 'Orion' -or $file.VersionInfo.ProductVersion -ne $version -or
    (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne $InstallerSha256) {
    throw 'The installer does not match the approved release version or SHA-256.'
}
$installed = Join-Path $env:LOCALAPPDATA 'Orion/Orion.exe'
if ((Test-Path -LiteralPath $installed -PathType Leaf) -and
    [version]$version -le [version](Get-Item -LiteralPath $installed).VersionInfo.ProductVersion) {
    throw 'Select a Preview newer than the installed Orion.'
}
$cert = Get-OrionPreviewCertificate ([IO.File]::ReadAllBytes((Get-Item -LiteralPath $Certificate).FullName)) $SignerSha256
$store = $null
$added = $false
try {
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if (!$signature.SignerCertificate -or
        $signature.SignerCertificate.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $SignerSha256) {
        throw 'The installer does not use the approved Preview publisher.'
    }
    if ($TrustPreviewCertificate) {
        $store = [Security.Cryptography.X509Certificates.X509Store]::new('Root', 'CurrentUser')
        $store.Open('ReadWrite')
        if ($store.Certificates.Find('FindByThumbprint', $cert.Thumbprint, $false).Count -eq 0) {
            $store.Add($cert)
            $added = $true
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    }
    if ($signature.Status -ne 'Valid' -or !$signature.TimeStamperCertificate -or
        $signature.SignerCertificate.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $SignerSha256 -or
        (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne $InstallerSha256) {
        throw "Authenticode verification failed: $($signature.Status)."
    }
    Write-Output "PASS Orion Preview $version ($($file.FullName))"
} catch {
    if ($added) { $store.Remove($cert) }
    throw
} finally {
    if ($store) { $store.Dispose() }
    $cert.Dispose()
}
