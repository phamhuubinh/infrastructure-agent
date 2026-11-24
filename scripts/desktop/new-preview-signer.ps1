# Run interactively under the key custodian's Windows account with PowerShell 7.
[CmdletBinding()]
param([securestring]$Password)

$ErrorActionPreference = 'Stop'
if (!$IsWindows -or !$env:LOCALAPPDATA) { throw 'Use PowerShell 7 on Windows.' }
if (!$Password) { $Password = Read-Host 'Mật khẩu mạnh và riêng cho PFX (tối thiểu 24 ký tự)' -AsSecureString }
if ($Password.Length -lt 24) { throw 'Use a unique PFX password of at least 24 characters.' }

$directory = Join-Path $env:LOCALAPPDATA ('OrionSigning/preview-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $directory
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = Get-Acl -LiteralPath $directory
$acl.SetAccessRuleProtection($true, $false)
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $sid, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow'))
Set-Acl -LiteralPath $directory -AclObject $acl

$rsa = [Security.Cryptography.RSA]::Create(3072)
$cert = $null
$pfx = $null
try {
    $request = [Security.Cryptography.X509Certificates.CertificateRequest]::new(
        'CN=Orion Personal Preview', $rsa,
        [Security.Cryptography.HashAlgorithmName]::SHA256,
        [Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $true))
    $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new('DigitalSignature', $true))
    $usage = [Security.Cryptography.OidCollection]::new()
    $null = $usage.Add([Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.3'))
    $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($usage, $true))
    $now = [DateTimeOffset]::UtcNow
    $cert = $request.CreateSelfSigned($now.AddMinutes(-5), $now.AddYears(2))
    $pfx = $cert.Export('Pfx', $Password)
    [IO.File]::WriteAllBytes((Join-Path $directory 'OrionPreview.pfx'), $pfx)
    [IO.File]::WriteAllBytes((Join-Path $directory 'OrionPreview.cer'), $cert.RawData)
    $fingerprint = $cert.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256)
    [IO.File]::WriteAllText((Join-Path $directory 'ORION_UPDATE_SIGNER_SHA256.txt'), $fingerprint)
    Write-Output $directory
} finally {
    if ($pfx) { [Array]::Clear($pfx) }
    if ($cert) { $cert.Dispose() }
    $rsa.Dispose()
}
