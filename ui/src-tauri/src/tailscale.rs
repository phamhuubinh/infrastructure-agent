use serde::Serialize;
use serde_json::Value;
use std::{path::PathBuf, time::Duration};
use tokio::{io::AsyncReadExt, process::Command};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    state: &'static str,
    backend: Option<String>,
    url: Option<String>,
    reachable: bool,
}

fn executable() -> Option<PathBuf> {
    ["ProgramW6432", "ProgramFiles"]
        .into_iter()
        .filter_map(std::env::var_os)
        .map(|root| PathBuf::from(root).join("Tailscale").join("tailscale.exe"))
        .find(|path| path.is_absolute() && path.is_file())
}

async fn read_status(exe: &PathBuf, args: &[&str]) -> Option<Value> {
    let mut child = Command::new(exe)
        .args(args)
        .creation_flags(0x08000000)
        .kill_on_drop(true)
        .stdin(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .spawn()
        .ok()?;
    let mut output = Vec::new();
    tokio::time::timeout(Duration::from_secs(5), async {
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
    if config["AllowFunnel"][host_port].as_bool() == Some(true) {
        return "public";
    }
    if config["TCP"][port.to_string()]["HTTPS"].as_bool() != Some(true) {
        return "unconfigured";
    }
    match config["Web"][host_port]["Handlers"]["/"]["Proxy"].as_str() {
        Some(proxy) if proxy.trim_end_matches('/') == backend => "configured",
        Some(_) => "different_backend",
        None => "unconfigured",
    }
}

pub async fn inspect(backend: Option<String>, host_origin: Option<String>) -> Status {
    let mut result = Status {
        state: "not_installed",
        backend,
        url: None,
        reachable: false,
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
