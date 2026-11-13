//! Native HTTP client shared by managed and remote Orion connections.

use std::{io, time::Duration};

use reqwest::{
    Client, Method, Response,
    header::{AUTHORIZATION, HeaderMap, HeaderName, HeaderValue},
    redirect::Policy,
};
use url::Url;

#[cfg(windows)]
use crate::managed::ManagedBackend;

pub(crate) const OWNER_HEADER: &str = "x-orion-managed-token";

pub struct Request {
    pub url: String,
    pub method: String,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

pub enum Destination<'a> {
    #[cfg(windows)]
    Managed(&'a ManagedBackend),
    Remote {
        origin: &'a str,
    },
}

pub struct Transport {
    client: Client,
}

impl Transport {
    pub fn new() -> io::Result<Self> {
        let builder = Client::builder();
        #[cfg(target_os = "android")]
        let builder = {
            let roots = rustls::RootCertStore {
                roots: webpki_roots::TLS_SERVER_ROOTS.to_vec(),
            };
            let tls = rustls::ClientConfig::builder_with_provider(
                rustls::crypto::aws_lc_rs::default_provider().into(),
            )
            .with_safe_default_protocol_versions()
            .map_err(|_| io::Error::other("Cannot initialize Orion TLS"))?
            .with_root_certificates(roots)
            .with_no_client_auth();
            builder.tls_backend_preconfigured(tls)
        };
        builder
            .connect_timeout(Duration::from_secs(10))
            .redirect(Policy::none())
            .retry(reqwest::retry::never())
            .no_proxy()
            .build()
            .map(|client| Self { client })
            .map_err(|_| io::Error::other("Cannot initialize Orion HTTP transport"))
    }

    /// Response headers and body remain available for incremental reads by the native host.
    pub async fn send(
        &self,
        destination: Destination<'_>,
        request: Request,
    ) -> io::Result<Response> {
        let (origin, managed_token): (&str, Option<&str>) = match destination {
            #[cfg(windows)]
            Destination::Managed(backend) => (backend.origin(), Some(backend.owner_token())),
            Destination::Remote { origin } => (origin, None),
        };
        let url = validate_url(&request.url, origin)?;
        let method =
            Method::from_bytes(request.method.as_bytes()).map_err(|_| invalid_request())?;
        if !matches!(
            method,
            Method::GET | Method::POST | Method::PUT | Method::PATCH | Method::DELETE
        ) || method == Method::GET && !request.body.is_empty()
        {
            return Err(invalid_request());
        }
        let mut headers = request_headers(request.headers, managed_token.is_some())?;
        if let Some(token) = managed_token {
            let mut value = HeaderValue::from_str(token).map_err(|_| invalid_request())?;
            value.set_sensitive(true);
            headers.insert(HeaderName::from_static(OWNER_HEADER), value);
        }
        let response = self
            .client
            .request(method, url)
            .headers(headers)
            .body(request.body)
            .send()
            .await
            .map_err(|_| io::Error::other("Orion server request failed"))?;
        if response.status().is_redirection() {
            return Err(io::Error::other("Orion server returned a redirect"));
        }
        Ok(response)
    }
}

fn invalid_request() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidInput,
        "Invalid native Orion API request",
    )
}

fn validate_url(raw: &str, origin: &str) -> io::Result<Url> {
    let url = Url::parse(raw).map_err(|_| invalid_request())?;
    let loopback = matches!(url.host_str(), Some("127.0.0.1" | "[::1]"));
    if url.origin().ascii_serialization() != origin
        || !(url.scheme() == "https" || url.scheme() == "http" && loopback)
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
        || !url.path().starts_with("/api/")
    {
        return Err(invalid_request());
    }
    Ok(url)
}

