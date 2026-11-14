#![cfg_attr(windows, windows_subsystem = "windows")]

#[cfg(windows)]
use orion_native::{managed, transport, vault};

#[cfg(windows)]
mod app;

#[cfg(windows)]
mod host_settings;

#[cfg(windows)]
fn main() {
    app::run();
}

#[cfg(not(windows))]
fn main() {}
