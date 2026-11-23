fn main() {
    #[cfg(feature = "desktop")]
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "orion_host",
            "orion_stop_host",
            "orion_host_settings",
            "orion_check_update",
            "orion_open_update_release",
            "orion_tailscale_status",
            "orion_tailscale_set_enabled",
            "orion_internet_set_enabled",
            "orion_save_host_settings",
            "orion_prepare",
            "orion_start",
            "orion_read",
            "orion_start_mobile",
            "orion_read_mobile",
            "orion_close",
            "orion_vault_get",
            "orion_vault_set",
            "orion_vault_clear",
            "orion_scan_qr",
        ]),
    ))
    .expect("build Orion native context");
}
