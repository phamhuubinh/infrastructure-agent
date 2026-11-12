use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};

#[cfg(windows)]
use crate::managed::ManagedBackend;
use crate::transport::{Destination, Request, Transport};
#[cfg(any(windows, target_os = "ios"))]
use crate::vault;
#[cfg(any(target_os = "android", target_os = "ios"))]
use base64::{Engine, engine::general_purpose::STANDARD};
use serde::{Deserialize, Serialize};
use tauri::{Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};
#[cfg(windows)]
use tauri::{
    ipc::{InvokeBody, Request as IpcRequest, Response as IpcResponse},
    webview::NewWindowResponse,
};
use tokio_util::sync::CancellationToken;

const INVALID: &str = "Invalid Orion request";
const CANCELLED: &str = "Orion request cancelled";
const WINDOW: &str = "main";

struct Host {
    #[cfg(windows)]
    backend: Option<ManagedBackend>,
    transport: Transport,
    pending: Mutex<HashMap<String, Arc<Pending>>>,
}

struct Pending {
    request: Mutex<Option<Prepared>>,
    response: tokio::sync::Mutex<Option<reqwest::Response>>,
    cancel: CancellationToken,
}

#[derive(Deserialize)]
struct Prepared {
    managed: bool,
    origin: String,
    url: String,
    method: String,
    headers: Vec<(String, String)>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct HostInfo {
    platform: &'static str,
    managed_origin: Option<String>,
}

#[derive(Serialize)]
struct ResponseHead {
    status: u16,
    headers: Vec<(String, String)>,
}

impl Host {
    fn entry(&self, id: &str) -> Result<Arc<Pending>, &'static str> {
        self.pending
            .lock()
            .map_err(|_| INVALID)?
            .get(id)
            .cloned()
            .ok_or(CANCELLED)
    }

    fn close(&self, id: &str) {
        if let Ok(mut pending) = self.pending.lock()
            && let Some(entry) = pending.remove(id)
        {
            entry.cancel.cancel();
        }
    }

    fn cancel_all(&self) {
        if let Ok(mut pending) = self.pending.lock() {
            for (_, entry) in pending.drain() {
                entry.cancel.cancel();
            }
        }
    }
}

#[tauri::command]
fn orion_host(_state: State<'_, Host>) -> HostInfo {
    HostInfo {
        #[cfg(windows)]
        platform: "windows",
        #[cfg(target_os = "android")]
        platform: "android",
        #[cfg(target_os = "ios")]
        platform: "ios",
        #[cfg(windows)]
        managed_origin: _state
            .backend
            .as_ref()
            .map(|backend| backend.origin().to_owned()),
        #[cfg(any(target_os = "android", target_os = "ios"))]
        managed_origin: None,
    }
}

#[tauri::command]
fn orion_prepare(
    id: String,
    request: Prepared,
    state: State<'_, Host>,
) -> Result<(), &'static str> {
    if id.len() != 36
        || !id
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() || byte == b'-')
    {
        return Err(INVALID);
    }
    let mut pending = state.pending.lock().map_err(|_| INVALID)?;
    if pending.len() >= 64 || pending.contains_key(&id) {
        return Err(INVALID);
    }
    pending.insert(
        id,
        Arc::new(Pending {
            request: Mutex::new(Some(request)),
            response: tokio::sync::Mutex::new(None),
            cancel: CancellationToken::new(),
        }),
    );
    Ok(())
}

#[tauri::command]
#[cfg(windows)]
async fn orion_start(
    request: IpcRequest<'_>,
    state: State<'_, Host>,
) -> Result<ResponseHead, &'static str> {
    let id = request
        .headers()
        .get("x-orion-request")
        .and_then(|header| header.to_str().ok())
        .ok_or(INVALID)?
        .to_owned();
    let InvokeBody::Raw(body) = request.body() else {
        state.close(&id);
        return Err(INVALID);
    };
    start(&state, &id, body.clone()).await
}

#[cfg(any(target_os = "android", target_os = "ios"))]
#[tauri::command]
async fn orion_start_mobile(
    id: String,
    body: String,
    state: State<'_, Host>,
) -> Result<ResponseHead, &'static str> {
    let Ok(bytes) = STANDARD.decode(body) else {
        state.close(&id);
        return Err(INVALID);
    };
    start(&state, &id, bytes).await
}

