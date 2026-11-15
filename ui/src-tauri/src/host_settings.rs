use serde::{Deserialize, Serialize};
use std::io;
use winreg::{enums::HKEY_CURRENT_USER, RegKey};

const SETTINGS: &str = r"Software\Orion\DesktopHost";
const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const ENTRY: &str = "OrionDesktopHost";

#[derive(Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Settings {
    pub enabled: bool,
    pub autostart: bool,
    pub origin: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    enabled: bool,
    autostart: bool,
    origin: String,
}

impl Settings {
    pub fn read() -> io::Result<Option<Self>> {
        let key = match RegKey::predef(HKEY_CURRENT_USER).open_subkey(SETTINGS) {
            Ok(key) => key,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e),
        };
        let encoded: String = key.get_value("Config")?;
        serde_json::from_str(&encoded)
            .map(Some)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
    }

    pub fn status() -> io::Result<Status> {
        let settings = Self::read()?.unwrap_or_else(|| Self {
            enabled: std::env::var("ORION_DESKTOP_HOST_MODE").as_deref() == Ok("1"),
            origin: std::env::var("ORION_PUBLIC_ORIGIN").unwrap_or_default(),
            ..Self::default()
        });
        Ok(Status {
            enabled: settings.enabled,
            autostart: settings.autostart,
            origin: settings.origin,
        })
    }

    pub fn configure(&self, child: &mut std::process::Command) {
        child.env("ORION_DESKTOP_HOST_MODE", if self.enabled { "1" } else { "0" });
        if self.enabled {
            child.env("ORION_REMOTE_ACCESS", "1")
                .env("ORION_BIND_HOST", "127.0.0.1")
                .env("ORION_PUBLIC_ORIGIN", &self.origin)
                .env_remove("ORION_AUTH_PASSWORD_HASH")
                .env("ORION_ENDPOINTS", "1");
        }
    }

    pub fn save(mut self) -> io::Result<()> {
        if self.enabled {
            let valid_origin = url::Url::parse(&self.origin).is_ok_and(|url| {
                url.scheme() == "https" &&
                url.origin().ascii_serialization() == self.origin
            });
            if !valid_origin {
                return Err(io::Error::new(io::ErrorKind::InvalidInput, "HTTPS origin is invalid"));
            }
        } else {
            self.autostart = false;
        }
        let user = RegKey::predef(HKEY_CURRENT_USER);
        let (key, _) = user.create_subkey(SETTINGS)?;
        let (run, _) = user.create_subkey(RUN)?;
        if self.autostart {
            let exe = std::env::current_exe()?;
            run.set_value(ENTRY, &format!("\"{}\"", exe.display()))?;
        } else if let Err(error) = run.delete_value(ENTRY) {
            if error.kind() != io::ErrorKind::NotFound {
                return Err(error);
            }
        }
        let encoded = serde_json::json!({
            "enabled": self.enabled,
            "autostart": self.autostart,
            "origin": self.origin,
        });
        key.set_value("Config", &encoded.to_string())
    }
}
