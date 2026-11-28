use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::{self, Write},
    os::windows::process::CommandExt,
    path::{Path, PathBuf},
    process::{Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;
use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;

const RELEASES: &str = "https://github.com/phamhuubinh/infrastructure-agent/releases";
const LATEST: &str = "https://api.github.com/repos/phamhuubinh/infrastructure-agent/releases/latest";
const PREVIEWS: &str = "https://api.github.com/repos/phamhuubinh/infrastructure-agent/releases?per_page=50";
const LIMIT: u64 = 512 * 1024 * 1024;
const UNAVAILABLE: &str = "Không kiểm tra được bản cập nhật Orion.";
const REJECTED: &str = "Bộ cài không khớp phiên bản, SHA-256 hoặc chữ ký Orion.";
const CHECK_SIGNATURE: &str = r#"
$ErrorActionPreference = 'Stop'
$file = $env:ORION_UPDATE_FILE
$sig = Get-AuthenticodeSignature -LiteralPath $file
if ($sig.Status -ne 'Valid' -or !$sig.SignerCertificate) { throw 'Signature invalid' }
$hash = [Security.Cryptography.SHA256]::Create()
$signer = [BitConverter]::ToString($hash.ComputeHash($sig.SignerCertificate.RawData)).Replace('-', '')
if ($signer -ne $env:ORION_UPDATE_SIGNER) { throw 'Wrong publisher' }
if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $env:ORION_UPDATE_HASH) {
    throw 'Wrong asset digest'
}
$info = (Get-Item -LiteralPath $file).VersionInfo
if ($info.ProductName -ne 'Orion' -or $info.ProductVersion -ne $env:ORION_UPDATE_VERSION) {
    throw 'Wrong product version'
}
"#;

// NSIS /D must be the final raw argument, including when the existing path has spaces.
// Start only after the current UI exits, then reopen the same installation if it still exists.
const HANDOFF: &str = r#"
$ErrorActionPreference = 'Stop'
$exe = $env:ORION_UPDATE_EXE
$stage = Split-Path -LiteralPath $env:ORION_UPDATE_FILE
$receipt = Join-Path $stage 'snapshot.json'
$installStarted = $false
$committed = $false
$updated = $null
$relaunch = $false
$clearActive = $false
try {
    $parent = Get-Process -Id ([int]$env:ORION_UPDATE_PARENT) -ErrorAction SilentlyContinue
    if ($parent -and !$parent.WaitForExit(30000)) { throw 'Orion did not exit' }
    $relaunch = $true
    & ([scriptblock]::Create($env:ORION_UPDATE_VERIFY))
    $directory = Split-Path -LiteralPath $exe
    $backup = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
    $restore = Join-Path $backup.snapshot 'installed/backend/OrionBackend.exe'
    if (!(Test-Path -LiteralPath $restore -PathType Leaf)) { throw 'Missing rollback helper' }
    $installStarted = $true
    $process = Start-Process -FilePath $env:ORION_UPDATE_FILE -ArgumentList ("/S /D=" + $directory) -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Installer failed' }
    if ((Get-Item -LiteralPath $exe).VersionInfo.ProductVersion -ne $env:ORION_UPDATE_VERSION) {
        throw 'Unexpected installed version'
    }
    $updated = Start-Process -FilePath $exe -ArgumentList ('--finish-update "' + $stage + '"') -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    $healthy = Join-Path $stage 'healthy.txt'
    while (!(Test-Path -LiteralPath $healthy -PathType Leaf)) {
        if ($updated.HasExited -or [DateTime]::UtcNow -ge $deadline) { throw 'Orion health timeout' }
        Start-Sleep -Milliseconds 100
    }
    if ($updated.HasExited) { throw 'Orion exited before commit' }
    $prepared = Join-Path $stage 'commit.tmp'
    [IO.File]::WriteAllText($prepared, 'committed')
    [IO.File]::Move($prepared, (Join-Path $stage 'committed.txt'))
    $committed = $true
    $clearActive = $true
    $relaunch = $false
    'Installed' | Set-Content -LiteralPath (Join-Path $stage 'outcome.txt')
} catch {
    if ($committed) { exit 0 }
    if ($installStarted) {
        $relaunch = $false
        try {
            if ($updated -and !$updated.HasExited) {
                $updated.Kill()
                if (!$updated.WaitForExit(15000)) { throw 'Updated app did not stop' }
            }
            & $restore '--restore-for-update' $receipt
            if ($LASTEXITCODE -ne 0) { throw 'Restore failed' }
            $relaunch = $true
            $clearActive = $true
            'Rolled back' | Set-Content -LiteralPath (Join-Path $stage 'outcome.txt')
        } catch {
            'Manual recovery required' | Set-Content -LiteralPath (Join-Path $stage 'outcome.txt')
        }
    } else {
        $clearActive = $true
        'Update rejected' | Set-Content -LiteralPath (Join-Path $stage 'outcome.txt')
    }
} finally {
    if ($clearActive) {
        $expected = Split-Path -Leaf $stage
        $active = $env:ORION_UPDATE_ACTIVE
        if ((Test-Path -LiteralPath $active) -and [IO.File]::ReadAllText($active) -eq $expected) {
            [IO.File]::Delete($active)
        }
    }
    if ($relaunch -and (Test-Path -LiteralPath $exe -PathType Leaf)) { Start-Process -FilePath $exe }
}
"#;

