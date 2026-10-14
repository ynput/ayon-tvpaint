//! JSON-RPC 2.0 websocket server running in a background thread.
//!
//! TVPaint SDK functions can be called only from TVPaint's main thread, so
//! the server never handles requests by itself. Requests are queued and
//! the plugin takes them on each tick with 'Server::take_requests', then
//! sends the result back with 'Responder::respond'.
//!
//! Once listening, the server writes a JSON file with its port and the
//! TVPaint process id to the servers directory, so other processes can
//! find out that TVPaint is running and connect to it. The file is
//! removed when the server stops.
//!
//! The server also connects AYON processes with each other. The AYON
//! process controlling TVPaint registers itself as "host client" with
//! 'register_host'. Other processes (e.g. a second launch of TVPaint from
//! AYON) can then call methods of the host client with 'send_to_host',
//! the server forwards the request and routes the response back. These
//! methods don't touch TVPaint and are handled in the server thread.

use std::collections::HashMap;
use std::io;
use std::net::{Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread::JoinHandle;

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio::sync::{mpsc as tokio_mpsc, oneshot};
use tokio_tungstenite::tungstenite::Message;

pub const PARSE_ERROR: i64 = -32700;
pub const INVALID_REQUEST: i64 = -32600;
pub const METHOD_NOT_FOUND: i64 = -32601;
pub const INVALID_PARAMS: i64 = -32602;
/// 'send_to_host' called but no host client is registered.
pub const NO_HOST_CLIENT: i64 = -32001;
/// 'register_host' called but other connection is already registered.
pub const HOST_CLIENT_REGISTERED: i64 = -32002;
/// Host client disconnected before it responded to forwarded request.
pub const HOST_CLIENT_DISCONNECTED: i64 = -32003;

/// Request received from a client which must be handled in main thread.
pub struct Request {
    pub connection_id: u64,
    /// 'None' for notifications which don't expect a response.
    pub id: Option<Value>,
    pub method: String,
    pub params: Value,
}

pub struct RpcError {
    pub code: i64,
    pub message: String,
}

impl RpcError {
    pub fn new(code: i64, message: impl Into<String>) -> Self {
        Self { code, message: message.into() }
    }
}

type Connections = Mutex<HashMap<u64, tokio_mpsc::UnboundedSender<Message>>>;

struct HostClient {
    connection_id: u64,
    /// Data passed to 'register_host', returned by 'get_server_info'.
    info: Value,
}

/// Request forwarded to host client which waits for response.
struct ForwardedRequest {
    connection_id: u64,
    id: Value,
}

struct Shared {
    connections: Connections,
    requests: mpsc::Sender<Request>,
    info: Value,
    host_client: Mutex<Option<HostClient>>,
    /// Requests forwarded to host client by id used in forwarded request.
    forwarded: Mutex<HashMap<u64, ForwardedRequest>>,
    next_forward_id: AtomicU64,
}

/// Cheap handle used to send messages to connected clients.
#[derive(Clone)]
pub struct Responder {
    shared: Arc<Shared>,
}

impl Responder {
    pub fn respond(&self, request: &Request, result: Result<Value, RpcError>) {
        let Some(id) = &request.id else {
            return;
        };
        let message = response_message(id.clone(), result);
        send_to(&self.shared.connections, request.connection_id, message);
    }

    /// Send notification to all connected clients.
    pub fn notify_all(&self, method: &str, params: Value) {
        let message = json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        })
        .to_string();
        let connections = self.shared.connections.lock().unwrap();
        for sender in connections.values() {
            let _ = sender.send(Message::Text(message.clone()));
        }
    }
}

pub struct Server {
    port: u16,
    info_path: PathBuf,
    responder: Responder,
    requests: mpsc::Receiver<Request>,
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
}

