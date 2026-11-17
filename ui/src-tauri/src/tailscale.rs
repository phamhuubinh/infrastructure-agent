use serde::Serialize;
use serde_json::Value;
use std::{path::{Path, PathBuf}, process::Stdio, time::Duration};
use tokio::{io::AsyncReadExt, process::Command};
use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;

const CLI_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    state: &'static str,
    backend: Option<String>,
    url: Option<String>,
    reachable: bool,
    probe: &'static str,
    owned: bool,
    enabled: bool,
    error: Option<&'static str>,
}

fn executable() -> Option<PathBuf> {
    use windows_sys::Win32::UI::Shell::{CSIDL_PROGRAM_FILES, SHGetFolderPathW};
    let mut root = [0_u16; 260];
    if unsafe {
        SHGetFolderPathW(std::ptr::null_mut(), CSIDL_PROGRAM_FILES as i32,
            std::ptr::null_mut(), 0, root.as_mut_ptr())
    } < 0 {
        return None;
    }
    let end = root.iter().position(|value| *value == 0)?;
    let path = PathBuf::from(String::from_utf16_lossy(&root[..end])).join("Tailscale/tailscale.exe");
    (path.is_absolute() && path.is_file()).then_some(path)
}

fn cli(exe: &Path) -> Command {
    let mut command = Command::new(exe);
    command.creation_flags(CREATE_NO_WINDOW)
        .kill_on_drop(true)
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .stdout(Stdio::null());
    command
}

async fn read_status(exe: &Path, args: &[&str]) -> Option<Value> {
    let mut child = cli(exe)
        .args(args)
        .stdout(Stdio::piped())
        .spawn()
        .ok()?;
    let mut output = Vec::new();
    tokio::time::timeout(CLI_TIMEOUT, async {
        child
            .stdout
            .take()?
            .take(1024 * 1024)
            .read_to_end(&mut output)
            .await
            .ok()?;
        if output.len() >= 1024 * 1024 || !child.wait().await.ok()?.success() {
            return None;
        }
        serde_json::from_slice(&output).ok()
    })
    .await
    .ok()?
}

fn serve_state(config: &Value, host_port: &str, port: u16, backend: &str) -> &'static str {
    let port = port.to_string();
    let foreground = config["Foreground"].as_object().into_iter().flat_map(|map| map.values());
    let mut occupied = false;
    let mut exact = false;
    for scope in std::iter::once(config).chain(foreground) {
        if scope["AllowFunnel"][host_port].as_bool() == Some(true) {
            return "public";
        }
        if !scope["TCP"][&port].is_null() || !scope["Web"][host_port].is_null() {
            if scope["TCP"][&port]["HTTPS"].as_bool() == Some(true)
                && scope["Web"][host_port]["Handlers"]["/"]["Proxy"]
                    .as_str().is_some_and(|proxy| proxy.trim_end_matches('/') == backend)
            {
                exact = true;
            } else {
                occupied = true;
            }
        }
    }
    if occupied {
        "different_backend"
    } else if exact {
        "configured"
    } else {
        "unconfigured"
    }
}

pub const HOST_BACKEND: &str = "http://127.0.0.1:61888";

fn managed_route(config: &Value, address: &str, port: u16) -> bool {
    let key = port.to_string();
    let suffix = format!(":{port}");
    config["TCP"][&key] == serde_json::json!({"HTTPS": true})
        && config["Web"][address] == serde_json::json!({"Handlers": {"/": {"Proxy": HOST_BACKEND}}})
        && config["Web"].as_object().is_some_and(|routes| {
            routes.keys().all(|host| host == address || !host.ends_with(&suffix))
        })
        && serve_state(config, address, port, HOST_BACKEND) == "configured"
        && config["Foreground"].as_object().is_none_or(|items| {
            items.values().all(|scope| scope["TCP"][&key].is_null()
                && scope["Web"][address].is_null())
        })
}

