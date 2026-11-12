//! Windows Credential Manager storage for native Orion session tokens.

use std::{io, ptr::NonNull};

use url::Url;
use windows_sys::Win32::{
    Foundation::ERROR_NOT_FOUND,
    Security::Credentials::{
        CRED_MAX_CREDENTIAL_BLOB_SIZE, CRED_PERSIST_LOCAL_MACHINE, CRED_TYPE_GENERIC, CREDENTIALW,
        CredDeleteW, CredFree, CredReadW, CredWriteW,
    },
};

fn target(origin: &str) -> io::Result<Vec<u16>> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput, "Invalid Orion server origin");
    let url = Url::parse(origin).map_err(|_| invalid())?;
    let loopback = matches!(url.host_str(), Some("127.0.0.1" | "[::1]"));
    if origin.len() > 300
        || url.origin().ascii_serialization() != origin
        || !(url.scheme() == "https" || url.scheme() == "http" && loopback)
    {
        return Err(invalid());
    }
    Ok(format!("Orion/NativeSession/v1/{origin}")
        .encode_utf16()
        .chain([0])
        .collect())
}

fn missing(error: &io::Error) -> bool {
    error.raw_os_error() == Some(ERROR_NOT_FOUND as i32)
}

pub fn get(origin: &str) -> io::Result<Option<Vec<u8>>> {
    let target = target(origin)?;
    let mut pointer = std::ptr::null_mut();
    if unsafe { CredReadW(target.as_ptr(), CRED_TYPE_GENERIC, 0, &mut pointer) } == 0 {
        let error = io::Error::last_os_error();
        return if missing(&error) {
            Ok(None)
        } else {
            Err(error)
        };
    }
    let invalid = || {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "Invalid stored Orion credential",
        )
    };
    let buffer = CredentialBuffer(NonNull::new(pointer).ok_or_else(invalid)?);
    // CredReadW owns one allocation containing the record and its blob until CredFree.
    let credential = unsafe { buffer.0.as_ref() };
    let size = credential.CredentialBlobSize;
    if size == 0 || size > CRED_MAX_CREDENTIAL_BLOB_SIZE || credential.CredentialBlob.is_null() {
        return Err(invalid());
    }
    let value = unsafe { std::slice::from_raw_parts(credential.CredentialBlob, size as usize) };
    Ok(Some(value.to_vec()))
}

pub fn set(origin: &str, value: &[u8]) -> io::Result<()> {
    let mut target = target(origin)?;
    if value.is_empty() || value.len() > CRED_MAX_CREDENTIAL_BLOB_SIZE as usize {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Invalid Orion credential size",
        ));
    }
    let credential = CREDENTIALW {
        Type: CRED_TYPE_GENERIC,
        TargetName: target.as_mut_ptr(),
        CredentialBlobSize: value.len() as u32,
        CredentialBlob: value.as_ptr().cast_mut(),
        Persist: CRED_PERSIST_LOCAL_MACHINE,
        ..Default::default()
    };
    // CredWriteW reads the input record and blob synchronously.
    if unsafe { CredWriteW(&credential, 0) } == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

pub fn clear(origin: &str) -> io::Result<()> {
    let target = target(origin)?;
    if unsafe { CredDeleteW(target.as_ptr(), CRED_TYPE_GENERIC, 0) } == 0 {
        let error = io::Error::last_os_error();
        if !missing(&error) {
            return Err(error);
        }
    }
    Ok(())
}

struct CredentialBuffer(NonNull<CREDENTIALW>);

impl Drop for CredentialBuffer {
    fn drop(&mut self) {
        unsafe { CredFree(self.0.as_ptr().cast()) };
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scopes_credentials_to_canonical_server_origins() {
        for origin in [
            "http://127.0.0.1:61888",
            "http://[::1]:61888",
            "https://orion.example",
        ] {
            assert!(target(origin).is_ok());
        }
        for origin in [
            "https://ORION.example",
            "https://orion.example/",
            "https://key@orion.example",
            "http://orion.example",
            "https://orion.example#fragment",
            "https://orion.example:443",
        ] {
            assert!(target(origin).is_err());
        }
    }

    #[test]
    #[ignore = "writes and removes unique synthetic entries in the current Windows credential vault"]
    fn windows_vault_round_trips_and_isolates_origins() {
        let mut random = [0; 16];
        getrandom::fill(&mut random).unwrap();
        let unique = u128::from_ne_bytes(random);
        struct Fixture(String);
        impl Drop for Fixture {
            fn drop(&mut self) {
                let _ = clear(&self.0);
            }
        }
        let one = Fixture(format!("https://orion-test-{unique:x}.invalid"));
        let two = Fixture(format!("https://orion-test-{unique:x}.invalid:8443"));
        assert!(get(&one.0).unwrap().is_none());
        set(&one.0, b"synthetic session").unwrap();
        set(&two.0, b"other synthetic session").unwrap();
        set(&one.0, b"rotated synthetic session").unwrap();
        assert_eq!(
            get(&one.0).unwrap().as_deref(),
            Some(b"rotated synthetic session".as_slice())
        );
        clear(&one.0).unwrap();
        clear(&one.0).unwrap();
        assert!(get(&one.0).unwrap().is_none());
        assert_eq!(
            get(&two.0).unwrap().as_deref(),
            Some(b"other synthetic session".as_slice())
        );
        clear(&two.0).unwrap();
        assert!(get(&two.0).unwrap().is_none());
    }
}