impl Server {
    /// Start listening on a free localhost port and write the server file.
    ///
    /// 'info' is stored in the server file and returned by
    /// 'get_server_info' method; 'port', 'host' and 'url' are added.
    pub fn start(servers_dir: &Path, mut info: Value) -> io::Result<Server> {
        // Bind in the calling thread to know the port and fail early
        let listener = std::net::TcpListener::bind(SocketAddr::from((Ipv4Addr::LOCALHOST, 0)))?;
        listener.set_nonblocking(true)?;
        let port = listener.local_addr()?.port();

        if let Value::Object(map) = &mut info {
            map.insert("host".into(), json!("127.0.0.1"));
            map.insert("port".into(), json!(port));
            map.insert("url".into(), json!(format!("ws://127.0.0.1:{port}")));
        }

        let (requests_sender, requests) = mpsc::channel();
        let shared = Arc::new(Shared {
            connections: Mutex::new(HashMap::new()),
            requests: requests_sender,
            info: info.clone(),
            host_client: Mutex::new(None),
            forwarded: Mutex::new(HashMap::new()),
            next_forward_id: AtomicU64::new(1),
        });

        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_io()
            .build()?;
        let (shutdown_sender, shutdown_receiver) = oneshot::channel();
        let thread_shared = shared.clone();
        let thread = std::thread::Builder::new()
            .name("ayon-websocket-server".into())
            .spawn(move || {
                runtime.block_on(accept_loop(listener, thread_shared, shutdown_receiver));
                // Dropping the runtime cancels all connection tasks
            })?;

        let mut server = Server {
            port,
            info_path: server_file_path(servers_dir),
            responder: Responder { shared },
            requests,
            shutdown: Some(shutdown_sender),
            thread: Some(thread),
        };
        // Stop the server if the file can't be written, nobody would find it
        if let Err(error) = write_server_file(&server.info_path, &info) {
            server.stop();
            return Err(error);
        }
        Ok(server)
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn responder(&self) -> Responder {
        self.responder.clone()
    }

    /// Take all requests waiting for main thread.
    pub fn take_requests(&self) -> Vec<Request> {
        self.requests.try_iter().collect()
    }

    pub fn stop(&mut self) {
        let _ = std::fs::remove_file(&self.info_path);
        if let Some(shutdown) = self.shutdown.take() {
            let _ = shutdown.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        self.stop();
    }
}

fn server_file_path(servers_dir: &Path) -> PathBuf {
    servers_dir.join(format!("tvpaint_{}.json", std::process::id()))
}

fn write_server_file(path: &Path, info: &Value) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    // Write to temp file and rename, readers never see partial content
    let tmp_path = path.with_extension("json.tmp");
    std::fs::write(&tmp_path, serde_json::to_vec_pretty(info)?)?;
    std::fs::rename(&tmp_path, path)
}

async fn accept_loop(
    listener: std::net::TcpListener,
    shared: Arc<Shared>,
    mut shutdown: oneshot::Receiver<()>,
) {
    let listener = match tokio::net::TcpListener::from_std(listener) {
        Ok(listener) => listener,
        Err(error) => {
            eprintln!("AYON: Failed to start websocket server: {error}");
            return;
        }
    };
    let mut next_connection_id: u64 = 0;
    loop {
        tokio::select! {
            _ = &mut shutdown => break,
            accepted = listener.accept() => match accepted {
                Ok((stream, _)) => {
                    next_connection_id += 1;
                    tokio::spawn(handle_connection(
                        stream, next_connection_id, shared.clone()
                    ));
                }
                Err(error) => eprintln!("AYON: Failed to accept connection: {error}"),
            },
        }
    }
}

async fn handle_connection(stream: tokio::net::TcpStream, connection_id: u64, shared: Arc<Shared>) {
    let websocket = match tokio_tungstenite::accept_async(stream).await {
        Ok(websocket) => websocket,
        Err(error) => {
            eprintln!("AYON: Websocket handshake failed: {error}");
            return;
        }
    };
    let (mut sink, mut stream) = websocket.split();
    let (sender, mut receiver) = tokio_mpsc::unbounded_channel();
    shared
        .connections
        .lock()
        .unwrap()
        .insert(connection_id, sender.clone());

    let writer = async {
        while let Some(message) = receiver.recv().await {
            if sink.send(message).await.is_err() {
                break;
            }
        }
    };
    let reader = async {
        while let Some(message) = stream.next().await {
            match message {
                Ok(Message::Text(text)) => {
                    if let Some(response) = handle_text(&text, connection_id, &shared) {
                        let _ = sender.send(Message::Text(response));
                    }
                }
                Ok(Message::Close(_)) | Err(_) => break,
                Ok(_) => {}
            }
        }
    };
    tokio::select! {
        _ = writer => {}
        _ = reader => {}
    }

    shared.connections.lock().unwrap().remove(&connection_id);
    on_disconnect(connection_id, &shared);
}

fn on_disconnect(connection_id: u64, shared: &Shared) {
    let mut host_client = shared.host_client.lock().unwrap();
    if host_client.as_ref().map(|host| host.connection_id) != Some(connection_id) {
        return;
    }
    *host_client = None;
    drop(host_client);

    // Nobody will respond to requests forwarded to the host client
    let forwarded: Vec<ForwardedRequest> = shared
        .forwarded
        .lock()
        .unwrap()
        .drain()
        .map(|(_, request)| request)
        .collect();
    for request in forwarded {
        let message = response_message(
            request.id,
            Err(RpcError::new(
                HOST_CLIENT_DISCONNECTED,
                "Host client disconnected before it responded",
            )),
        );
        send_to(&shared.connections, request.connection_id, message);
    }
}

/// Handle received text message, returns message to send back, if any.
fn handle_text(text: &str, connection_id: u64, shared: &Shared) -> Option<String> {
    let message: Value = match serde_json::from_str(text) {
        Ok(message) => message,
        Err(error) => {
            return Some(response_message(
                Value::Null,
                Err(RpcError::new(PARSE_ERROR, error.to_string())),
            ))
        }
    };
    let Value::Object(mut message) = message else {
        return Some(response_message(
            Value::Null,
            Err(RpcError::new(INVALID_REQUEST, "Expected a JSON object (batches are not supported)")),
        ));
    };
    let id = message.remove("id");
    let method = match message.remove("method") {
        Some(Value::String(method)) => method,
        // Response, the server sends requests only when forwarding them
        None => {
            route_host_response(connection_id, id, message, shared);
            return None;
        }
        Some(_) => {
            return Some(response_message(
                id.unwrap_or(Value::Null),
                Err(RpcError::new(INVALID_REQUEST, "'method' must be a string")),
            ))
        }
    };
    let params = message.remove("params").unwrap_or_else(|| json!([]));

    // Methods below don't touch TVPaint, they are handled in this thread
    //   and work even if TVPaint's main thread is busy.
    let result = match method.as_str() {
        "get_server_info" => Ok(server_info(shared)),
        "register_host" => register_host(connection_id, params, shared),
        "send_to_host" => match send_to_host(connection_id, id.clone(), params, shared) {
            // Host client responds later
            Ok(()) => return None,
            Err(error) => Err(error),
        },
        _ => {
            let request = Request { connection_id, id, method, params };
            let _ = shared.requests.send(request);
            return None;
        }
    };
    id.map(|id| response_message(id, result))
}

fn server_info(shared: &Shared) -> Value {
    let mut info = shared.info.clone();
    let host_client = shared.host_client.lock().unwrap();
    if let Value::Object(map) = &mut info {
        map.insert(
            "host_client".into(),
            host_client
                .as_ref()
                .map(|host| host.info.clone())
                .unwrap_or(Value::Null),
        );
    }
    info
}

fn register_host(connection_id: u64, params: Value, shared: &Shared) -> Result<Value, RpcError> {
    // Data are passed as first positional argument or as named arguments
    let info = match params {
        Value::Array(mut values) if !values.is_empty() => values.swap_remove(0),
        Value::Object(map) => Value::Object(map),
        _ => json!({}),
    };
    if !info.is_object() {
        return Err(RpcError::new(INVALID_PARAMS, "Expected host client data object"));
    }
    let mut host_client = shared.host_client.lock().unwrap();
    if let Some(host) = host_client.as_ref() {
        if host.connection_id != connection_id {
            return Err(RpcError::new(
                HOST_CLIENT_REGISTERED,
                "Other host client is already registered",
            ));
        }
    }
    *host_client = Some(HostClient { connection_id, info });
    Ok(Value::Null)
}

/// Forward request to the host client.
///
/// Params are '{"method": str, "params": Any}'. The host client gets
/// a request with a new id, its response is routed back to the caller.
fn send_to_host(
    connection_id: u64,
    id: Option<Value>,
    params: Value,
    shared: &Shared,
) -> Result<(), RpcError> {
    let Value::Object(mut params) = params else {
        return Err(RpcError::new(
            INVALID_PARAMS,
            "Expected object with 'method' and 'params'",
        ));
    };
    let Some(Value::String(method)) = params.remove("method") else {
        return Err(RpcError::new(INVALID_PARAMS, "Missing 'method' string"));
    };
    let method_params = params.remove("params").unwrap_or_else(|| json!([]));

    let host_connection_id = match shared.host_client.lock().unwrap().as_ref() {
        Some(host) => host.connection_id,
        None => {
            return Err(RpcError::new(NO_HOST_CLIENT, "No host client is registered"))
        }
    };

    let mut message = json!({
        "jsonrpc": "2.0",
        "method": method,
        "params": method_params,
    });
    // Notification is forwarded as notification, nothing to wait for
    if let Some(id) = id {
        let forward_id = shared.next_forward_id.fetch_add(1, Ordering::Relaxed);
        shared
            .forwarded
            .lock()
            .unwrap()
            .insert(forward_id, ForwardedRequest { connection_id, id });
        message["id"] = json!(forward_id);
    }
    send_to(&shared.connections, host_connection_id, message.to_string());
    Ok(())
}

/// Route response of the host client to the client which sent request.
fn route_host_response(
    connection_id: u64,
    id: Option<Value>,
    mut message: serde_json::Map<String, Value>,
    shared: &Shared,
) {
    let is_host = shared
        .host_client
        .lock()
        .unwrap()
        .as_ref()
        .is_some_and(|host| host.connection_id == connection_id);
    let Some(forward_id) = id.as_ref().and_then(Value::as_u64) else {
        return;
    };
    if !is_host {
        return;
    }
    let Some(request) = shared.forwarded.lock().unwrap().remove(&forward_id) else {
        return;
    };
    message.insert("jsonrpc".into(), json!("2.0"));
    message.insert("id".into(), request.id);
    send_to(
        &shared.connections,
        request.connection_id,
        Value::Object(message).to_string(),
    );
}

fn response_message(id: Value, result: Result<Value, RpcError>) -> String {
    match result {
        Ok(result) => json!({"jsonrpc": "2.0", "id": id, "result": result}),
        Err(error) => json!({
            "jsonrpc": "2.0",
            "id": id,
            "error": {"code": error.code, "message": error.message},
        }),
    }
    .to_string()
}

fn send_to(connections: &Connections, connection_id: u64, message: String) {
    if let Some(sender) = connections.lock().unwrap().get(&connection_id) {
        let _ = sender.send(Message::Text(message));
    }
}
