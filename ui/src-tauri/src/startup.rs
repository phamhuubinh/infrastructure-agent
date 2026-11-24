use std::{
    fs::{self, OpenOptions},
    io::{self, Write},
    path::PathBuf,
    time::{Instant, SystemTime, UNIX_EPOCH},
};

/// Debug-only benchmark that starts a private sidecar and WebView profile.
#[derive(Clone)]
pub struct StartupProbe {
    pub directory: PathBuf,
    pub backend: PathBuf,
    started: Instant,
}

impl StartupProbe {
    pub fn from_args() -> io::Result<Option<Self>> {
        if !cfg!(debug_assertions) {
            return Ok(None);
        }
        let mut args = std::env::args_os().skip(1);
        if args.next().as_deref() != Some(std::ffi::OsStr::new("--startup-probe")) {
            return Ok(None);
        }
        let directory = args.next().map(PathBuf::from);
        let backend = args.next().map(PathBuf::from);
        let (Some(directory), Some(backend)) = (directory, backend) else {
            return Err(io::Error::other("Missing startup probe paths"));
        };
        let temporary = std::env::temp_dir().canonicalize()?;
        let parent = directory.parent().ok_or(io::Error::other("Missing probe parent"))?;
        if !directory.is_absolute() || parent.canonicalize()? != temporary || !backend.is_absolute()
            || !backend.is_file() || args.next().is_some()
        {
            return Err(io::Error::other("Invalid startup probe paths"));
        }
        fs::create_dir(&directory)?;
        let probe = Self { directory, backend, started: Instant::now() };
        probe.mark("native_entry");
        Ok(Some(probe))
    }

    pub fn mark(&self, phase: &str) {
        if let Ok(mut log) = OpenOptions::new().create(true).append(true)
            .open(self.directory.join("startup.jsonl"))
        {
            let event = serde_json::json!({
                "phase": phase,
                "elapsed_ms": self.started.elapsed().as_millis() as u64,
                "wall_ms": SystemTime::now().duration_since(UNIX_EPOCH)
                    .unwrap_or_default().as_millis() as u64,
            });
            let _ = log.write_all(format!("{event}\n").as_bytes());
        }
    }
}
