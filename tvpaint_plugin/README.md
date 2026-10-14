AYON TVPaint plugin
===================

TVPaint plugin which lets the AYON python process control TVPaint. It is written in Rust and uses the TVPaint SDK.

The plugin runs a websocket server speaking JSON-RPC 2.0. The AYON python process connects to it as a client, executes george scripts and defines the plugin menu. When a menu button is clicked, the plugin sends a notification to all connected clients.

## Server discovery

The server always starts when TVPaint loads the plugin. It listens on a free port on `127.0.0.1` and writes `tvpaint_<pid>.json` into a predefined per-user directory:

| Platform | Directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Ynput\AYON\tvpaint_servers` |
| macOS | `~/Library/Application Support/AYON/tvpaint_servers` |
| Linux | `$XDG_DATA_HOME/AYON/tvpaint_servers` (default `~/.local/share/AYON/tvpaint_servers`) |

It is the default AYON launcher local directory, but it doesn't depend on any AYON environment variable, so a TVPaint started outside of AYON writes to the same place. The python side computes it with `get_servers_dir()` in `ayon_tvpaint.api.communication_server`; keep the two in sync.

File content:

```json
{
  "pid": 12345,
  "port": 50123,
  "host": "127.0.0.1",
  "url": "ws://127.0.0.1:50123",
  "launch_id": "4f0c...",
  "plugin_version": "2.0.0",
  "started": 1760000000
}
```

- `launch_id` is the value of the `AYON_TVPAINT_LAUNCH_ID` environment variable, or `null` if it isn't set. The launcher sets it to find the server of the process it started. When it is set, the plugin menu also opens on startup by default.
- The file is removed when TVPaint closes. If TVPaint crashes the file stays, so readers should check that `pid` is still running. `get_running_servers` in `ayon_tvpaint.api.communication_server` does this and removes stale files.

## Methods

Methods handled by the plugin:

| Method | Params | Result |
| --- | --- | --- |
| `execute_george` | `[script]` | Output of the george script (UTF-8). |
| `define_menu` | `[{"title": str, "menu_items": [{"label", "help", "callback"}]}]` | `""` |
| `get_server_info` | none | Content of the server file plus `host_client` (data of the registered host client, or `null`). |
| `register_host` | `[{...}]` | `null`. Registers the connection as host client. Fails with `-32002` if another connection is registered. |
| `send_to_host` | `{"method": str, "params": ...}` | Response of the host client. Fails with `-32001` if no host client is registered, or `-32003` if it disconnects before responding. |

When a menu button is clicked, the plugin sends a notification named after the button's `callback`, with empty `params`. The plugin does not wait for a response, so TVPaint never blocks on the client.

`execute_george` and `define_menu` are queued and handled on TVPaint's main thread (on requester ticks), because SDK functions can't be called from other threads. The other methods don't touch TVPaint. They are handled in the server thread and work even while TVPaint is busy.

## Host client and reuse of running TVPaint

The AYON process that controls TVPaint (tools, menu, publishing) registers itself with `register_host`, passing `{"addon_version", "project_name", "pid"}`. Only one host client can be registered. The registration is removed when its connection closes.

When TVPaint is launched from AYON again, the new launch process (`launch_script.py`) looks for a running TVPaint whose host client has the same addon version and project. If it finds one, it calls `send_to_host` with method `open_workfile` and params `{"workfile_path", "project_name", "folder_path", "task_name"}`, then exits. The host client opens the workfile with `open_workfile_with_context`, which switches the context and stores it in the workfile metadata. If there is no workfile in the launch arguments, no matching TVPaint, or the host client returns an error, a new TVPaint is launched.

## Build

Requirements:
- Rust 1.83+ (https://rustup.rs)
- C compiler (MSVC Build Tools on Windows, Xcode command line tools on macOS)
- TVPaint SDK, which you can request from TVPaint support. It is not redistributable.

Set `TVPAINT_SDK_DIR` to the SDK root (the folder containing `include/` and `lib/dllx.c`) and build:

```shell
cargo build --release
```

On Windows, build both architectures and copy the libraries into the addon:

```shell
rustup target add i686-pc-windows-msvc
cargo build --release --target x86_64-pc-windows-msvc
cargo build --release --target i686-pc-windows-msvc
```

- `target/x86_64-pc-windows-msvc/release/AYONPlugin.dll` -> `client/ayon_tvpaint/tvpaint_plugin/windows_x64/plugin/AYONPlugin.dll`
- `target/i686-pc-windows-msvc/release/AYONPlugin.dll` -> `client/ayon_tvpaint/tvpaint_plugin/windows_x86/plugin/AYONPlugin.dll`

The C runtime is linked statically (see `.cargo/config.toml`), so the DLL only needs system libraries.

## Layout

- `src/lib.rs`: `PI_*` entry points called by TVPaint, menu, and request handling.
- `src/server.rs`: websocket server thread and server file.
- `src/sdk.rs`: bindings to the SDK host functions.
- `src/shim.c`: exposes SDK constants and `PIFilter` fields so they aren't duplicated in Rust.
- `build.rs`: compiles `dllx.c` from the SDK together with `shim.c`.
