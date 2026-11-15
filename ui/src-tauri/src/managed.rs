use std::{
    fs::{self, File, OpenOptions},
    io::{self, BufRead, BufReader, Read, Write},
    mem::size_of,
    net::{Ipv4Addr, SocketAddrV4},
    os::windows::{
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
        process::CommandExt,
    },
    path::Path,
    process::{Child, Command, Stdio},
    sync::{Mutex, mpsc},
    thread,
    time::{Duration, Instant},
};

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde::Deserialize;
use windows_sys::Win32::System::{
    JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
        SetInformationJobObject,
    },
    Threading::CREATE_NO_WINDOW,
};

#[cfg(test)]
use crate::transport::OWNER_HEADER;
const READINESS_TIMEOUT: Duration = Duration::from_secs(40);
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(12);
const READINESS_LIMIT: u64 = 512;

/// Owns the private bundled backend and its stdin. The owner token stays in the host.
pub struct ManagedBackend {
    process: Mutex<OwnedProcess>,
    origin: String,
    token: String,
}

impl ManagedBackend {
    pub fn start_configured(
        executable: &Path,
        data_dir: &Path,
        configure: impl FnOnce(&mut Command),
    ) -> io::Result<Self> {
        if !executable.is_absolute() || !data_dir.is_absolute() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Managed backend paths must be absolute",
            ));
        }
        let executable_dir = executable.parent().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "Missing backend executable path",
            )
        })?;
        fs::create_dir_all(data_dir)?;
        // Keep Python and bootloader diagnostics even when no console is attached.
        let mut log = OpenOptions::new()
            .create(true)
            .append(true)
            .open(data_dir.join("desktop-backend.log"))?;
        let result = Self::spawn(executable, executable_dir, data_dir, log.try_clone()?, configure);
        if let Err(error) = &result {
            let _ = writeln!(log, "Managed backend startup failed: {error}");
        }
        result
    }

    fn spawn(
        executable: &Path,
        executable_dir: &Path,
        data_dir: &Path,
        log: File,
        configure: impl FnOnce(&mut Command),
    ) -> io::Result<Self> {
        let mut random = [0; 32];
        getrandom::fill(&mut random)
            .map_err(|_| io::Error::other("Cannot generate the managed owner token"))?;
        let token = URL_SAFE_NO_PAD.encode(random);
        let job = create_job()?;
        let mut command = Command::new(executable);
        command
            .current_dir(executable_dir)
            .creation_flags(CREATE_NO_WINDOW)
            .env_remove("PYTHONPATH")
            .env_remove("PYTHONHOME")
            .env_remove("VIRTUAL_ENV")
            .env_remove("ORION_UI_DIR")
            .env_remove("ORION_DATABASE_PATH")
            .env_remove("ORION_LOG_PATH")
            .env("ORION_DATA_DIR", data_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::from(log));
        configure(&mut command);
        let mut child = command.spawn()?;
        // The backend waits for its token before creating the application or spawning work.
        if unsafe { AssignProcessToJobObject(job.as_raw_handle(), child.as_raw_handle()) } == 0 {
            let error = io::Error::last_os_error();
            drop(child.stdin.take());
            if child.kill().is_ok() {
                let _ = child.wait();
            }
            return Err(error);
        }
        let mut process = OwnedProcess {
            child,
            job: Some(job),
        };
        let stdout = process
            .child
            .stdout
            .take()
            .expect("managed child stdout is piped");
        let (ready, receiver) = mpsc::sync_channel(1);
        thread::Builder::new()
            .name("orion-managed-stdout".into())
            .spawn(move || {
                let mut reader = BufReader::new(stdout);
                let result = read_origin(&mut reader);
                if ready.send(result).is_ok() {
                    let _ = io::copy(&mut reader, &mut io::sink());
                }
            })?;
        let stdin = process
            .child
            .stdin
            .as_mut()
            .expect("managed child stdin is piped");
        writeln!(stdin, "{token}")?;
        stdin.flush()?;
        let origin = receiver
            .recv_timeout(READINESS_TIMEOUT)
            .map_err(|error| match error {
                mpsc::RecvTimeoutError::Timeout => io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Managed backend did not report readiness",
                ),
                mpsc::RecvTimeoutError::Disconnected => io::Error::new(
                    io::ErrorKind::BrokenPipe,
                    "Managed backend closed its readiness pipe",
                ),
            })??;
        Ok(Self {
            process: Mutex::new(process),
            origin,
            token,
        })
    }

    pub fn origin(&self) -> &str {
        &self.origin
    }

    pub(crate) fn owner_token(&self) -> &str {
        &self.token
    }

    pub fn shutdown(&self) -> io::Result<()> {
        self.process
            .lock()
            .map_err(|_| io::Error::other("Managed backend process state unavailable"))?
            .stop()
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Readiness {
    #[serde(rename = "type")]
    event: String,
    origin: String,
}

fn read_origin(reader: &mut impl BufRead) -> io::Result<String> {
    let invalid = || {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "Invalid managed backend readiness",
        )
    };
    let mut line = Vec::new();
    reader.take(READINESS_LIMIT).read_until(b'\n', &mut line)?;
    if line.last() != Some(&b'\n') {
        return Err(invalid());
    }
    let ready: Readiness = serde_json::from_slice(&line).map_err(|_| invalid())?;
    let address: SocketAddrV4 = ready
        .origin
        .strip_prefix("http://")
        .ok_or_else(invalid)?
        .parse()
        .map_err(|_| invalid())?;
    if ready.event != "ready"
        || *address.ip() != Ipv4Addr::LOCALHOST
        || address.port() == 0
        || ready.origin != format!("http://{address}")
    {
        return Err(invalid());
    }
    Ok(ready.origin)
}

