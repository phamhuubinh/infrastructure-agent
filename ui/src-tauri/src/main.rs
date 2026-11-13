#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

#[cfg(windows)]
use orion_native::{managed, transport, vault};

#[cfg(windows)]
mod app;

#[cfg(windows)]
fn main() {
    app::run();
}

#[cfg(not(windows))]
fn main() {}
