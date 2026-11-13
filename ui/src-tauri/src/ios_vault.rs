//! App-scoped iOS Keychain storage for remote Orion sessions.

use std::io;

use security_framework::{
    base::Error,
    passwords::{
        PasswordOptions, delete_generic_password_options, generic_password,
        set_generic_password_options,
    },
};
use security_framework_sys::base::errSecItemNotFound;
use url::Url;

const SERVICE: &str = "io.orion.desktop.native-session.v1";
const MAX_VALUE: usize = 4096;

fn options(origin: &str) -> io::Result<PasswordOptions> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput, "Invalid Orion server origin");
    let url = Url::parse(origin).map_err(|_| invalid())?;
    let loopback = matches!(url.host_str(), Some("127.0.0.1" | "[::1]"));
    if origin.len() > 300
        || url.origin().ascii_serialization() != origin
        || !(url.scheme() == "https" || url.scheme() == "http" && loopback)
    {
        return Err(invalid());
    }
    let mut options = PasswordOptions::new_generic_password(SERVICE, origin);
    options.set_access_synchronized(Some(false));
    Ok(options)
}

fn keychain_error(error: Error) -> io::Error {
    io::Error::from_raw_os_error(error.code())
}

pub fn get(origin: &str) -> io::Result<Option<Vec<u8>>> {
    match generic_password(options(origin)?) {
        Ok(value) if (1..=MAX_VALUE).contains(&value.len()) => Ok(Some(value)),
        Ok(_) => Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Invalid stored Orion credential size",
        )),
        Err(error) if error.code() == errSecItemNotFound => Ok(None),
        Err(error) => Err(keychain_error(error)),
    }
}

pub fn set(origin: &str, value: &[u8]) -> io::Result<()> {
    if !(1..=MAX_VALUE).contains(&value.len()) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Invalid Orion credential size",
        ));
    }
    set_generic_password_options(value, options(origin)?).map_err(keychain_error)
}

pub fn clear(origin: &str) -> io::Result<()> {
    match delete_generic_password_options(options(origin)?) {
        Ok(()) => Ok(()),
        Err(error) if error.code() == errSecItemNotFound => Ok(()),
        Err(error) => Err(keychain_error(error)),
    }
}
