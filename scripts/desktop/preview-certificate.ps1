function Get-OrionPreviewCertificate {
    param([byte[]]$Certificate, [string]$Fingerprint)

    if ([Security.Cryptography.X509Certificates.X509Certificate2]::GetCertContentType($Certificate) -ne 'Cert') {
        throw 'Expected a public DER certificate.'
    }
    $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new($Certificate)
    try {
        $usage = $cert.Extensions['2.5.29.15']
        $eku = $cert.Extensions['2.5.29.37']
        $constraints = $cert.Extensions['2.5.29.19']
        if ($Fingerprint -notmatch '^[a-fA-F0-9]{64}$' -or
            $cert.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $Fingerprint -or
            $cert.HasPrivateKey -or
            [Convert]::ToBase64String($cert.RawData) -cne [Convert]::ToBase64String($Certificate) -or
            [Convert]::ToBase64String($cert.SubjectName.RawData) -cne [Convert]::ToBase64String($cert.IssuerName.RawData) -or
            !$usage -or $usage.KeyUsages -ne [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -or
            !$eku -or $eku.EnhancedKeyUsages.Count -ne 1 -or $eku.EnhancedKeyUsages[0].Value -ne '1.3.6.1.5.5.7.3.3' -or
            !$constraints -or $constraints.CertificateAuthority -or
            $cert.NotBefore -gt (Get-Date) -or $cert.NotAfter -le (Get-Date)) {
            throw 'Expected the pinned, currently valid, public Orion Preview code-signing leaf certificate.'
        }
        # Verify the isolated one-element chain without editing Windows trust stores.
        $chain = [Security.Cryptography.X509Certificates.X509Chain]::new()
        try {
            $chain.ChainPolicy.TrustMode = 'CustomRootTrust'
            $chain.ChainPolicy.RevocationMode = 'NoCheck'
            $chain.ChainPolicy.DisableCertificateDownloads = $true
            $null = $chain.ChainPolicy.CustomTrustStore.Add($cert)
            if (!$chain.Build($cert) -or $chain.ChainElements.Count -ne 1) {
                throw 'The Preview certificate is not a valid self-signed leaf.'
            }
        } finally {
            $chain.Dispose()
        }
        return $cert
    } catch {
        $cert.Dispose()
        throw
    }
}