#[derive(Deserialize)]
struct Release {
    tag_name: String,
    draft: bool,
    prerelease: bool,
    assets: Vec<Asset>,
}

#[derive(Deserialize)]
struct Asset {
    name: String,
    size: u64,
    digest: Option<String>,
}

struct Candidate {
    version: String,
    asset: Asset,
}

#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Channel {
    Stable,
    Preview,
}

impl Channel {
    fn prefix(self) -> &'static str {
        match self {
            Self::Stable => "v",
            Self::Preview => "orion-preview-v",
        }
    }

    fn tag(self, version: &str) -> String {
        format!("{}{version}", self.prefix())
    }
}

#[derive(Serialize)]
pub struct UpdateCheck {
    current: String,
    available: Option<String>,
    can_install: bool,
}

fn stable_version(version: &str) -> Option<[u64; 3]> {
    let mut components = version.split('.');
    let mut value = [0; 3];
    for number in &mut value {
        let part = components.next()?;
        if part.len() > 9
            || !part.bytes().all(|byte| byte.is_ascii_digit())
            || (part.len() > 1 && part.starts_with('0'))
        {
            return None;
        }
        *number = part.parse().ok()?;
    }
    components.next().is_none().then_some(value)
}

fn digest(value: &str) -> Option<&str> {
    if value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        Some(value)
    } else {
        None
    }
}

fn publisher_pin() -> Option<&'static str> {
    // Both release channels use the publisher pinned at build time.
    option_env!("ORION_UPDATE_SIGNER_SHA256").and_then(digest)
}

fn available_release(current: [u64; 3], channel: Channel, release: Release) -> Option<Candidate> {
    let version = release.tag_name.strip_prefix(channel.prefix())?;
    if release.draft || release.prerelease != matches!(channel, Channel::Preview)
        || stable_version(version)? <= current
    {
        return None;
    }
    let installer = format!("Orion_{version}_x64-setup.exe");
    let asset = release.assets.into_iter().find(|asset| {
        asset.name == installer && asset.size > 0 && asset.size <= LIMIT
            && asset.digest.as_deref()
                .and_then(|value| digest(value.strip_prefix("sha256:")?)).is_some()
    })?;
    Some(Candidate { version: version.to_owned(), asset })
}

async fn latest(app: &tauri::AppHandle, channel: Channel) -> Result<Option<Candidate>, &'static str> {
    let mut response = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .no_proxy()
        .timeout(Duration::from_secs(8))
        .build().map_err(|_| UNAVAILABLE)?
        .get(match channel { Channel::Stable => LATEST, Channel::Preview => PREVIEWS })
        .header(reqwest::header::USER_AGENT, "Orion-Desktop")
        .header(reqwest::header::ACCEPT, "application/vnd.github+json")
        .send().await.map_err(|_| UNAVAILABLE)?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(UNAVAILABLE);
    }
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| UNAVAILABLE)? {
        if body.len() + chunk.len() > 512 * 1024 {
            return Err(UNAVAILABLE);
        }
        body.extend_from_slice(&chunk);
    }
    let current = &app.package_info().version;
    let current = [current.major, current.minor, current.patch];
    let releases = match channel {
        Channel::Stable => vec![serde_json::from_slice(&body).map_err(|_| UNAVAILABLE)?],
        Channel::Preview => serde_json::from_slice::<Vec<Release>>(&body).map_err(|_| UNAVAILABLE)?,
    };
    Ok(releases.into_iter()
        .filter_map(|release| available_release(current, channel, release))
        .max_by_key(|candidate| stable_version(&candidate.version)))
}