fn occupied_port(config: &Value, port: u16) -> bool {
    let key = port.to_string();
    let suffix = format!(":{port}");
    std::iter::once(config).chain(
        config["Foreground"].as_object().into_iter().flat_map(|scopes| scopes.values())
    ).any(|scope| {
        !scope["TCP"][&key].is_null()
            || ["Web", "AllowFunnel"].iter().any(|section| {
                scope[*section].as_object().is_some_and(|entries| {
                    entries.keys().any(|host| host.ends_with(&suffix))
                })
            })
    })
}

async fn config(exe: &Path) -> Result<Value, &'static str> {
    read_status(exe, &["serve", "status", "--json"]).await
        .ok_or("Không đọc được cấu hình Serve.")
}

async fn run_serve(exe: &Path, args: &[&str], allow_uac: bool) -> Result<(), &'static str> {
    let output = tokio::time::timeout(
        Duration::from_secs(15),
        cli(exe).args(args).stdout(Stdio::piped()).stderr(Stdio::piped()).output(),
    ).await.map_err(|_| "Tailscale không hoàn tất trong thời gian chờ.")?
        .map_err(|_| "Không chạy được Tailscale.")?;
    if output.status.success() {
        return Ok(());
    }
    let message = String::from_utf8_lossy(&output.stderr).to_ascii_lowercase();
    if !["access denied", "access is denied", "permission denied", "administrator",
        "not allowed", "not permitted", "not authorized"].iter().any(|part| message.contains(part))
    {
        return Err("Tailscale từ chối yêu cầu. Kiểm tra quyền HTTPS của tailnet.");
    }
    if !allow_uac {
        return Err("Tailscale cần quyền Administrator. Bấm bật lại để xác nhận UAC.");
    }
    let executable = exe.to_owned();
    let parameters = args.join(" ");
    tokio::task::spawn_blocking(move || request_elevation(&executable, &parameters))
        .await.map_err(|_| "Không mở được thao tác UAC.")?
}

fn request_elevation(executable: &Path, parameters: &str) -> Result<(), &'static str> {
    use std::os::windows::{ffi::OsStrExt, io::{FromRawHandle, OwnedHandle}};
    use windows_sys::Win32::{
        Foundation::{ERROR_CANCELLED, GetLastError, WAIT_OBJECT_0},
        System::Threading::{GetExitCodeProcess, WaitForSingleObject},
        UI::Shell::{SEE_MASK_NOCLOSEPROCESS, SHELLEXECUTEINFOW, ShellExecuteExW},
    };
    let file: Vec<u16> = executable.as_os_str().encode_wide().chain([0]).collect();
    let verb: Vec<u16> = "runas".encode_utf16().chain([0]).collect();
    let parameters: Vec<u16> = parameters.encode_utf16().chain([0]).collect();
    let mut info = SHELLEXECUTEINFOW {
        cbSize: std::mem::size_of::<SHELLEXECUTEINFOW>() as u32,
        fMask: SEE_MASK_NOCLOSEPROCESS,
        lpVerb: verb.as_ptr(),
        lpFile: file.as_ptr(),
        lpParameters: parameters.as_ptr(),
        nShow: 0,
        ..Default::default()
    };
    if unsafe { ShellExecuteExW(&mut info) } == 0 {
        return Err(if unsafe { GetLastError() } == ERROR_CANCELLED {
            "Bạn đã hủy yêu cầu UAC."
        } else {
            "Windows không mở được Tailscale với quyền Administrator."
        });
    }
    if info.hProcess.is_null() {
        return Err("Không xác minh được tiến trình Tailscale.");
    }
    let _handle = unsafe { OwnedHandle::from_raw_handle(info.hProcess) };
    if unsafe { WaitForSingleObject(info.hProcess, 30_000) } != WAIT_OBJECT_0 {
        return Err("Tailscale không hoàn tất trong thời gian chờ.");
    }
    let mut code = 1;
    if unsafe { GetExitCodeProcess(info.hProcess, &mut code) } == 0 || code != 0 {
        return Err("Tailscale không lưu được cấu hình Serve.");
    }
    Ok(())
}

