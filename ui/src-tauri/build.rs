fn main() {
    #[cfg(feature = "desktop")]
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "orion_host",
            "orion_prepare",
            "orion_start",
            "orion_read",
            "orion_start_mobile",
            "orion_read_mobile",
            "orion_close",
            "orion_vault_get",
            "orion_vault_set",
            "orion_vault_clear",
        ]),
    ))
    .expect("build Orion native context");
}