async fn start(state: &Host, id: &str, body: Vec<u8>) -> Result<ResponseHead, &'static str> {
    let entry = state.entry(id)?;
    let prepared = entry
        .request
        .lock()
        .map_err(|_| INVALID)?
        .take()
        .ok_or(INVALID)?;
    #[cfg(windows)]
    let destination = if prepared.managed {
        let Some(backend) = &state.backend else {
            state.close(id);
            return Err("Managed Orion backend is unavailable");
        };
        Destination::Managed(backend)
    } else {
        Destination::Remote {
            origin: &prepared.origin,
        }
    };
    #[cfg(any(target_os = "android", target_os = "ios"))]
    let destination = {
        if prepared.managed {
            state.close(id);
            return Err(INVALID);
        }
        Destination::Remote {
            origin: &prepared.origin,
        }
    };
    let outgoing = Request {
        url: prepared.url,
        method: prepared.method,
        headers: prepared.headers,
        body,
    };
    let result = tokio::select! {
        _ = entry.cancel.cancelled() => Err(CANCELLED),
        result = state.transport.send(destination, outgoing) => result.map_err(|_| "Orion server request failed"),
    };
    match result {
        Ok(response) => {
            let head = ResponseHead {
                status: response.status().as_u16(),
                headers: response
                    .headers()
                    .iter()
                    .filter_map(|(name, value)| {
                        if name == "set-cookie" {
                            return None;
                        }
                        Some((name.to_string(), value.to_str().ok()?.to_owned()))
                    })
                    .collect(),
            };
            *entry.response.lock().await = Some(response);
            Ok(head)
        }
        Err(error) => {
            state.close(id);
            Err(error)
        }
    }
}

#[tauri::command]
#[cfg(windows)]
async fn orion_read(id: String, state: State<'_, Host>) -> Result<IpcResponse, &'static str> {
    read(&state, &id).await.map(IpcResponse::new)
}

#[cfg(any(target_os = "android", target_os = "ios"))]
#[tauri::command]
async fn orion_read_mobile(id: String, state: State<'_, Host>) -> Result<String, &'static str> {
    read(&state, &id).await.map(|bytes| STANDARD.encode(bytes))
}

async fn read(state: &Host, id: &str) -> Result<Vec<u8>, &'static str> {
    let entry = state.entry(id)?;
    let mut response = entry.response.lock().await;
    let response = response.as_mut().ok_or(INVALID)?;
    let result = tokio::select! {
        _ = entry.cancel.cancelled() => Err(CANCELLED),
        result = response.chunk() => result.map_err(|_| "Orion response stream failed"),
    };
    match result {
        Ok(Some(bytes)) => Ok(bytes.to_vec()),
        Ok(None) => {
            state.close(id);
            Ok(Vec::new())
        }
        Err(error) => {
            state.close(id);
            Err(error)
        }
    }
}

#[tauri::command]
fn orion_close(id: String, state: State<'_, Host>) {
    state.close(&id);
}

#[tauri::command]
#[cfg(any(windows, target_os = "ios"))]
fn orion_vault_get(origin: String) -> Result<Option<serde_json::Value>, &'static str> {
    let value = vault::get(&origin).map_err(|_| "Orion credential vault read failed")?;
    value
        .map(|value| serde_json::from_slice(&value).map_err(|_| "Invalid stored Orion credential"))
        .transpose()
}

#[tauri::command]
#[cfg(any(windows, target_os = "ios"))]
fn orion_vault_set(origin: String, pair: serde_json::Value) -> Result<(), &'static str> {
    let value = serde_json::to_vec(&pair).map_err(|_| "Invalid Orion credential")?;
    vault::set(&origin, &value).map_err(|_| "Orion credential vault write failed")
}

#[tauri::command]
#[cfg(any(windows, target_os = "ios"))]
fn orion_vault_clear(origin: String) -> Result<(), &'static str> {
    vault::clear(&origin).map_err(|_| "Orion credential vault removal failed")
}

#[cfg(target_os = "android")]
type AndroidVault = tauri::plugin::PluginHandle<tauri::Wry>;

