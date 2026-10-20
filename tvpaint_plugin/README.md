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
| `execute_george` | `[command]` | Output of the single-line george command. |
| `execute_george_batch` | `[[command, ...]]` | Output of each command. All commands run in one tick, nothing runs if any command is invalid. |
| `get_layer_ids` | none | Ids of all layers in the current clip (`tv_LayerGetID` until `none`). |
| `get_group_count` | none | Number of color groups without the default group 0 (26 in TVPaint 11.7, more in newer versions). |
| `define_menu` | `[{"title": str, "menu_items": [{"label", "help", "callback"}]}]` | `""` |
| `get_server_info` | none | Content of the server file plus `host_client` (data of the registered host client, or `null`). |
| `register_host` | `[{...}]` | `null`. Registers the connection as host client. Fails with `-32002` if another connection is registered. |
| `send_to_host` | `{"method": str, "params": ...}` | Response of the host client. Fails with `-32001` if no host client is registered, or `-32003` if it disconnects before responding. |

When a menu button is clicked, the plugin sends a notification named after the button's `callback`, with empty `params`. The plugin does not wait for a response, so TVPaint never blocks on the client.

`execute_george`, `execute_george_batch`, `get_layer_ids`, `get_group_count` and `define_menu` are queued and handled on TVPaint's main thread (on requester ticks), because SDK functions can't be called from other threads. The other methods don't touch TVPaint. They are handled in the server thread and work even while TVPaint is busy.

## George commands

TVPaint executes only the first line of a command sent by a plugin, and george variables, `PARSE` or control flow don't work. So the plugin refuses multiline commands, and loops or parsing are done by the caller. Use `execute_george_batch` to run many commands at once.

Commands are converted to the system ANSI code page, which TVPaint uses on Windows. Commands with characters outside the code page are refused, because TVPaint would get a different path or text.

Each command parses its arguments differently (tested with TVPaint 11.7):
- `tv_SaveProject`, `tv_SaveImage` and `tv_LayerCreate` take the rest of the line as the value, so it must not be quoted.
- Other strings (`tv_LoadProject`, `tv_LoadSequence`, `tv_SoundClipNew`, `tv_LayerRename`, `tv_WriteProjectString`, ...) must be in double quotes.
- Keywords (`tv_LayerColor get`, `tv_Background color`) must not be quoted. Quoted keywords fail or are silently ignored.
- Double quotes can't be passed inside a string.
- Missing files or folders make TVPaint show a modal dialog, which blocks it and the request. Check paths before sending the command.

## Host client and reuse of running TVPaint

The AYON process that controls TVPaint (tools, menu, publishing) registers itself with `register_host`, passing `{"bundle_name", "studio_bundle_name", "variant", "addon_version", "pid"}`. Only one host client can be registered. The registration is removed when its connection closes.

TVPaint is a single-instance application: running its executable again only passes the arguments to the running TVPaint and exits. So `launch_script.py` never launches TVPaint while one is running. It looks for a server whose `executable` matches the TVPaint being launched, then:

| Running TVPaint | Launch does |
| --- | --- |
| none | Launch TVPaint. |
| no host client (e.g. started without AYON) | Attach to it and become the host client, open the workfile from the launch arguments. |
| host client with the same bundle, studio bundle and variant | Call `send_to_host` with method `open_workfile` and params `{"workfile_path", "project_name", "folder_path", "task_name"}`, then exit. |
| host client with a different bundle or variant | Show a warning. Ignore does the same as above, using the running bundle's addons. Cancel ends the launch. |

The project doesn't have to match. TVPaint's current context, project included, is stored in the workfile metadata. The host client opens the workfile with `TVPaintHost.open_workfile_in_context`, which stores the new context in the opened workfile's metadata. It mirrors ayon-core's `open_workfile_with_context`, with the same hooks and events, but takes the project as an argument.

## Build

Requirements:
- Rust 1.83+ (https://rustup.rs)
- C compiler (MSVC Build Tools on Windows, Xcode command line tools on macOS, gcc on Linux)
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

On Linux, the library links to the glibc of the build machine and doesn't run on systems with older glibc. Build it in a Rocky Linux 8 container (glibc 2.28), so it runs on Rocky 8+ and Ubuntu 20.04+:

```shell
docker run --rm -v "$PWD":/src -v "$TVPAINT_SDK_DIR":/sdk:ro -e TVPAINT_SDK_DIR=/sdk -e CARGO_TARGET_DIR=/src/target/rocky8 -w /src rockylinux:8 bash -c "dnf install -y gcc && curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal && /root/.cargo/bin/cargo build --release"
```

- `target/rocky8/release/libAYONPlugin.so` -> `client/ayon_tvpaint/tvpaint_plugin/linux_x64/plugin/AYONPlugin.so`

On Linux, TVPaint loads plugins from `plugins` in its installation folder (e.g. `/usr/share/tvpaint-developpement/tvp-animation-11.7.6-pro/plugins`, owned by root) and from `plugins` in the active user profile (e.g. `~/.tvp/tvp animation 11 pro/default/plugins`, the profile is set in `system.ini` next to it). Tested with TVPaint 11.7.6, other folders like `/usr/share/tvpaint-animation` are not used. A plugin in both folders is loaded twice. The launch copies the plugin when it's missing or different:

- To the user profile, which doesn't need admin permissions.
- To the installation folder if the plugin is already there (e.g. installed by an administrator), and removes it from the user profile.
- To the installation folder before TVPaint created the user profile on its first start. TVPaint crashes on start if the profile folder exists before that, so it is not created by the launch.

If the copy to the installation folder fails, the launch fails with the `sudo cp` command to run.

## Layout

- `src/lib.rs`: `PI_*` entry points called by TVPaint, menu, and request handling.
- `src/server.rs`: websocket server thread and server file.
- `src/sdk.rs`: bindings to the SDK host functions.
- `src/shim.c`: exposes SDK constants and `PIFilter` fields so they aren't duplicated in Rust.
- `build.rs`: compiles `dllx.c` from the SDK together with `shim.c`.