pub async fn apply(origin: &str, enable: bool, allow_uac: bool) -> Result<bool, &'static str> {
    let exe = executable().ok_or("Chưa cài Tailscale.")?;
    let url = url::Url::parse(origin).map_err(|_| "URL HTTPS không hợp lệ.")?;
    let host = url.host_str().ok_or("URL HTTPS không hợp lệ.")?;
    let detected = inspect(None, None).await.url.ok_or("Tailscale chưa kết nối.")?;
    let expected = url::Url::parse(&detected).map_err(|_| "URL Tailscale không hợp lệ.")?;
    if url.scheme() != "https" || url.origin().ascii_serialization() != origin
        || expected.host_str() != Some(host)
    {
        return Err("URL Host Mode không khớp với máy Tailscale này.");
    }
    let port = url.port().unwrap_or(443);
    let address = format!("{host}:{port}");
    let before = config(&exe).await?;
    let state = serve_state(&before, &address, port, HOST_BACKEND);
    if enable && state == "configured" || !enable && !managed_route(&before, &address, port) {
        return Ok(false);
    }
    if enable && occupied_port(&before, port) {
        return Err("Cổng HTTPS đang dùng cho cấu hình Serve khác hoặc Funnel.");
    }
    let https = format!("--https={port}");
    let mut args = vec!["serve", "--bg", &https, HOST_BACKEND];
    if !enable {
        args.push("off");
    }
    run_serve(&exe, &args, allow_uac).await?;
    let after = config(&exe).await?;
    if enable && managed_route(&after, &address, port)
        || !enable && serve_state(&after, &address, port, HOST_BACKEND) != "configured"
    {
        return Ok(enable);
    }
    Err("Cấu hình Serve sau thao tác không khớp.")
}

pub async fn default_origin() -> Result<String, &'static str> {
    let status = inspect(None, None).await;
    status.url.ok_or(match status.state {
        "not_installed" => "Chưa cài Tailscale.",
        "login_required" => "Hãy đăng nhập Tailscale.",
        "no_dns" => "Tailscale chưa có tên DNS.",
        _ => "Tailscale chưa kết nối.",
    })
}

pub async fn validate_slot(origin: &str) -> Result<(), &'static str> {
    let url = url::Url::parse(origin).map_err(|_| "URL HTTPS không hợp lệ.")?;
    let host = url.host_str().ok_or("URL không có tên máy.")?;
    let port = url.port().unwrap_or(443);
    let executable = executable().ok_or("Chưa cài Tailscale.")?;
    let current = config(&executable).await?;
    let state = serve_state(&current, &format!("{host}:{port}"), port, HOST_BACKEND);
    if state != "configured" && occupied_port(&current, port) {
        return Err("Cổng HTTPS đang dùng cho cấu hình Serve khác hoặc Funnel.");
    }
    Ok(())
}

impl Status {
    pub fn with_settings(mut self, enabled: bool, owned: bool, error: Option<&'static str>) -> Self {
        self.enabled = enabled;
        self.owned = owned;
        self.error = error;
        self
    }
}

pub async fn owner_ready(backend: &crate::managed::ManagedBackend, transport: &crate::transport::Transport) -> bool {
    use crate::transport::{Destination, Request};
    let path = format!("{}/api/auth/owner", backend.origin());
    tokio::time::timeout(CLI_TIMEOUT, async {
        let response = transport.send(Destination::Managed(backend), Request {
            url: path.clone(),
            method: "GET".into(),
            headers: vec![],
            body: vec![],
        }).await.ok()?;
        if !response.status().is_success() {
            return None;
        }
        let body = response.bytes().await.ok()?;
        if serde_json::from_slice::<Value>(&body).ok()?["configured"] != true {
            return None;
        }
        let unauthorized = reqwest::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .build().ok()?.get(path).send().await.ok()?;
        Some(matches!(unauthorized.status().as_u16(), 401 | 403))
    }).await.ok().flatten().unwrap_or(false)
}