fn create_job() -> io::Result<OwnedHandle> {
    let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
    if handle.is_null() {
        return Err(io::Error::last_os_error());
    }
    // CreateJobObjectW returned a new handle. OwnedHandle closes it on every exit path.
    let job = unsafe { OwnedHandle::from_raw_handle(handle) };
    let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if unsafe {
        SetInformationJobObject(
            job.as_raw_handle(),
            JobObjectExtendedLimitInformation,
            std::ptr::from_ref(&limits).cast(),
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(job)
}

struct OwnedProcess {
    child: Child,
    job: Option<OwnedHandle>,
}

impl OwnedProcess {
    fn stop(&mut self) -> io::Result<()> {
        let Some(_job) = self.job.take() else {
            return Ok(());
        };
        drop(self.child.stdin.take());
        let deadline = Instant::now() + SHUTDOWN_TIMEOUT;
        while Instant::now() < deadline {
            if let Some(status) = self.child.try_wait()? {
                return if status.success() {
                    Ok(())
                } else {
                    Err(io::Error::other("Managed backend exited with an error"))
                };
            }
            thread::sleep(Duration::from_millis(50));
        }
        // The job handle closes here and terminates any processes still running.
        Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "Managed backend did not stop after pipe closure",
        ))
    }
}

impl Drop for OwnedProcess {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{env, net::TcpStream, path::PathBuf};

    #[test]
    fn accepts_only_bounded_loopback_readiness() {
        fn event(body: &str) -> io::Result<String> {
            read_origin(&mut body.as_bytes())
        }
        assert_eq!(
            event("{\"type\":\"ready\",\"origin\":\"http://127.0.0.1:49821\"}\n").unwrap(),
            "http://127.0.0.1:49821"
        );
        for origin in [
            "https://127.0.0.1:49821",
            "http://localhost:49821",
            "http://127.0.0.1:0",
            "http://127.0.0.1:49821/path",
            "http://127.0.0.1:49821@remote.example",
        ] {
            assert!(event(&format!("{{\"type\":\"ready\",\"origin\":\"{origin}\"}}\n")).is_err());
        }
        assert!(event("{\"type\":\"ready\",\"origin\":\"http://127.0.0.1:49821\"}").is_err());
        assert!(event(&format!("{}\n", " ".repeat(512))).is_err());
    }

    #[test]
    #[ignore = "requires the frozen Windows backend and an isolated data directory"]
    fn frozen_backend_authenticates_and_shuts_down() {
        use crate::transport::{Destination, Request, Transport};

        let path = |name| PathBuf::from(env::var_os(name).expect("missing fixture path"));
        let executable = path("ORION_TEST_MANAGED_EXE");
        let data = path("ORION_TEST_MANAGED_DATA_DIR");
        let backend = ManagedBackend::start_configured(&executable, &data, |_| {}).unwrap();
        let address: SocketAddrV4 = backend
            .origin()
            .strip_prefix("http://")
            .unwrap()
            .parse()
            .unwrap();
        let status = |header: Option<&str>| {
            let mut connection = TcpStream::connect(address).unwrap();
            connection
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            write!(
                connection,
                "GET /api/health HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n"
            )
            .unwrap();
            if let Some(token) = header {
                write!(connection, "{OWNER_HEADER}: {token}\r\n").unwrap();
            }
            connection.write_all(b"\r\n").unwrap();
            let mut response = String::new();
            connection.read_to_string(&mut response).unwrap();
            response.lines().next().unwrap().to_owned()
        };
        assert!(status(None).starts_with("HTTP/1.1 401 "));
        assert!(status(Some("invalid")).starts_with("HTTP/1.1 401 "));
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        runtime.block_on(async {
            let transport = Transport::new().unwrap();
            let response = transport
                .send(
                    Destination::Managed(&backend),
                    Request {
                        url: format!("{}/api/health", backend.origin()),
                        method: "GET".into(),
                        headers: vec![],
                        body: vec![],
                    },
                )
                .await
                .unwrap();
            assert!(response.status().is_success());
        });
        backend.shutdown().unwrap();
        assert!(TcpStream::connect(address).is_err());
        assert!(data.join("orion.db").is_file());
    }
}