#[tauri::command]
pub async fn orion_check_update(app: tauri::AppHandle, channel: Channel) -> Result<UpdateCheck, &'static str> {
    let available = latest(&app, channel).await?.map(|candidate| candidate.version);
    Ok(UpdateCheck {
        current: app.package_info().version.to_string(),
        can_install: available.is_some() && publisher_pin().is_some(),
        available,
    })
}

pub fn confirm_maintenance() -> bool {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        IDYES, MB_DEFBUTTON2, MB_ICONWARNING, MB_SETFOREGROUND, MB_YESNO, MessageBoxW,
    };
    let text: Vec<u16> = "Bắt đầu cửa sổ bảo trì? Orion sẽ tạm dừng Host, sao lưu và cài bản đã xác minh."
        .encode_utf16().chain([0]).collect();
    let caption: Vec<u16> = "Cập nhật Orion".encode_utf16().chain([0]).collect();
    unsafe {
        MessageBoxW(std::ptr::null_mut(), text.as_ptr(), caption.as_ptr(),
            MB_YESNO | MB_DEFBUTTON2 | MB_ICONWARNING | MB_SETFOREGROUND) == IDYES
    }
}

pub struct StagedUpdate {
    directory: PathBuf,
    version: String,
    hash: String,
    signer: &'static str,
    handed_off: bool,
}

impl StagedUpdate {
    pub fn receipt(&self) -> PathBuf {
        self.directory.join("snapshot.json")
    }
    fn installer(&self) -> PathBuf {
        self.directory.join("OrionSetup.exe")
    }

    fn powershell(&self, script: &str) -> Result<Command, &'static str> {
        let root = std::env::var_os("SystemRoot").ok_or(UNAVAILABLE)?;
        let mut command = Command::new(PathBuf::from(root)
            .join("System32/WindowsPowerShell/v1.0/powershell.exe"));
        command
            .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script])
            // A PowerShell 7 launcher can put incompatible modules ahead of the 5.1 modules.
            .env_remove("PSModulePath")
            .env("ORION_UPDATE_FILE", self.installer())
            .env("ORION_UPDATE_VERSION", &self.version)
            .env("ORION_UPDATE_HASH", &self.hash)
            .env("ORION_UPDATE_SIGNER", self.signer)
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
        Ok(command)
    }

    fn verify(&self) -> Result<(), &'static str> {
        if !wait_for_status(&mut self.powershell(CHECK_SIGNATURE)?, Duration::from_secs(90))
            .is_ok_and(|status| status.success())
        {
            return Err(REJECTED);
        }
        Ok(())
    }

    pub fn hand_off(mut self, executable: &Path) -> Result<(), &'static str> {
        let active = self.directory.parent().ok_or(UNAVAILABLE)?.join("update-active.txt");
        let mut command = self.powershell(HANDOFF)?;
        let name = self.directory.file_name().and_then(|name| name.to_str()).ok_or(UNAVAILABLE)?;
        let mut lock = OpenOptions::new().write(true).create_new(true).open(&active)
            .map_err(|_| "Đang có một giao dịch cập nhật Orion khác.")?;
        if lock.write_all(name.as_bytes()).is_err() || lock.sync_all().is_err() {
            drop(lock);
            let _ = fs::remove_file(&active);
            return Err(UNAVAILABLE);
        }
        drop(lock);
        if command
            .env("ORION_UPDATE_VERIFY", CHECK_SIGNATURE)
            .env("ORION_UPDATE_EXE", executable)
            .env("ORION_UPDATE_ACTIVE", &active)
            .env("ORION_UPDATE_PARENT", std::process::id().to_string())
            .spawn().is_err()
        {
            let _ = fs::remove_file(active);
            return Err("Không khởi động được bộ cài Orion.");
        }
        self.handed_off = true;
        Ok(())
    }
}

pub fn wait_for_status(command: &mut Command, limit: Duration) -> io::Result<ExitStatus> {
    let mut child = command.spawn()?;
    let deadline = Instant::now() + limit;
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok(status);
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(io::Error::new(io::ErrorKind::TimedOut, "Update helper timed out"));
        }
        thread::sleep(Duration::from_millis(50));
    }
}

impl Drop for StagedUpdate {
    fn drop(&mut self) {
        if !self.handed_off {
            let _ = fs::remove_file(self.installer());
            let _ = fs::remove_file(self.receipt());
            let _ = fs::remove_dir(&self.directory);
        }
    }
}

