//! AYON plugin for TVPaint.
//!
//! The plugin runs a JSON-RPC 2.0 websocket server, AYON python process
//! connects to it as a client. See 'README.md' for the protocol.
//!
//! All 'PI_*' functions are called by TVPaint from its main thread.

// Crate name gives the expected "AYONPlugin" library file name.
#![allow(non_snake_case)]

mod encoding;
mod sdk;
mod server;

use std::cell::RefCell;
use std::collections::HashMap;
use std::ffi::{c_char, c_int, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::PathBuf;

use serde_json::{json, Value};

use sdk::{Filter, IntPtr, PIFilter};
use server::{Request, RpcError, Server, INVALID_PARAMS, METHOD_NOT_FOUND};

/// Subfolder of AYON local directory where server files are stored.
const SERVERS_SUBDIR: &str = "tvpaint_servers";
/// Optional identifier of the launch, stored to the server file. It is
/// set when TVPaint is launched by AYON.
const LAUNCH_ID_ENV: &str = "AYON_TVPAINT_LAUNCH_ID";
const MENU_LABEL_ENV: &str = "AYON_MENU_LABEL";

const DEFAULT_MENU_TITLE: &str = "AYON Tools";
const MENU_WIDTH: i32 = 185;
const MENU_ROW_HEIGHT: i32 = 20;
const MENU_HEIGHT_OFFSET: i32 = 5;
const MENU_X_POS: i32 = 9;
const MENU_Y_POS: i32 = 5;

struct MenuItem {
    label: String,
    help: String,
    callback: String,
}

struct Menu {
    title: String,
    items: Vec<MenuItem>,
}

#[derive(Default)]
struct State {
    /// Menu requester, 0 when closed.
    menu_req: IntPtr,
    /// Hidden requester used to receive ticks.
    tick_req: IntPtr,
    menu: Option<Menu>,
    /// Menu was changed and requester must be rebuilt.
    menu_changed: bool,
    /// Callback names of menu buttons by button id.
    buttons: HashMap<i32, String>,
    server: Option<Server>,
    /// Requests are being processed, avoid nested processing when
    /// a george script makes TVPaint send ticks.
    processing: bool,
}

thread_local! {
    static STATE: RefCell<State> = RefCell::new(State::default());
}

/// Run callback with plugin state.
///
/// The state is never borrowed while TVPaint functions are called as
/// TVPaint may call 'PI_Msg' from inside of them.
fn with_state<R>(callback: impl FnOnce(&mut State) -> R) -> R {
    STATE.with(|state| callback(&mut state.borrow_mut()))
}

/// Never let a panic unwind into TVPaint.
fn guard<R>(default: R, callback: impl FnOnce() -> R) -> R {
    match catch_unwind(AssertUnwindSafe(callback)) {
        Ok(result) => result,
        Err(_) => {
            eprintln!("AYON: Plugin panicked");
            default
        }
    }
}

fn plugin_label() -> String {
    match std::env::var(MENU_LABEL_ENV) {
        Ok(label) if !label.is_empty() => label,
        _ => "AYON".into(),
    }
}

fn env_path(key: &str) -> Option<PathBuf> {
    std::env::var_os(key)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

/// Predefined directory where server files are stored.
///
/// Matches the default AYON launcher local directory, but does not depend
/// on environment set by AYON so TVPaint launched outside of AYON uses
/// the same location. Must match 'get_servers_dir' in
/// 'ayon_tvpaint/api/communication_server.py'.
fn servers_dir() -> Option<PathBuf> {
    let local_dir = if cfg!(windows) {
        env_path("LOCALAPPDATA")
            .or_else(|| env_path("USERPROFILE").map(|home| home.join("AppData").join("Local")))?
            .join("Ynput")
            .join("AYON")
    } else if cfg!(target_os = "macos") {
        env_path("HOME")?
            .join("Library")
            .join("Application Support")
            .join("AYON")
    } else {
        env_path("XDG_DATA_HOME")
            .or_else(|| env_path("HOME").map(|home| home.join(".local").join("share")))?
            .join("AYON")
    };
    Some(local_dir.join(SERVERS_SUBDIR))
}

fn start_server(filter: Filter) {
    let Some(servers_dir) = servers_dir() else {
        filter.warning("AYON: Can't determine directory for server file.");
        return;
    };
    let info = json!({
        "pid": std::process::id(),
        "launch_id": std::env::var(LAUNCH_ID_ENV).ok(),
        "plugin_version": env!("CARGO_PKG_VERSION"),
        "started": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_secs())
            .unwrap_or(0),
    });
    match Server::start(&servers_dir, info) {
        Ok(server) => {
            eprintln!("AYON: Websocket server listening on port {}", server.port());
            with_state(|state| state.server = Some(server));
        }
        Err(error) => {
            filter.warning(&format!("AYON: Failed to start server: {error}"));
        }
    }
}

// --- Menu ---

fn parse_menu(params: &Value) -> Result<Menu, String> {
    // Menu is the first positional argument
    let menu = match params {
        Value::Array(values) => values.first().unwrap_or(&Value::Null),
        value => value,
    };
    let Value::Object(menu) = menu else {
        return Err("Menu definition must be an object".into());
    };
    let title = menu
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or(DEFAULT_MENU_TITLE)
        .to_string();
    let mut items = Vec::new();
    let raw_items = menu.get("menu_items").and_then(Value::as_array);
    for item in raw_items.into_iter().flatten() {
        let text = |key: &str| item.get(key).and_then(Value::as_str);
        let (Some(label), Some(callback)) = (text("label"), text("callback")) else {
            return Err("Each menu item must have 'label' and 'callback'".into());
        };
        items.push(MenuItem {
            label: label.into(),
            help: text("help").unwrap_or_default().into(),
            callback: callback.into(),
        });
    }
    Ok(Menu { title, items })
}

/// Recreate menu buttons from current menu definition.
fn rebuild_menu(filter: Filter) {
    struct Button {
        id: i32,
        label: String,
        help: String,
    }

    let plan = with_state(|state| {
        state.menu_changed = false;
        let menu = state.menu.as_ref()?;
        if state.menu_req == 0 {
            return None;
        }
        let old_ids: Vec<i32> = state.buttons.keys().copied().collect();
        state.buttons.clear();
        let mut buttons = Vec::new();
        for (index, item) in menu.items.iter().enumerate() {
            let id = (index as i32 + 1) * 10;
            state.buttons.insert(id, item.callback.clone());
            buttons.push(Button {
                id,
                label: item.label.clone(),
                help: item.help.clone(),
            });
        }
        Some((state.menu_req, menu.title.clone(), old_ids, buttons))
    });
    let Some((req, title, old_ids, buttons)) = plan else {
        return;
    };

    for id in old_ids {
        filter.remove_button(req, id);
    }
    filter.set_req_title(req, &title);

    // Keep requester position, resize it to fit all buttons
    let info = filter.req_info(req);
    let height = MENU_ROW_HEIGHT * buttons.len() as i32 + MENU_HEIGHT_OFFSET;
    filter.resize_req(req, info.x, info.y, MENU_WIDTH, height);

    let flags = unsafe { sdk::AYON_PIRBF_BUTTON_NORMAL | sdk::AYON_PIRBF_BUTTON_ACTION };
    let button_width = MENU_WIDTH - 19;
    let mut y_pos = MENU_Y_POS;
    for button in buttons {
        filter.add_button(req, MENU_X_POS, y_pos, button_width, button.id, flags, &button.label);
        filter.set_button_info_text(req, button.id, &button.help);
        y_pos += MENU_ROW_HEIGHT;
    }
}

fn open_menu(filter: Filter) -> bool {
    let menu_req = with_state(|state| state.menu_req);
    if menu_req != 0 {
        filter.req_to_front(menu_req);
        return true;
    }

    // Requester is empty, buttons are defined with 'define_menu' method
    let req = unsafe {
        filter.open_filter_req(
            MENU_WIDTH,
            MENU_ROW_HEIGHT,
            sdk::AYON_PIRF_STANDARD_REQ | sdk::AYON_PIRF_COLLAPSABLE_REQ,
            sdk::AYON_FILTERREQ_NO_TBAR,
        )
    };
    if req == 0 {
        filter.warning("Can't Open Requester!");
        return false;
    }
    with_state(|state| {
        state.menu_req = req;
        // Buttons belonged to the previous requester
        state.buttons.clear();
    });
    filter.set_req_title(req, DEFAULT_MENU_TITLE);
    rebuild_menu(filter);
    true
}

// --- Requests ---

fn handle_request(filter: Filter, request: &Request) -> Result<Value, RpcError> {
    match request.method.as_str() {
        "execute_george" => execute_george(filter, &request.params),
        "define_menu" => {
            let menu =
                parse_menu(&request.params).map_err(|error| RpcError::new(INVALID_PARAMS, error))?;
            with_state(|state| {
                state.menu = Some(menu);
                state.menu_changed = true;
            });
            rebuild_menu(filter);
            Ok(json!(""))
        }
        method => Err(RpcError::new(
            METHOD_NOT_FOUND,
            format!("Method \"{method}\" not found"),
        )),
    }
}

fn execute_george(filter: Filter, params: &Value) -> Result<Value, RpcError> {
    let script = match params {
        Value::Array(values) => values.first().and_then(Value::as_str),
        Value::Object(values) => values.get("script").and_then(Value::as_str),
        _ => None,
    };
    let Some(script) = script else {
        return Err(RpcError::new(INVALID_PARAMS, "Expected george script string"));
    };
    let script = CString::new(script)
        .map_err(|_| RpcError::new(INVALID_PARAMS, "George script contains NUL byte"))?;
    let (output, success) = filter.send_cmd(&script);
    if !success {
        eprintln!("AYON: George script failed: {}", script.to_string_lossy());
    }
    // Output is returned even on failure, it may contain the error
    Ok(Value::String(encoding::to_utf8(&output)))
}

fn process_requests(filter: Filter) {
    let taken = with_state(|state| {
        if state.processing {
            return None;
        }
        let server = state.server.as_ref()?;
        let requests = server.take_requests();
        if requests.is_empty() {
            return None;
        }
        state.processing = true;
        Some((server.responder(), requests))
    });
    let Some((responder, requests)) = taken else {
        return;
    };

    for request in requests {
        let result = handle_request(filter, &request);
        responder.respond(&request, result);
    }
    with_state(|state| state.processing = false);
}

fn on_button_up(filter: Filter, button_id: i32) {
    let target = with_state(|state| {
        let callback = state.buttons.get(&button_id)?.clone();
        Some((state.server.as_ref()?.responder(), callback))
    });
    if let Some((responder, callback)) = target {
        // Notification, TVPaint must not wait for the client
        responder.notify_all(&callback, json!([]));
    }
    filter.execute();
}

fn on_close(filter: Filter, req: IntPtr, closed_by_shutdown: IntPtr) {
    let is_menu = with_state(|state| {
        if state.menu_req == req {
            state.menu_req = 0;
            state.buttons.clear();
            return true;
        }
        if state.tick_req == req {
            state.tick_req = 0;
        }
        false
    });
    if is_menu {
        // Flag is 1 when requester was closed by TVPaint shutdown,
        //   then the menu is opened on next start.
        filter.write_user_string(&filter.name(), "Open", &closed_by_shutdown.to_string());
    }
}

// --- Plugin functions ---

/// # Safety
/// Called by TVPaint with valid 'PIFilter'.
#[no_mangle]
pub unsafe extern "system" fn PI_About(filter: *mut PIFilter) {
    guard((), || {
        let filter = Filter(filter);
        let (version, revision) = filter.version();
        filter.warning(&format!("{} {version},{revision}", filter.name()));
    })
}

/// Called at TVPaint startup when the plugin is loaded.
///
/// # Safety
/// Called by TVPaint with valid 'PIFilter'.
#[no_mangle]
pub unsafe extern "system" fn PI_Open(filter: *mut PIFilter) -> c_int {
    guard(0, || {
        let filter = Filter(filter);
        let version = env!("CARGO_PKG_VERSION_MAJOR").parse().unwrap_or(0);
        let revision = env!("CARGO_PKG_VERSION_MINOR").parse().unwrap_or(0);
        filter.set_info(&plugin_label(), version, revision);

        // Re-open the menu if it was open when TVPaint was closed, open it
        //   by default when launched by AYON
        let launched_by_ayon = std::env::var_os(LAUNCH_ID_ENV).is_some();
        let default_open = if launched_by_ayon { "1" } else { "0" };
        let open = filter.read_user_string(&filter.name(), "Open", default_open);
        if open.trim().parse::<i32>().unwrap_or(0) != 0 {
            open_menu(filter);
        }

        let req = filter.open_req(150, 80, sdk::AYON_PIRF_HIDDEN_REQ, "AYONticker");
        if req == 0 {
            filter.warning("Can't Open Requester!");
        } else {
            with_state(|state| state.tick_req = req);
            filter.grab_ticks(req);
        }
        start_server(filter);
        1
    })
}

/// Called at TVPaint shutdown.
///
/// # Safety
/// Called by TVPaint with valid 'PIFilter'.
#[no_mangle]
pub unsafe extern "system" fn PI_Close(filter: *mut PIFilter) {
    guard((), || {
        let filter = Filter(filter);
        let (menu_req, tick_req) = with_state(|state| (state.menu_req, state.tick_req));
        if menu_req != 0 {
            filter.close_req(menu_req);
        }
        if tick_req != 0 {
            filter.close_req(tick_req);
        }
        // Dropping the server stops it and removes the server file
        let server = with_state(|state| state.server.take());
        drop(server);
    })
}

/// Called when user opens the plugin from TVPaint.
///
/// # Safety
/// Called by TVPaint with valid 'PIFilter'.
#[no_mangle]
pub unsafe extern "system" fn PI_Parameters(filter: *mut PIFilter, arg: *mut c_char) -> c_int {
    guard(0, || {
        if !arg.is_null() {
            return 1;
        }
        open_menu(Filter(filter)) as c_int
    })
}

/// Requester events.
///
/// # Safety
/// Called by TVPaint with valid 'PIFilter' and arguments array.
#[no_mangle]
pub unsafe extern "system" fn PI_Msg(
    filter: *mut PIFilter,
    event: IntPtr,
    req: IntPtr,
    args: *mut IntPtr,
) -> c_int {
    guard(1, || {
        let filter = Filter(filter);
        // Number of arguments depends on event, read only documented ones
        let arg = |index: usize| -> IntPtr {
            if args.is_null() {
                0
            } else {
                *args.add(index)
            }
        };

        if event == sdk::AYON_PICBREQ_BUTTON_UP {
            on_button_up(filter, arg(0) as i32);
        } else if event == sdk::AYON_PICBREQ_CLOSE {
            on_close(filter, req, arg(4));
        } else if event == sdk::AYON_PICBREQ_OPEN {
            if with_state(|state| state.menu_changed) {
                rebuild_menu(filter);
            }
        } else if event == sdk::AYON_PICBREQ_TICKS {
            if with_state(|state| state.menu_changed) {
                rebuild_menu(filter);
            }
            process_requests(filter);
        }
        1
    })
}

// Plugin is not an image filter, the functions below do nothing.

/// # Safety
/// Called by TVPaint.
#[no_mangle]
pub unsafe extern "system" fn PI_SequenceStart(_filter: *mut PIFilter, _size: c_int) -> c_int {
    1
}

/// # Safety
/// Called by TVPaint.
#[no_mangle]
pub unsafe extern "system" fn PI_SequenceFinish(_filter: *mut PIFilter) {}

/// # Safety
/// Called by TVPaint.
#[no_mangle]
pub unsafe extern "system" fn PI_Start(_filter: *mut PIFilter, _pos: f64, _size: f64) -> c_int {
    1
}

/// # Safety
/// Called by TVPaint.
#[no_mangle]
pub unsafe extern "system" fn PI_Finish(_filter: *mut PIFilter) {}

/// # Safety
/// Called by TVPaint.
#[no_mangle]
pub unsafe extern "system" fn PI_Work(_filter: *mut PIFilter) -> c_int {
    1
}