fn is_access_token(value: &HeaderValue) -> bool {
    let Some(token) = value.as_bytes().strip_prefix(b"Bearer orion_access_") else {
        return false;
    };
    token.len() == 43
        && token
            .iter()
            .all(|&byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn request_headers(values: Vec<(String, String)>, managed: bool) -> io::Result<HeaderMap> {
    let mut headers = HeaderMap::new();
    for (name, value) in values {
        let name = HeaderName::from_bytes(name.as_bytes()).map_err(|_| invalid_request())?;
        let mut value = HeaderValue::from_str(&value).map_err(|_| invalid_request())?;
        if name == AUTHORIZATION {
            if managed || !is_access_token(&value) {
                return Err(invalid_request());
            }
            value.set_sensitive(true);
        } else if !matches!(
            name.as_str(),
            "accept"
                | "content-type"
                | "last-event-id"
                | "x-desktop-session"
                | "x-endpoint-path"
                | "x-overwrite"
        ) {
            return Err(invalid_request());
        }
        if headers.insert(name, value).is_some() {
            return Err(invalid_request());
        }
    }
    Ok(headers)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_origin_path_and_credential_boundaries() {
        let origin = "https://orion.example";
        assert!(validate_url("https://orion.example/api/doctor?detail=1", origin).is_ok());
        for raw in [
            "https://other.example/api/doctor",
            "https://orion.example/api/../private",
            "https://key@orion.example/api/doctor",
            "https://orion.example/api/doctor#private",
            "http://orion.example/api/doctor",
        ] {
            assert!(validate_url(raw, origin).is_err());
        }
        for name in [
            OWNER_HEADER,
            "Cookie",
            "Origin",
            "Host",
            "Proxy-Authorization",
        ] {
            assert!(request_headers(vec![(name.into(), "arbitrary".into())], false).is_err());
        }
        let header = vec![(
            "Authorization".into(),
            format!("Bearer orion_access_{}", "a".repeat(43)),
        )];
        assert!(request_headers(header.clone(), true).is_err());
        assert!(request_headers(header, false).unwrap()[AUTHORIZATION].is_sensitive());
        assert!(request_headers(vec![("Last-Event-Id".into(), "42".into())], true).is_ok());
    }

    #[test]
    fn reads_stream_chunks_and_refuses_redirects_on_loopback() {
        use std::{
            io::{Read, Write},
            net::TcpListener,
            sync::mpsc,
            thread,
        };
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let origin = format!("http://{}", listener.local_addr().unwrap());
        let (first_read, allow_next) = mpsc::channel();
        let fixture = thread::spawn(move || {
            for (index, response) in [
                "HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n3\r\none\r\n",
                "HTTP/1.1 302 Found\r\nConnection: close\r\nContent-Length: 0\r\nLocation: https://remote.invalid/api/doctor\r\n\r\n",
            ].into_iter().enumerate() {
                let (mut connection, _) = listener.accept().unwrap();
                connection
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut head = Vec::new();
                while !head.ends_with(b"\r\n\r\n") && head.len() < 2048 {
                    let mut byte = [0];
                    connection.read_exact(&mut byte).unwrap();
                    head.push(byte[0]);
                }
                assert!(head.starts_with(b"GET /api/doctor HTTP/1.1\r\n"));
                connection.write_all(response.as_bytes()).unwrap();
                if index == 0 {
                    allow_next.recv_timeout(Duration::from_secs(5)).unwrap();
                    connection.write_all(b"3\r\ntwo\r\n0\r\n\r\n").unwrap();
                }
            }
        });
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        runtime.block_on(async {
            let transport = Transport::new().unwrap();
            let send = || {
                transport.send(
                    Destination::Remote { origin: &origin },
                    Request {
                        url: format!("{origin}/api/doctor"),
                        method: "GET".into(),
                        headers: vec![],
                        body: vec![],
                    },
                )
            };
            let mut response = send().await.unwrap();
            assert_eq!(response.headers()["content-type"], "text/event-stream");
            assert_eq!(response.chunk().await.unwrap().unwrap(), "one");
            first_read.send(()).unwrap();
            assert_eq!(response.chunk().await.unwrap().unwrap(), "two");
            assert!(response.chunk().await.unwrap().is_none());
            assert_eq!(
                send().await.unwrap_err().to_string(),
                "Orion server returned a redirect"
            );
        });
        fixture.join().unwrap();
    }
}