pub fn boot_directory(app: &tauri::AppHandle) -> io::Result<Option<PathBuf>> {
    let invalid = || io::Error::other("Invalid Orion update transaction");
    let app_data = app.path().app_local_data_dir().map_err(|_| invalid())?;
    let active = app_data.join("update-active.txt");
    let mut args = std::env::args_os().skip(1);
    if args.next().as_deref() != Some(std::ffi::OsStr::new("--finish-update")) {
        if active.exists() {
            return Err(io::Error::other("Orion update in progress. See the recovery runbook."));
        }
        return Ok(None);
    }
    let path = PathBuf::from(args.next().ok_or_else(invalid)?).canonicalize()?;
    let parent = app_data.canonicalize()?;
    let pending = fs::read_to_string(active)?;
    if args.next().is_some() || path.parent() != Some(&parent)
        || !path.file_name().and_then(|name| name.to_str())
            .is_some_and(|name| name.starts_with("update-") && name == pending)
        || !path.join("snapshot.json").is_file()
        || path.join("healthy.txt").exists() || path.join("committed.txt").exists()
    {
        return Err(invalid());
    }
    Ok(Some(path))
}

pub fn report_healthy(directory: &Path) -> io::Result<()> {
    let marker = directory.join("healthy.tmp");
    OpenOptions::new().write(true).create_new(true).open(&marker)?.write_all(b"healthy")?;
    fs::rename(&marker, directory.join("healthy.txt"))?;
    let deadline = Instant::now() + Duration::from_secs(12);
    while !directory.join("committed.txt").is_file() {
        if Instant::now() >= deadline {
            return Err(io::Error::new(io::ErrorKind::TimedOut, "Update not committed"));
        }
        thread::sleep(Duration::from_millis(50));
    }
    Ok(())
}

fn is_release_redirect(url: &url::Url) -> bool {
    url.scheme() == "https"
        && url.username().is_empty() && url.password().is_none()
        && url.port().is_none()
        && matches!(url.host_str(), Some("release-assets.githubusercontent.com" | "objects.githubusercontent.com"))
}

pub async fn stage(app: &tauri::AppHandle, version: &str, channel: Channel) -> Result<StagedUpdate, &'static str> {
    let signer = publisher_pin().ok_or("Bản này chưa cấu hình chữ ký phát hành Orion.")?;
    let candidate = latest(app, channel).await?.filter(|candidate| candidate.version == version)
        .ok_or("Bản phát hành đã thay đổi. Hãy kiểm tra lại.")?;
    let hash = candidate.asset.digest.as_deref().and_then(|value| value.strip_prefix("sha256:"))
        .and_then(digest).ok_or(REJECTED)?.to_owned();
    let mut random = [0u8; 18];
    getrandom::fill(&mut random).map_err(|_| UNAVAILABLE)?;
    let directory = app.path().app_local_data_dir().map_err(|_| UNAVAILABLE)?
        .join(format!("update-{}", URL_SAFE_NO_PAD.encode(random)));
    fs::create_dir(&directory).map_err(|_| UNAVAILABLE)?;
    let staged = StagedUpdate { directory, version: candidate.version, hash, signer, handed_off: false };
    let mut file = OpenOptions::new().write(true).create_new(true).open(staged.installer())
        .map_err(|_| UNAVAILABLE)?;

    let tag = channel.tag(&staged.version);
    let download = format!("{RELEASES}/download/{tag}/{}", candidate.asset.name);
    let mut response = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::custom(|hop| {
            if hop.previous().len() <= 3 && is_release_redirect(hop.url()) {
                hop.follow()
            } else {
                hop.error("Unexpected release download redirect")
            }
        }))
        .no_proxy()
        .connect_timeout(Duration::from_secs(10))
        .timeout(Duration::from_secs(180))
        .build().map_err(|_| UNAVAILABLE)?
        .get(download).send().await.map_err(|_| UNAVAILABLE)?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(UNAVAILABLE);
    }
    let mut bytes = 0;
    while let Some(chunk) = response.chunk().await.map_err(|_| UNAVAILABLE)? {
        bytes += chunk.len() as u64;
        if bytes > candidate.asset.size {
            return Err(REJECTED);
        }
        file.write_all(&chunk).map_err(|_| UNAVAILABLE)?;
    }
    if bytes != candidate.asset.size {
        return Err(REJECTED);
    }
    file.sync_all().map_err(|_| UNAVAILABLE)?;
    drop(file);
    tauri::async_runtime::spawn_blocking(move || {
        staged.verify()?;
        Ok(staged)
    }).await.map_err(|_| UNAVAILABLE)?
}

