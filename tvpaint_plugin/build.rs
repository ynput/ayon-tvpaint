//! Compile the C code talking to TVPaint ('src/host.c') and the shim
//! exposing SDK constants and 'PIFilter' fields to Rust ('src/shim.c').
//!
//! Only headers of the TVPaint SDK are used, its location must be passed
//! with the 'TVPAINT_SDK_DIR' environment variable. Two layouts are
//! supported:
//! - SDK distributed by TVPaint support, with 'include/plugdllx.h'.
//! - Public SDK (https://github.com/TVPaint-Developpement/TVPaintAnimationSDK),
//!   with 'sdk/include/TVPaintAnimationSDK/TVPaintSDK.h'. It supports only
//!   64-bit targets.
//!
//! Host functions of the SDK ('lib/dllx.c', 'pi-private.c') are not
//! compiled, see 'src/host.c'.

use std::env;
use std::path::PathBuf;

fn main() {
    println!("cargo:rerun-if-env-changed=TVPAINT_SDK_DIR");
    println!("cargo:rerun-if-changed=src/shim.c");
    println!("cargo:rerun-if-changed=src/host.c");

    let sdk_dir = match env::var_os("TVPAINT_SDK_DIR") {
        Some(value) => PathBuf::from(value),
        None => panic!(
            "Environment variable 'TVPAINT_SDK_DIR' is not set. \
             Set it to the TVPaint SDK root."
        ),
    };
    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    let pointer_width = env::var("CARGO_CFG_TARGET_POINTER_WIDTH").unwrap_or_default();

    let legacy_include_dir = sdk_dir.join("include");
    let public_include_dir = sdk_dir.join("sdk").join("include");

    let (include_dir, is_public) = if legacy_include_dir.join("plugdllx.h").is_file() {
        (legacy_include_dir, false)
    } else if public_include_dir
        .join("TVPaintAnimationSDK")
        .join("TVPaintSDK.h")
        .is_file()
    {
        (public_include_dir, true)
    } else {
        panic!(
            "'{}' does not look like TVPaint SDK root (missing \
             'include/plugdllx.h' or \
             'sdk/include/TVPaintAnimationSDK/TVPaintSDK.h').",
            sdk_dir.display()
        );
    };
    if is_public && pointer_width != "64" {
        panic!(
            "Public TVPaint SDK supports only 64-bit targets, \
             use the SDK from TVPaint support for 32-bit builds."
        );
    }

    let mut build = cc::Build::new();
    build
        .include(&include_dir)
        .file("src/host.c")
        .file("src/shim.c")
        // The SDK headers are old and noisy, we don't own them.
        .warnings(false);
    if is_public {
        build.define("AYON_PUBLIC_SDK", None);
    }

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
    } else if target_os == "macos" {
        // TVPaint SDK uses 'MACOSX' to choose 'PIPixel' channel order.
        build.define("MACOSX", None);
    }

    build.compile("tvpaint_sdk");
}
