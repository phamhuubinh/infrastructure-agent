[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Directory,
    [Parameter(Mandatory)][string]$Evidence,
    [string]$Repository = 'phamhuubinh/infrastructure-agent'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$out = (Get-Item -LiteralPath $Directory).FullName
$build = Get-Content -LiteralPath (Join-Path $out 'build.json') -Raw | ConvertFrom-Json
$result = Get-Content -LiteralPath $Evidence -Raw | ConvertFrom-Json
if ($build.source -notmatch '^[a-f0-9]{40}$' -or $build.version -notmatch '^\d+\.\d+\.\d+$' -or
    $build.signer -notmatch '^[a-f0-9]{64}$' -or $result.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
    $result.source -cne $build.source -or $result.version -cne $build.version -or $result.signer -cne $build.signer -or
    ($result.outcomes -join ',') -cne 'Installed,Rolled back') {
    throw 'Expected isolated acceptance evidence for this release build.'
}
$name = "Orion_$($build.version)_x64-setup.exe"
$installer = Join-Path $out $name
$checksums = Join-Path $out 'DESKTOP-SHA256SUMS'
$checksum = (Get-Content -LiteralPath $checksums -Raw).TrimEnd("`r", "`n")
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($checksum -cne "$($result.sha256)  $name" -or (Get-FileHash -LiteralPath $installer).Hash -ne $result.sha256 -or
    !$signature.SignerCertificate -or !$signature.TimeStamperCertificate -or
    $signature.SignerCertificate.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256) -ne $build.signer) {
    throw 'The local bundle does not match the accepted signed installer.'
}
$repo = (Resolve-Path -LiteralPath "$PSScriptRoot/../..").Path
if ($build.source -cne (git -C $repo rev-parse HEAD).Trim() -or (git -C $repo status --porcelain)) {
    throw 'Publish from the exact clean build commit.'
}
$null = gh api "repos/$Repository/commits/$($build.source)" --jq .sha
$base = git -C $repo show "HEAD:backend/src/orion/_version.py" |
    Select-String '^__version__ = "(\d+\.\d+\.\d+)"$'
if (!$base) { throw 'Cannot read the source release version.' }
$candidate = [version]$build.version
$floor = [version]$base.Matches[0].Groups[1].Value
$tags = gh api --paginate "repos/$Repository/releases?per_page=100" --jq '.[].tag_name'
foreach ($tag in $tags) {
    if ($tag -match '^(?:orion-preview-v|v)(\d+\.\d+\.\d+)$') {
        $published = [version]$Matches[1]
        if ($published -gt $floor) { $floor = $published }
    }
}
if ($candidate -le $floor) { throw "Preview must exceed the current release version floor $floor." }
gh release create "orion-preview-v$($build.version)" $installer $checksums --repo $Repository --target $build.source `
    --prerelease --latest=false --title "Orion Preview $($build.version)" `
    --notes "Windows x64 NSIS built and signed locally from $($build.source). Isolated install and rollback verified. SHA-256 $($result.sha256)."
