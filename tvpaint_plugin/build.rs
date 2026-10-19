//! Compile the TVPaint SDK host functions ('dllx.c') and the small C shim
//! exposing SDK constants and 'PIFilter' fields to Rust.
//!
//! The SDK is not redistributable, so its location must be passed with
//! the 'TVPAINT_SDK_DIR' environment variable. The directory must contain
//! 'include/plugdllx.h' and 'lib/dllx.c'.

use std::env;
use std::path::PathBuf;

fn main() {
    println!("cargo:rerun-if-env-changed=TVPAINT_SDK_DIR");
    println!("cargo:rerun-if-changed=src/shim.c");

    let sdk_dir = match env::var_os("TVPAINT_SDK_DIR") {
        Some(value) => PathBuf::from(value),
        None => panic!(
            "Environment variable 'TVPAINT_SDK_DIR' is not set. \
             Set it to the TVPaint SDK root (folder with 'include' and 'lib')."
        ),
    };
    let include_dir = sdk_dir.join("include");
    let dllx_path = sdk_dir.join("lib").join("dllx.c");
    if !include_dir.join("plugdllx.h").is_file() || !dllx_path.is_file() {
        panic!(
            "'{}' does not look like TVPaint SDK root \
             (missing 'include/plugdllx.h' or 'lib/dllx.c').",
            sdk_dir.display()
        );
    }
    println!("cargo:rerun-if-changed={}", dllx_path.display());

    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    let pointer_width =
        env::var("CARGO_CFG_TARGET_POINTER_WIDTH").unwrap_or_default();

    let mut build = cc::Build::new();
    build
        .include(&include_dir)
        .file(&dllx_path)
        .file("src/shim.c")
        // The SDK sources are old and noisy, we don't own them.
        .warnings(false);

    if target_os == "windows" {
        // TVPaint SDK uses 'WIN64'/'WIN32' to choose 'INTPTR' type.
        if pointer_width == "64" {
            build.define("WIN64", None);
        } else {
            build.define("WIN32", None);
        }
        build.define("_CRT_SECURE_NO_WARNINGS", None);
    } else if target_os == "linux" {
        // TVPaint SDK uses 'LINUX' to choose 'PIPixel' channel order.
        build.define("LINUX", None);
    }

    build.compile("tvpaint_sdk");
}