async fn https_request(origin: &str, path: &str, login: bool) -> Result<(u16, Value), &'static str> {
    use windows_sys::Win32::System::SystemInformation::GetSystemDirectoryW;
    let mut directory = [0_u16; 260];
    let length = unsafe { GetSystemDirectoryW(directory.as_mut_ptr(), directory.len() as u32) } as usize;
    if length == 0 || length >= directory.len() {
        return Err("probe_unavailable");
    }
    let executable = PathBuf::from(String::from_utf16_lossy(&directory[..length])).join("curl.exe");
    let mut command = cli(&executable);
    command.args([
        "--disable", "--noproxy", "*", "--silent", "--max-time", "10",
        "--max-filesize", "4096", "--write-out", "\\n%{http_code}",
    ]);
    if login {
        // Malformed JSON checks the browser Origin gate without submitting a login attempt.
        command.args(["--header", &format!("Origin: {origin}"), "--data-binary", "{"]);
    }
    let output = command.arg(format!("{origin}{path}")).stdout(Stdio::piped())
        .output().await.map_err(|_| "probe_unavailable")?;
    if !output.status.success() {
        return Err(match output.status.code() {
            Some(28) => "timeout",
            Some(35 | 51 | 58 | 59 | 60 | 66 | 77 | 80 | 82 | 83 | 90 | 91) => "tls",
            Some(5 | 6) => "dns",
            Some(7 | 52 | 55 | 56) => "connect",
            _ => "invalid_response",
        });
    }
    let split = output.stdout.iter().rposition(|byte| *byte == b'\n')
        .ok_or("invalid_response")?;
    let status = std::str::from_utf8(&output.stdout[split + 1..])
        .ok().and_then(|code| code.trim().parse().ok()).ok_or("invalid_response")?;
    let body = serde_json::from_slice(&output.stdout[..split]).unwrap_or(Value::Null);
    Ok((status, body))
}

fn orion_health(body: &Value) -> bool {
    body["identity"] == "orion" && body["status"] == "ok"
}

async fn verify_https(origin: &str, backend: &str) -> Result<&'static str, &'static str> {
    let (local_status, local) = https_request(backend, "/api/health", false).await
        .map_err(|_| "backend_unavailable")?;
    if local_status != 200 || !orion_health(&local) {
        return Err("backend_unavailable");
    }
    match https_request(origin, "/api/health", false).await? {
        (200, health) if orion_health(&health) => {}
        (401 | 403, _) => {}
        (502..=504, _) => return Err("upstream_proxy"),
        _ => return Err("invalid_response"),
    }
    match https_request(origin, "/api/auth/session", false).await? {
        (200, auth) if auth["remote_access"] == true && auth["authenticated"] == false
            && auth["mfa_required"] == true => {}
        (401 | 403, _) => return Ok("auth_required"),
        (502..=504, _) => return Err("upstream_proxy"),
        _ => return Err("auth_mismatch"),
    }
    match https_request(origin, "/api/sessions", false).await?.0 {
        401 | 403 => {}
        502..=504 => return Err("upstream_proxy"),
        _ => return Err("auth_mismatch"),
    }
    match https_request(origin, "/api/auth/login", true).await?.0 {
        400 | 422 => Ok("login_ready"),
        403 => Ok("origin_rejected"),
        502..=504 => Err("upstream_proxy"),
        _ => Err("auth_mismatch"),
    }
}

