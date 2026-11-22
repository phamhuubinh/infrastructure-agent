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
    #[cfg(windows)]
    backend_error: Option<&'static str>,
    #[cfg(windows)]
    keep_host_running: bool,
    #[cfg(windows)]
    host_origin: Option<String>,
    #[cfg(windows)]
    serve: tokio::sync::Mutex<Option<&'static str>>,
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
    #[cfg(windows)]
    managed_error: Option<&'static str>,
    #[cfg(windows)]
    host_mode: bool,
    #[cfg(windows)]
    host_origin: Option<String>,
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
        #[cfg(windows)]
        managed_error: _state.backend_error,
        #[cfg(windows)]
        host_mode: _state.keep_host_running,
        #[cfg(windows)]
        host_origin: _state.host_origin.clone(),
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
struct AndroidQr(tauri::plugin::PluginHandle<tauri::Wry>);

#[cfg(target_os = "android")]
#[tauri::command]
async fn orion_scan_qr(scanner: State<'_, AndroidQr>) -> Result<Option<String>, &'static str> {
    #[derive(Deserialize)]
    struct ScanResult {
        value: Option<String>,
    }
    scanner
        .0
        .run_mobile_plugin_async::<ScanResult>("scan", ())
        .await
        .map(|result| result.value)
        .map_err(|_| "Orion QR scan failed")
}

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

#[cfg(windows)]
#[tauri::command]
async fn orion_stop_host(app: tauri::AppHandle, host: State<'_, Host>) -> Result<(), &'static str> {
    if !host.keep_host_running {
        return Err("Host Mode is not active");
    }
    let _operation = host.serve.lock().await;
    app.exit(0);
    Ok(())
}

#[cfg(windows)]
#[tauri::command]
async fn orion_tailscale_status(host: State<'_, Host>) -> Result<crate::tailscale::Status, &'static str> {
    let operation = host.serve.lock().await;
    let settings = remote_settings()?;
    let backend = host.backend.as_ref().map(|backend| backend.origin().to_owned());
    Ok(crate::tailscale::inspect(backend, host.host_origin.clone()).await
        .with_settings(settings.remote_access,
            settings.serve_owned, *operation))
}

#[cfg(windows)]
#[tauri::command]
async fn orion_tailscale_set_enabled(app: tauri::AppHandle, host: State<'_, Host>, enabled: bool) -> Result<crate::tailscale::Status, &'static str> {
    let mut operation = host.serve.lock().await;
    let mut settings = remote_settings()?;
    *operation = None;
    if !enabled {
        if settings.funnel_owned {
            crate::tailscale::apply_funnel(&settings.origin, false, false).await?;
            settings.funnel_owned = false;
        }
        if settings.serve_owned {
            crate::tailscale::apply(&settings.origin, false, true).await?;
        }
        settings.enabled = false;
        settings.remote_access = false;
        settings.serve_pending = false;
        settings.serve_owned = false;
        store_remote_settings(settings)?;
        app.request_restart();
        return Ok(crate::tailscale::inspect(None, None).await);
    }
    let backend = host.backend.as_ref().ok_or("Backend cục bộ chưa sẵn sàng.")?;
    if !crate::tailscale::owner_ready(backend, &host.transport).await {
        return Err("Thiết lập và xác minh tài khoản Owner trước khi bật Serve.");
    }
    let detected = crate::tailscale::default_origin().await?;
    let origin = host.host_origin.as_deref().filter(|current| {
        url::Url::parse(current).ok().zip(url::Url::parse(&detected).ok())
            .is_some_and(|(current, detected)| current.host_str() == detected.host_str())
    }).unwrap_or(&detected);
    if settings.serve_owned && settings.origin != origin {
        return Err("URL Serve đã đổi. Hãy tắt cấu hình Orion trước khi bật lại.");
    }
    crate::tailscale::validate_slot(origin).await?;
    let restart = host.host_origin.as_deref() != Some(origin);
    if !restart && backend.origin() != crate::tailscale::HOST_BACKEND {
        return Err("Backend Host Mode chưa lắng nghe đúng cổng.");
    }
    settings.enabled = true;
    settings.autostart = true;
    settings.remote_access = true;
    settings.origin = origin.to_owned();
    settings.serve_pending = restart;
    store_remote_settings(settings)?;
    if restart {
        app.request_restart();
        return Ok(crate::tailscale::inspect(None, None).await.with_settings(true, false, None));
    }
    configure_remote_serve(&host, true).await?;
    let settings = remote_settings()?;
    Ok(crate::tailscale::inspect(Some(backend.origin().to_owned()), Some(origin.to_owned()))
        .await.with_settings(true, settings.serve_owned, None))
}

#[cfg(windows)]
#[tauri::command]
async fn orion_internet_set_enabled(host: State<'_, Host>, enabled: bool, confirmed_public: bool)
    -> Result<crate::tailscale::Status, &'static str> {
    let _operation = host.serve.lock().await;
    let mut settings = remote_settings()?;
    let backend = host.backend.as_ref().ok_or("Backend cục bộ chưa sẵn sàng.")?;
    if !settings.enabled || !settings.remote_access
        || backend.origin() != crate::tailscale::HOST_BACKEND
        || host.host_origin.as_deref() != Some(settings.origin.as_str()) {
        return Err("Bật Host Mode và Serve HTTPS riêng tư trước khi bật Internet.");
    }
    if enabled && (!confirmed_public || !crate::tailscale::owner_ready(backend, &host.transport).await) {
        return Err("Cần Owner với mật khẩu và TOTP, cùng xác nhận công khai URL.");
    }
    crate::tailscale::apply_funnel(&settings.origin, enabled, confirmed_public).await?;
    settings.funnel_owned = enabled;
    let serve_owned = settings.serve_owned;
    if store_remote_settings(settings).is_err() {
        if enabled {
            crate::tailscale::apply_funnel(host.host_origin.as_deref().unwrap_or(""), false, false).await?;
        }
        return Err("Không lưu được cài đặt Internet. Đã yêu cầu quay về Serve riêng tư.");
    }
    Ok(crate::tailscale::inspect(Some(backend.origin().to_owned()), host.host_origin.clone()).await
        .with_settings(true, serve_owned, None))
}

#[cfg(windows)]
fn remote_settings() -> Result<crate::host_settings::Settings, &'static str> {
    crate::host_settings::Settings::read().map(Option::unwrap_or_default)
        .map_err(|_| "Không đọc được cài đặt truy cập từ xa.")
}

#[cfg(windows)]
fn store_remote_settings(settings: crate::host_settings::Settings) -> Result<(), &'static str> {
    settings.save().map_err(|_| "Không lưu được cài đặt truy cập từ xa.")
}

#[cfg(windows)]
async fn configure_remote_serve(host: &Host, requested: bool) -> Result<(), &'static str> {
    let mut settings = remote_settings()?;
    if !settings.remote_access {
        return Ok(());
    }
    if settings.funnel_owned {
        // Persisted Funnel is inspected, never silently enabled on startup.
        return Ok(());
    }
    let allow_uac = requested || settings.serve_pending;
    if settings.serve_pending {
        settings.serve_pending = false;
        store_remote_settings(settings)?;
        settings = remote_settings()?;
    }
    let backend = host.backend.as_ref().ok_or("Backend Host Mode chưa sẵn sàng.")?;
    if backend.origin() != crate::tailscale::HOST_BACKEND
        || host.host_origin.as_deref() != Some(settings.origin.as_str())
        || !crate::tailscale::owner_ready(backend, &host.transport).await
    {
        return Err("Host Mode cần backend và Owner đã xác minh để bật Serve.");
    }
    if crate::tailscale::apply(&settings.origin, true, allow_uac).await? {
        settings.serve_owned = true;
        store_remote_settings(settings)?;
    }
    Ok(())
}

#[cfg(windows)]
#[tauri::command]
fn orion_host_settings() -> Result<crate::host_settings::Status, String> {
    crate::host_settings::Settings::status().map_err(|error| error.to_string())
}

#[cfg(windows)]
#[tauri::command]
fn orion_save_host_settings(app: tauri::AppHandle, mut settings: crate::host_settings::Settings) -> Result<(), String> {
    if remote_settings()?.remote_access {
        return Err("Tắt truy cập từ xa trước khi sửa Host Mode.".into());
    }
    settings.remote_access = false;
    settings.serve_owned = false;
    settings.serve_pending = false;
    settings.save().map_err(|error| error.to_string())?;
    app.request_restart();
    Ok(())
}

pub fn run() {
    let builder = tauri::Builder::default();
    #[cfg(windows)]
    let builder = builder
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window(WINDOW) {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let settings = crate::host_settings::Settings::read()?;
            let backend_path = app.path().resource_dir()?.join("backend/OrionBackend.exe");
            let data_path = app.path().app_local_data_dir()?.join("managed");
            let (backend, backend_error) = match ManagedBackend::start_configured(&backend_path, &data_path, |child| {
                if let Some(settings) = &settings {
                    settings.configure(child);
                }
            }) {
                Ok(backend) => (Some(backend), None),
                Err(error) => {
                    let reason = match error.kind() {
                        std::io::ErrorKind::NotFound => "Không tìm thấy tệp backend cục bộ.",
                        std::io::ErrorKind::PermissionDenied => {
                            "Orion không có quyền mở backend hoặc thư mục dữ liệu."
                        }
                        std::io::ErrorKind::TimedOut => {
                            "Backend cục bộ khởi động quá thời gian chờ."
                        }
                        _ => "Backend cục bộ không khởi động được.",
                    };
                    (None, Some(reason))
                }
            };
            let configured_host = settings.as_ref().map(|settings| settings.enabled)
                .unwrap_or_else(|| std::env::var("ORION_DESKTOP_HOST_MODE").as_deref() == Ok("1"));
            let keep_host_running = backend.is_some() && configured_host;
            let host_origin = if keep_host_running {
                settings.as_ref().map(|settings| settings.origin.clone())
                    .or_else(|| std::env::var("ORION_PUBLIC_ORIGIN").ok())
            } else { None };
            app.manage(Host {
                backend,
                keep_host_running,
                host_origin,
                serve: Default::default(),
                backend_error,
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
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let host = handle.state::<Host>();
                let mut operation = host.serve.lock().await;
                *operation = configure_remote_serve(&host, false).await.err();
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            orion_host,
            orion_stop_host,
            orion_host_settings,
            orion_tailscale_status,
            orion_tailscale_set_enabled,
            orion_internet_set_enabled,
            orion_save_host_settings,
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
        tauri::plugin::Builder::<_, ()>::new("orion-vault")
            .setup(|app, api| {
                app.manage(api.register_android_plugin("io.orion.desktop", "OrionVaultPlugin")?);
                Ok(())
            })
            .build(),
    ).plugin(
        tauri::plugin::Builder::<_, ()>::new("orion-qr")
            .setup(|app, api| {
                app.manage(AndroidQr(
                    api.register_android_plugin("io.orion.desktop", "OrionQrPlugin")?,
                ));
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
            #[cfg(target_os = "android")]
            orion_scan_qr,
            orion_close,
            orion_vault_get,
            orion_vault_set,
            orion_vault_clear
        ]);
    builder
        .build(tauri::generate_context!())
        .expect("build Orion native application")
        .run(|app, event| {
            #[cfg(windows)]
            if let RunEvent::WindowEvent {
                label,
                event: tauri::WindowEvent::CloseRequested { api, .. },
                ..
            } = &event
            {
                if label == WINDOW && app.state::<Host>().keep_host_running {
                    if let Some(window) = app.get_webview_window(WINDOW) {
                        if window.hide().is_ok() {
                            api.prevent_close();
                        }
                    }
                }
            }
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
