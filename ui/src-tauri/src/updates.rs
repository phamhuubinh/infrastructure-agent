use serde::{Deserialize, Serialize};
use std::time::Duration;

const RELEASES: &str = "https://github.com/phamhuubinh/infrastructure-agent/releases";
const LATEST: &str =
    "https://api.github.com/repos/phamhuubinh/infrastructure-agent/releases/latest";

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
}

#[derive(Serialize)]
pub struct UpdateCheck {
    current: String,
    available: Option<String>,
}

fn stable_version(version: &str) -> Option<[u64; 3]> {
    let mut components = version.split('.');
    let mut value = [0; 3];
    for number in &mut value {
        let part = components.next()?;
        if !part.bytes().all(|byte| byte.is_ascii_digit())
            || (part.len() > 1 && part.starts_with('0'))
        {
            return None;
        }
        *number = part.parse().ok()?;
    }
    components.next().is_none().then_some(value)
}

fn available_release(current: [u64; 3], release: Release) -> Option<String> {
    let version = release.tag_name.strip_prefix('v')?;
    if release.draft || release.prerelease || stable_version(version)? <= current {
        return None;
    }
    let installer = format!("Orion_{version}_x64-setup.exe");
    release.assets.iter().any(|asset| asset.name == installer && asset.size > 0)
        .then(|| version.to_owned())
}

#[tauri::command]
pub async fn orion_check_update(app: tauri::AppHandle) -> Result<UpdateCheck, &'static str> {
    let unavailable = "Không kiểm tra được bản cập nhật Orion.";
    let mut response = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(10))
        .build().map_err(|_| unavailable)?
        .get(LATEST)
        .header(reqwest::header::USER_AGENT, "Orion-Desktop")
        .header(reqwest::header::ACCEPT, "application/vnd.github+json")
        .send().await.map_err(|_| unavailable)?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(unavailable);
    }
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| unavailable)? {
        if body.len() + chunk.len() > 512 * 1024 {
            return Err(unavailable);
        }
        body.extend_from_slice(&chunk);
    }
    let release = serde_json::from_slice(&body).map_err(|_| unavailable)?;
    let current = &app.package_info().version;
    Ok(UpdateCheck {
        current: current.to_string(),
        available: available_release([current.major, current.minor, current.patch], release),
    })
}

#[tauri::command]
pub fn orion_open_update_release(version: String) -> Result<(), &'static str> {
    stable_version(&version).ok_or("Phiên bản Orion không hợp lệ.")?;
    let url: Vec<u16> = format!("{RELEASES}/tag/v{version}").encode_utf16().chain([0]).collect();
    let result = unsafe {
        windows_sys::Win32::UI::Shell::ShellExecuteW(
            std::ptr::null_mut(),
            std::ptr::null(),
            url.as_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL,
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
    fn only_newer_stable_releases_with_an_nsis_asset_are_offered() {
        for (tag, prerelease, draft, asset, available) in [
            ("v0.1.10", false, false, "Orion_0.1.10_x64-setup.exe", true),
            ("v0.1.5", false, false, "Orion_0.1.5_x64-setup.exe", false),
            ("v0.1.4", false, false, "Orion_0.1.4_x64-setup.exe", false),
            ("v0.1.6", true, false, "Orion_0.1.6_x64-setup.exe", false),
            ("v0.1.6", false, true, "Orion_0.1.6_x64-setup.exe", false),
            ("v0.1.6", false, false, "orion-0.1.6-windows-x64.zip", false),
            ("v0.1.6/../../other", false, false, "setup.exe", false),
        ] {
            let release = Release {
                tag_name: tag.into(),
                draft,
                prerelease,
                assets: vec![Asset { name: asset.into(), size: 1 }],
            };
            assert_eq!(available_release([0, 1, 5], release).is_some(), available, "{tag}");
        }
    }
}
