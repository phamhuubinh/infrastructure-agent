use serde::Serialize;
use serde_json::Value;
use std::{os::windows::io::{AsRawHandle, OwnedHandle}, path::{Path, PathBuf}, process::Stdio, time::Duration};
use tokio::{io::AsyncReadExt, process::{Child, Command}, time::{Instant, sleep}};
use windows_sys::Win32::System::{JobObjects::AssignProcessToJobObject, Threading::CREATE_NO_WINDOW};

const CLI_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    state: &'static str,
    backend: Option<String>,
    url: Option<String>,
    reachable: bool,
    owned: bool,
    manual_command: Option<String>,
}

fn executable() -> Option<PathBuf> {
    ["ProgramW6432", "ProgramFiles"]
        .into_iter()
        .filter_map(std::env::var_os)
        .map(|root| PathBuf::from(root).join("Tailscale").join("tailscale.exe"))
        .find(|path| path.is_absolute() && path.is_file())
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

#[derive(Default)]
pub struct Serve {
    process: Option<(Child, OwnedHandle)>,
}

impl Serve {
    pub fn stop(&mut self) {
        // Closing the CLI's foreground watcher removes just that Serve session.
        if let Some((mut child, _job)) = self.process.take() {
            let _ = child.start_kill();
        }
    }

    fn running(&mut self) -> bool {
        match self.process.as_mut().map(|(child, _job)| child.try_wait()) {
            Some(Ok(None)) => true,
            _ => {
                self.stop();
                false
            }
        }
    }

    pub async fn status(&mut self, backend: Option<String>, origin: Option<String>) -> Status {
        let mut result = inspect(backend, origin).await;
        result.owned = self.running();
        result
    }

    pub async fn enable(&mut self, backend: String, origin: String) -> Status {
        let mut result = self.status(Some(backend.clone()), Some(origin.clone())).await;
        if result.state != "unconfigured" || result.owned {
            return result;
        }
        let Some(exe) = executable() else {
            result.state = "not_installed";
            return result;
        };
        let Ok(url) = url::Url::parse(&origin) else {
            result.state = "origin_mismatch";
            return result;
        };
        let port = url.port().unwrap_or(443);
        let https = format!("--https={port}");
        let deadline = Instant::now() + Duration::from_secs(8);
        if let Some(process) = spawn_serve(&exe, &https, &backend) {
            self.process = Some(process);
            while self.running() && Instant::now() < deadline {
                sleep(Duration::from_millis(350)).await;
                result = self.status(Some(backend.clone()), Some(origin.clone())).await;
                if result.state == "configured" && result.owned {
                    return result;
                }
                if matches!(result.state, "public" | "different_backend") {
                    self.stop();
                    result.owned = false;
                    return result;
                }
            }
            self.stop();
        }
        result = self.status(Some(backend.clone()), Some(origin)).await;
        if result.state == "unconfigured" {
            result.state = "enable_failed";
            result.manual_command = Some(format!("& '{}' serve {https} {backend}", exe.to_string_lossy().replace('\'', "''")));
        }
        result
    }
}

fn spawn_serve(exe: &Path, https: &str, backend: &str) -> Option<(Child, OwnedHandle)> {
    let job = crate::managed::create_job().ok()?;
    let child = cli(exe).args(["serve", https, backend]).spawn().ok()?;
    let handle = child.raw_handle()?;
    if unsafe { AssignProcessToJobObject(job.as_raw_handle(), handle) } == 0 {
        return None;
    }
    Some((child, job))
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

pub async fn inspect(backend: Option<String>, host_origin: Option<String>) -> Status {
    let mut result = Status {
        state: "not_installed",
        backend,
        url: None,
        reachable: false,
        owned: false,
        manual_command: None,
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
        if let Ok(client) = reqwest::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(5))
            .build()
        {
            if let Ok(mut response) = client.get(format!("{origin}/api/health")).send().await {
                if response.status() == reqwest::StatusCode::OK {
                    let mut body = Vec::new();
                    while let Ok(Some(chunk)) = response.chunk().await {
                        if body.len() + chunk.len() > 1024 {
                            return result;
                        }
                        body.extend_from_slice(&chunk);
                    }
                    if let Ok(health) = serde_json::from_slice::<Value>(&body) {
                        result.reachable =
                            health["identity"] == "orion" && health["status"] == "ok";
                    }
                }
            }
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
}