pub async fn inspect(backend: Option<String>, host_origin: Option<String>) -> Status {
    let mut result = Status {
        state: "not_installed",
        backend,
        url: None,
        reachable: false,
        probe: "not_checked",
        owned: false,
        enabled: false,
        error: None,
    };
    let Some(exe) = executable() else {
        return result;
    };
    let Some(node) = read_status(&exe, &["status", "--json", "--peers=false"]).await else {
        result.state = "unavailable";
        return result;
    };
    if node["BackendState"].as_str() != Some("Running") {
        result.state = match node["BackendState"].as_str() {
            Some("NeedsLogin" | "NeedsMachineAuth") => "login_required",
            _ => "offline",
        };
        return result;
    }
    let Some(hostname) = node["Self"]["DNSName"]
        .as_str()
        .map(|name| name.trim_end_matches('.'))
        .filter(|name| {
            name.ends_with(".ts.net")
                && name
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'.')
        })
    else {
        result.state = "no_dns";
        return result;
    };
    let default_url = format!("https://{hostname}");
    result.url = Some(default_url.clone());
    let (Some(backend), Some(origin)) = (&result.backend, host_origin) else {
        result.state = "host_disabled";
        return result;
    };
    let Ok(url) = url::Url::parse(&origin) else {
        result.state = "origin_mismatch";
        return result;
    };
    if url.scheme() != "https"
        || url.host_str() != Some(hostname)
        || url.origin().ascii_serialization() != origin
    {
        result.state = "origin_mismatch";
        return result;
    }
    result.url = Some(origin.clone());
    let Some(config) = read_status(&exe, &["serve", "status", "--json"]).await else {
        result.state = "serve_unavailable";
        return result;
    };
    let port = url.port().unwrap_or(443);
    result.state = serve_state(&config, &format!("{hostname}:{port}"), port, backend);
    if result.state == "configured" {
        match verify_https(&origin, backend).await {
            Ok(probe) => {
                result.probe = probe;
                result.reachable = true;
            }
            Err(probe) => result.probe = probe,
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn checks_exact_upstream_and_funnel_state() {
        let mut config = json!({
            "TCP": {"443": {"HTTPS": true}},
            "Web": {"host.example.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:39577"}}}}
        });
        let host = "host.example.ts.net:443";
        assert_eq!(
            serve_state(&config, host, 443, "http://127.0.0.1:39577"),
            "configured"
        );
        assert_eq!(
            serve_state(&config, host, 443, "http://127.0.0.1:61888"),
            "different_backend"
        );
        config["AllowFunnel"] = json!({host: true});
        assert_eq!(
            serve_state(&config, host, 443, "http://127.0.0.1:39577"),
            "public"
        );
    }

    #[test]
    fn protects_existing_serve_routes() {
        let host = "host.example.ts.net:443";
        let mut config = json!({
            "TCP": {"443": {"HTTPS": true}},
            "Web": {host: {"Handlers": {"/": {"Proxy": HOST_BACKEND}}}}
        });
        assert!(occupied_port(&config, 443));
        assert!(!occupied_port(&config, 8443));
        assert!(managed_route(&config, host, 443));
        config["Web"]["another.example.ts.net:443"] = json!({"Handlers": {"/": {"Text": "other"}}});
        assert!(!managed_route(&config, host, 443));
        config["Web"].as_object_mut().unwrap().remove("another.example.ts.net:443");
        config["Web"][host]["Handlers"]["/other"] = json!({"Text": "another app"});
        assert!(!managed_route(&config, host, 443));
        assert!(occupied_port(&json!({"Foreground":{"existing":{"TCP":{"443":{"HTTPS":true}}}}}), 443));
        assert!(occupied_port(&json!({"AllowFunnel":{host:true}}), 443));
    }

    #[tokio::test]
    #[ignore = "requires a running private Orion Host Mode on this machine"]
    async fn verifies_real_private_serve() {
        let origin = default_origin().await.unwrap();
        assert_eq!(verify_https(&origin, HOST_BACKEND).await, Ok("login_ready"));
    }
}