#[cfg(target_os = "android")]
#[tauri::command]
async fn orion_vault_get(
    origin: String,
    vault: State<'_, AndroidVault>,
) -> Result<Option<serde_json::Value>, &'static str> {
    #[derive(Deserialize)]
    struct Stored {
        pair: Option<serde_json::Value>,
    }
    vault
        .run_mobile_plugin_async::<Stored>("get", serde_json::json!({ "origin": origin }))
        .await
        .map(|value| value.pair)
        .map_err(|_| "Orion credential vault read failed")
}

#[cfg(target_os = "android")]
#[tauri::command]
async fn orion_vault_set(
    origin: String,
    pair: serde_json::Value,
    vault: State<'_, AndroidVault>,
) -> Result<(), &'static str> {
    vault
        .run_mobile_plugin_async::<()>("set", serde_json::json!({ "origin": origin, "pair": pair }))
        .await
        .map_err(|_| "Orion credential vault write failed")
}

#[cfg(target_os = "android")]
#[tauri::command]
async fn orion_vault_clear(
    origin: String,
    vault: State<'_, AndroidVault>,
) -> Result<(), &'static str> {
    vault
        .run_mobile_plugin_async::<()>("clear", serde_json::json!({ "origin": origin }))
        .await
        .map_err(|_| "Orion credential vault removal failed")
}

fn allow_navigation(url: &url::Url) -> bool {
    matches!(
        (url.scheme(), url.host_str()),
        ("tauri", Some("localhost")) | ("http" | "https", Some("tauri.localhost"))
    )
}

pub fn run() {
    let builder = tauri::Builder::default();
    #[cfg(windows)]
    let builder = builder
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window(WINDOW) {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let backend_path = app.path().resource_dir()?.join("backend/OrionBackend.exe");
            let data_path = app.path().app_local_data_dir()?.join("managed");
            let backend = ManagedBackend::start(&backend_path, &data_path).ok();
            app.manage(Host {
                backend,
                transport: Transport::new()?,
                pending: Mutex::new(HashMap::new()),
            });
            WebviewWindowBuilder::new(app, WINDOW, WebviewUrl::App("_shell.html".into()))
                .title("Orion")
                .inner_size(1200.0, 780.0)
                .min_inner_size(480.0, 480.0)
                .devtools(false)
                .on_navigation(allow_navigation)
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .on_page_load(|window, payload| {
                    if payload.event() == tauri::webview::PageLoadEvent::Started {
                        window.state::<Host>().cancel_all();
                    }
                })
                .build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            orion_host,
            orion_prepare,
            orion_start,
            orion_read,
            orion_close,
            orion_vault_get,
            orion_vault_set,
            orion_vault_clear
        ]);
    #[cfg(target_os = "android")]
    let builder = builder.plugin(
        tauri::plugin::Builder::new("orion-vault")
            .setup(|app, api| {
                app.manage(api.register_android_plugin("io.orion.desktop", "OrionVaultPlugin")?);
                Ok(())
            })
            .build(),
    );
    #[cfg(any(target_os = "android", target_os = "ios"))]
    let builder = builder
        .setup(|app| {
            app.manage(Host {
                transport: Transport::new()?,
                pending: Mutex::new(HashMap::new()),
            });
            WebviewWindowBuilder::new(app, WINDOW, WebviewUrl::App("_shell.html".into()))
                .devtools(false)
                .on_navigation(allow_navigation)
                .on_page_load(|window, payload| {
                    if payload.event() == tauri::webview::PageLoadEvent::Started {
                        window.state::<Host>().cancel_all();
                    }
                })
                .build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            orion_host,
            orion_prepare,
            orion_start_mobile,
            orion_read_mobile,
            orion_close,
            orion_vault_get,
            orion_vault_set,
            orion_vault_clear
        ]);
    builder
        .build(tauri::generate_context!())
        .expect("build Orion native application")
        .run(|app, event| {
            if matches!(event, RunEvent::Exit) {
                let state = app.state::<Host>();
                state.cancel_all();
                #[cfg(windows)]
                if let Some(backend) = &state.backend {
                    let _ = backend.shutdown();
                }
            }
        });
}
