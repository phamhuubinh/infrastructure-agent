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
$tag = "orion-preview-v$($build.version)"
$ref = "refs/tags/$tag"
$refs = gh api "repos/$Repository/git/matching-refs/tags/$tag" | ConvertFrom-Json
$existing = $refs | Where-Object ref -CEQ $ref
if (!$existing) {
    $null = gh api --method POST "repos/$Repository/git/refs" -f "ref=$ref" -f "sha=$($build.source)"
} elseif ($existing.object.type -ne 'commit' -or $existing.object.sha -cne $build.source) {
    throw 'The existing Preview tag points to a different source.'
}
gh release create $tag $installer $checksums --repo $Repository --verify-tag `
    --prerelease --latest=false --title "Orion Preview $($build.version)" `
    --notes "Windows x64 NSIS built and signed locally from $($build.source). Isolated install and rollback verified. SHA-256 $($result.sha256)."

$release = gh api "repos/$Repository/releases/tags/$tag" | ConvertFrom-Json
$remoteInstaller = $release.assets | Where-Object name -CEQ $name
if ($release.draft -or !$release.prerelease -or $release.assets.Count -ne 2 -or
    !($release.assets | Where-Object name -CEQ 'DESKTOP-SHA256SUMS') -or
    $remoteInstaller.digest -cne "sha256:$($result.sha256)") {
    throw 'GitHub did not report the expected Preview assets and SHA-256.'
}
