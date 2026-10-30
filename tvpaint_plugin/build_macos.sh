#!/bin/sh
# Build universal (arm64 + x86_64) TVPaint plugin bundle and copy it
#   into the addon. Requires 'TVPAINT_SDK_DIR' (see README.md).
set -eu

cd "$(dirname "$0")"
rustup target add aarch64-apple-darwin x86_64-apple-darwin
cargo build --release --target aarch64-apple-darwin
cargo build --release --target x86_64-apple-darwin

bundle=../client/ayon_tvpaint/tvpaint_plugin/macos/plugin/AYONPlugin.bundle
rm -rf "$bundle"
mkdir -p "$bundle/Contents/MacOS"
lipo -create \
    target/aarch64-apple-darwin/release/libAYONPlugin.dylib \
    target/x86_64-apple-darwin/release/libAYONPlugin.dylib \
    -output "$bundle/Contents/MacOS/AYONPlugin"