#[tauri::command]
pub fn orion_open_update_release(version: String, channel: Channel) -> Result<(), &'static str> {
    stable_version(&version).ok_or("Phiên bản Orion không hợp lệ.")?;
    let url: Vec<u16> = format!("{RELEASES}/tag/{}", channel.tag(&version)).encode_utf16().chain([0]).collect();
    let result = unsafe {
        windows_sys::Win32::UI::Shell::ShellExecuteW(
            std::ptr::null_mut(), std::ptr::null(), url.as_ptr(), std::ptr::null(),
            std::ptr::null(), windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL,
        )
    };
    if result as isize <= 32 {
        return Err("Không mở được trang phát hành Orion.");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn release_requires_exact_asset_bounded_size_and_digest() {
        for (tag, prerelease, draft, asset, sha, available) in [
            ("v0.1.10", false, false, "Orion_0.1.10_x64-setup.exe", true, true),
            ("v0.1.5", false, false, "Orion_0.1.5_x64-setup.exe", true, false),
            ("v0.1.6", true, false, "Orion_0.1.6_x64-setup.exe", true, false),
            ("v0.1.6", false, true, "Orion_0.1.6_x64-setup.exe", true, false),
            ("v0.1.6", false, false, "Orion_0.1.6_x64-preview-setup.exe", true, false),
            ("v0.1.6", false, false, "Orion_0.1.6_x64-setup.exe", false, false),
            ("v0.1.6/../../other", false, false, "setup.exe", true, false),
        ] {
            let release = Release {
                tag_name: tag.into(), draft, prerelease,
                assets: vec![Asset {
                    name: asset.into(), size: 100,
                    digest: sha.then(|| format!("sha256:{}", "1".repeat(64))),
                }],
            };
            assert_eq!(available_release([0, 1, 5], Channel::Stable, release).is_some(), available, "{tag}");
        }
    }

    #[test]
    fn only_github_release_delivery_hosts_are_followed() {
        for (address, allowed) in [
            ("https://release-assets.githubusercontent.com/a", true),
            ("https://objects.githubusercontent.com/a", true),
            ("http://objects.githubusercontent.com/a", false),
            ("https://objects.githubusercontent.com.evil.example/a", false),
            ("https://objects.githubusercontent.com:8081/a", false),
        ] {
            assert_eq!(is_release_redirect(&url::Url::parse(address).unwrap()), allowed);
        }
    }

    #[test]
    fn preview_tags_are_opt_in_and_cannot_downgrade() {
        fn preview() -> Release {
            Release {
                tag_name: "orion-preview-v0.1.9".into(),
                draft: false, prerelease: true,
                assets: vec![Asset {
                    name: "Orion_0.1.9_x64-setup.exe".into(), size: 100,
                    digest: Some(format!("sha256:{}", "a".repeat(64))),
                }],
            }
        }
        assert!(available_release([0, 1, 5], Channel::Preview, preview()).is_some());
        assert!(available_release([0, 1, 5], Channel::Stable, preview()).is_none());
        assert!(available_release([0, 1, 10], Channel::Preview, preview()).is_none());
    }

    #[test]
    fn windows_update_uses_windows_powershell_security_module() {
        let update = StagedUpdate {
            directory: PathBuf::new(),
            version: "0.1.6".into(),
            hash: "0".repeat(64),
            signer: "1111111111111111111111111111111111111111111111111111111111111111",
            handed_off: true,
        };
        let mut command = update.powershell(r#"
$ErrorActionPreference = 'Stop'
$null = Get-AuthenticodeSignature -LiteralPath (Join-Path $PSHOME 'powershell.exe')
$module = Get-Module Microsoft.PowerShell.Security
if ($PSVersionTable.PSEdition -ne 'Desktop' -or
    $module.Path -ne (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1')) {
    throw 'Signature verification used the wrong PowerShell module.'
}
"#).unwrap();
        assert!(command.get_envs().any(|(key, value)| {
            key == std::ffi::OsStr::new("PSModulePath") && value.is_none()
        }));
        let output = command.stderr(Stdio::piped()).output().unwrap();
        assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    }


    #[test]
    #[ignore = "requires a local unsigned installer fixture"]
    fn windows_trust_rejects_unsigned_installer() {
        let fixture = PathBuf::from(std::env::var_os("ORION_TEST_UNSIGNED_INSTALLER").unwrap());
        let directory = std::env::temp_dir().join(format!("orion-update-test-{}", std::process::id()));
        fs::create_dir(&directory).unwrap();
        let update = StagedUpdate {
            directory, version: "0.1.5".into(), hash: "0".repeat(64),
            signer: "1111111111111111111111111111111111111111111111111111111111111111",
            handed_off: false,
        };
        fs::copy(fixture, update.installer()).unwrap();
        assert_eq!(update.verify(), Err(REJECTED));
    }
}
