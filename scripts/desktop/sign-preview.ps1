[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Directory,
    [Parameter(Mandatory)][string]$Certificate,
    [Parameter(Mandatory)][string]$SignTool
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
. "$PSScriptRoot/preview-certificate.ps1"
$out = (Get-Item -LiteralPath $Directory).FullName
$build = Get-Content -LiteralPath (Join-Path $out 'build.json') -Raw | ConvertFrom-Json
if ($build.version -notmatch '^\d+\.\d+\.\d+$' -or $build.source -notmatch '^[a-f0-9]{40}$') {
    throw 'Invalid local Preview build record.'
}
$name = "Orion_$($build.version)_x64-setup.exe"
$installer = Join-Path $out $name
$file = Get-Item -LiteralPath $installer
if ($file.VersionInfo.ProductName -ne 'Orion' -or $file.VersionInfo.ProductVersion -ne $build.version -or
    (Get-FileHash -LiteralPath $installer).Hash -ne $build.unsignedSha256 -or
    (Get-AuthenticodeSignature -LiteralPath $installer).Status -ne 'NotSigned') {
    throw 'Expected the original unsigned NSIS from the build record.'
}
$preview = Get-OrionPreviewCertificate ([IO.File]::ReadAllBytes((Get-Item -LiteralPath $Certificate).FullName)) $build.signer
try {
    $key = Get-Item -LiteralPath "Cert:\CurrentUser\My\$($preview.Thumbprint)" -ErrorAction SilentlyContinue
    if (!$key -or !$key.HasPrivateKey) { throw 'Unlock the existing Preview signing key in CurrentUser\My.' }
    $tool = (Get-Item -LiteralPath $SignTool).FullName
    $candidate = Join-Path $out ('signing-' + [guid]::NewGuid() + '.exe')
    Copy-Item -LiteralPath $installer -Destination $candidate
    try {
        & $tool sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com /sha1 $preview.Thumbprint $candidate
        $signature = Get-AuthenticodeSignature -LiteralPath $candidate
        if (!$signature.TimeStamperCertificate -or
            $signature.SignerCertificate.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $build.signer) {
            throw 'Expected the pinned Preview signature and timestamp.'
        }
        Move-Item -LiteralPath $candidate -Destination $installer -Force
    } finally {
        if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate }
    }
} finally {
    $preview.Dispose()
}
$digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $out 'DESKTOP-SHA256SUMS'), "$digest  $name`n")
Write-Output "$digest  $installer"
