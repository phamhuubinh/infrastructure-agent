#[cfg(windows)]
pub mod managed;
#[cfg(any(windows, target_os = "android", target_os = "ios"))]
pub mod transport;
#[cfg(windows)]
pub mod vault;
#[cfg(target_os = "ios")]
#[path = "ios_vault.rs"]
mod vault;

#[cfg(all(feature = "desktop", any(target_os = "android", target_os = "ios")))]
mod app;

#[cfg(all(feature = "desktop", any(target_os = "android", target_os = "ios")))]
#[cfg_attr(
    any(target_os = "android", target_os = "ios"),
    tauri::mobile_entry_point
)]
pub fn run() {
    app::run();
}
