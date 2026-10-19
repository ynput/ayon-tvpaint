import os
import json
import time
import uuid
import inspect
import itertools
import subprocess
import collections
import asyncio
import ctypes
import logging
import platform
import filecmp
import tempfile
import threading
import shutil
import shlex
import concurrent.futures

import aiohttp

from ayon_core.lib import emit_event
from ayon_tvpaint.tvpaint_plugin import get_plugin_files_path
from ayon_tvpaint.version import __version__ as ADDON_VERSION

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# Environment variable read by TVPaint plugin, stored to its server file
#   to be able to find server of launched process.
LAUNCH_ID_ENV_KEY = "AYON_TVPAINT_LAUNCH_ID"


class CommunicationWrapper:
    # TODO add logs and exceptions
    communicator = None

    log = logging.getLogger("CommunicationWrapper")

    @classmethod
    def create_qt_communicator(cls, *args, **kwargs):
        """Create communicator for Artist usage."""
        communicator = QtCommunicator(*args, **kwargs)
        cls.set_communicator(communicator)
        return communicator

    @classmethod
    def set_communicator(cls, communicator):
        if not cls.communicator:
            cls.communicator = communicator
        else:
            cls.log.warning("Communicator was set multiple times.")

    @classmethod
    def client(cls):
        if not cls.communicator:
            return None
        return cls.communicator.client()

    @classmethod
    def execute_george(cls, george_script):
        """Execute passed goerge script in TVPaint."""
        if not cls.communicator:
            return
        return cls.communicator.execute_george(george_script)


def get_servers_dir():
    """Directory where TVPaint plugin stores information about its server.

    Each running TVPaint with AYON plugin has a 'tvpaint_<pid>.json' file
    in the directory. The file is removed when TVPaint is closed.

    The location is predefined and must match 'servers_dir' in the plugin
    ('tvpaint_plugin/src/lib.rs'). It is the default AYON launcher local
    directory, but it does not use 'AYON_LAUNCHER_LOCAL_DIR' because
    TVPaint launched outside of AYON does not have it set.

    Returns:
        str: Path to directory.

    """
    platform_name = platform.system().lower()
    if platform_name == "windows":
        local_dir = os.path.join(
            os.environ.get("LOCALAPPDATA")
            or os.path.join(os.path.expanduser("~"), "AppData", "Local"),
            "Ynput",
            "AYON",
        )
    elif platform_name == "darwin":
        local_dir = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", "AYON"
        )
    else:
        local_dir = os.path.join(
            os.environ.get("XDG_DATA_HOME")
            or os.path.join(os.path.expanduser("~"), ".local", "share"),
            "AYON",
        )
    return os.path.join(local_dir, "tvpaint_servers")


def _is_process_running(pid):
    if platform.system().lower() != "windows":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    process_query_limited_information = 0x1000
    still_active = 259
    error_access_denied = 5
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(
        process_query_limited_information, False, pid
    )
    if not handle:
        return ctypes.get_last_error() == error_access_denied
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class TVPaintServerInfo:
    """Information about websocket server running in TVPaint plugin.

    Args:
        filepath (str): Path to server file.
        data (dict[str, Any]): Content of the server file.

    """
    def __init__(self, filepath, data):
        self.filepath = filepath
        self.data = data

    @property
    def pid(self):
        return self.data["pid"]

    @property
    def port(self):
        return self.data["port"]

    @property
    def url(self):
        return self.data["url"]

    @property
    def launch_id(self):
        return self.data.get("launch_id")

    @property
    def plugin_version(self):
        return self.data.get("plugin_version")

    @property
    def executable(self):
        return self.data.get("executable")

    def is_executable(self, executable):
        """Server runs in TVPaint launched with the executable."""
        if not self.executable:
            return True
        return _normalize_path(self.executable) == _normalize_path(executable)

    def __repr__(self):
        return f"<TVPaintServerInfo pid={self.pid} url={self.url}>"


def _normalize_path(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


class _RunningProcess:
    """Process which was not started by this process.

    Mimics 'poll' of 'subprocess.Popen' used to check if TVPaint is running.
    """
    def __init__(self, pid):
        self.pid = pid
        self.returncode = None

    def poll(self):
        if self.returncode is None and not _is_process_running(self.pid):
            self.returncode = 0
        return self.returncode


def get_running_servers():
    """Get servers of running TVPaint processes.

    Server files of processes that are not running anymore (e.g. TVPaint
    crashed) are removed.

    Returns:
        list[TVPaintServerInfo]: Servers of running TVPaint processes.

    """
    servers_dir = get_servers_dir()
    if not os.path.isdir(servers_dir):
        return []

    output = []
    for filename in os.listdir(servers_dir):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(servers_dir, filename)
        try:
            with open(filepath, "r") as stream:
                server_info = TVPaintServerInfo(filepath, json.load(stream))
            pid = int(server_info.pid)
            server_info.url
        except (OSError, ValueError, KeyError, TypeError):
            log.debug(f"Skipping invalid server file '{filepath}'.")
            continue

        if _is_process_running(pid):
            output.append(server_info)
            continue

        log.debug(f"Removing server file of dead process '{filepath}'.")
        try:
            os.remove(filepath)
        except OSError:
            pass
    return output


def find_server(launch_id=None, pid=None):
    """Find server of running TVPaint process.

    Args:
        launch_id (Optional[str]): Launch id passed to TVPaint process
            with 'AYON_TVPAINT_LAUNCH_ID' environment variable.
        pid (Optional[int]): TVPaint process id.

    Returns:
        Optional[TVPaintServerInfo]: Server info or None if not found.

    """
    for server_info in get_running_servers():
        if launch_id is not None and server_info.launch_id != launch_id:
            continue
        if pid is not None and server_info.pid != pid:
            continue
        return server_info
    return None


class TVPaintRpcError(Exception):
    """Error response received from TVPaint plugin."""
    def __init__(self, error):
        self.code = error.get("code")
        self.message = error.get("message")
        super().__init__(f"TVPaint error {self.code}: {self.message}")


class TVPaintRpcClient:
    """JSON-RPC 2.0 client connected to websocket server in TVPaint.

    The client runs its own asyncio loop in a thread. Public methods are
    blocking and can be called from any thread except the loop thread.

    Methods called by TVPaint (e.g. on menu button click) are registered
    with 'add_method'. Callbacks are executed in the loop thread so they
    must not block, nor call blocking methods of the client.
    """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._session = None
        self._ws = None
        self._request_ids = itertools.count(1)
        self._pending_requests = {}
        self._methods = {}
        # Running method calls, cancelled on close
        self._method_tasks = set()
        self._thread = threading.Thread(
            target=self._run_loop, name="TVPaintRpcClient", daemon=True
        )
        self._thread.start()

    @property
    def is_connected(self):
        return self._ws is not None and not self._ws.closed

    def add_method(self, name, callback):
        """Register method which can be called by TVPaint."""
        self._methods[name] = callback

    def connect(self, url, timeout=10):
        self._run(self._connect(url), timeout)

    def close(self):
        if not self._thread.is_alive():
            return
        try:
            self._run(self._close(), 5)
        except Exception:
            log.debug("Failed to close connection to TVPaint", exc_info=True)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(5)

    def send_request(self, method, params=None, timeout=None):
        """Call method in TVPaint and wait for result.

        Raises:
            TVPaintRpcError: TVPaint responded with error.
            ConnectionError: Not connected or connection was closed.
            TimeoutError: Response did not arrive in time.

        """
        response = self._run(self._send_request(method, params), timeout)
        error = response.get("error")
        if error:
            raise TVPaintRpcError(error)
        return response.get("result")

    def send_notification(self, method, params=None):
        """Call method in TVPaint without waiting for result."""
        self._run(self._send({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
        }))

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run(self, coroutine, timeout=None):
        if threading.current_thread() is self._thread:
            coroutine.close()
            raise RuntimeError(
                "Can't wait for TVPaint response in the client loop thread."
            )
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError("TVPaint did not respond in time.")

    async def _connect(self, url):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(url, max_msg_size=0)
        self.loop.create_task(self._read_loop(self._ws))

    async def _close(self):
        for task in tuple(self._method_tasks):
            task.cancel()
        if self._method_tasks:
            await asyncio.gather(*self._method_tasks, return_exceptions=True)
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()

    async def _read_loop(self, ws):
        try:
            async for message in ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    await self._process_message(message.data)
        finally:
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(
                        ConnectionError("Connection to TVPaint was closed.")
                    )
            self._pending_requests.clear()
            log.info("Connection to TVPaint closed")

    async def _send(self, data):
        if not self.is_connected:
            raise ConnectionError("Not connected to TVPaint.")
        await self._ws.send_str(json.dumps(data))

    async def _send_request(self, method, params):
        request_id = next(self._request_ids)
        future = self.loop.create_future()
        self._pending_requests[request_id] = future
        try:
            await self._send({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or [],
            })
            return await future
        finally:
            self._pending_requests.pop(request_id, None)

    async def _process_message(self, raw_message):
        try:
            message = json.loads(raw_message)
        except ValueError:
            log.warning(f"Received invalid message: {raw_message}")
            return

        if not isinstance(message, dict):
            return

        message_id = message.get("id")
        method = message.get("method")
        if method is None:
            future = self._pending_requests.get(message_id)
            if future is not None and not future.done():
                future.set_result(message)
            return

        # Handle in a task, so the read loop can receive responses while
        #   the callback waits e.g. for george scripts executed by it.
        task = self.loop.create_task(
            self._handle_method_call(message_id, method, message.get("params"))
        )
        self._method_tasks.add(task)
        task.add_done_callback(self._method_tasks.discard)

    async def _handle_method_call(self, message_id, method, params):
        response = await self._call_method(method, params)
        if message_id is None:
            return
        response["jsonrpc"] = "2.0"
        response["id"] = message_id
        try:
            await self._send(response)
        except ConnectionError:
            log.warning(f"Could not send response of '{method}' to TVPaint")

    async def _call_method(self, method, params):
        callback = self._methods.get(method)
        if callback is None:
            log.warning(f"TVPaint called unknown method '{method}'")
            return {"error": {
                "code": -32601,
                "message": f"Method \"{method}\" not found",
            }}

        try:
            if isinstance(params, dict):
                result = callback(**params)
            else:
                result = callback(*(params or []))
            if inspect.isawaitable(result):
                result = await result
            return {"result": result}

        except Exception as exc:
            log.warning(
                f"Method '{method}' called by TVPaint failed", exc_info=True
            )
            return {"error": {"code": -32000, "message": str(exc)}}


def get_host_client_info():
    """Data of this process registered in TVPaint as its host client.

    Other AYON processes use them to decide if TVPaint can be reused. Same
    bundle and variant means same addons, so the host client can open
    workfile of any project.

    Returns:
        dict[str, Any]: Host client data.

    """
    from ayon_core.lib import get_settings_variant

    return {
        "bundle_name": os.getenv("AYON_BUNDLE_NAME"),
        "studio_bundle_name": os.getenv("AYON_STUDIO_BUNDLE_NAME"),
        "variant": get_settings_variant(),
        "addon_version": ADDON_VERSION,
        "pid": os.getpid(),
    }


def get_workfile_from_launch_args(launch_args):
    """Workfile path passed to TVPaint executable.

    Args:
        launch_args (list[str]): TVPaint executable followed by arguments.

    Returns:
        Optional[str]: Path to workfile.

    """
    for arg in launch_args[1:]:
        if arg.lower().endswith(".tvpp"):
            return arg
    return None


class RunningTVPaint:
    """TVPaint which is already running.

    TVPaint is single instance application, launching its executable again
    only passes arguments to the running TVPaint. AYON has to use it.

    Args:
        server_info (TVPaintServerInfo): Server of the TVPaint plugin.
        host_client (Optional[dict[str, Any]]): Data of AYON process
            controlling the TVPaint, None if there is not any.

    """
    def __init__(self, server_info, host_client):
        self.server_info = server_info
        self.host_client = host_client

    @property
    def has_host_client(self):
        return self.host_client is not None

    def is_compatible(self):
        """Host client uses the same bundle and variant as this process."""
        if self.host_client is None:
            return True
        current = get_host_client_info()
        return all(
            self.host_client.get(key) == current[key]
            for key in ("bundle_name", "studio_bundle_name", "variant")
        )

    def open_workfile(
        self, workfile_path, project_name, folder_path, task_name
    ):
        """Let host client open workfile in context.

        Raises:
            TVPaintRpcError: Host client failed to open the workfile.
            ConnectionError: Connection to TVPaint failed.

        """
        client = TVPaintRpcClient()
        try:
            client.connect(self.server_info.url)
            # No timeout, user might be asked to save current changes
            client.send_request("send_to_host", {
                "method": "open_workfile",
                "params": {
                    "workfile_path": workfile_path,
                    "project_name": project_name,
                    "folder_path": folder_path,
                    "task_name": task_name,
                },
            })
        finally:
            client.close()


def find_running_tvpaint(executable):
    """Find running TVPaint launched with the executable.

    Args:
        executable (str): Path to TVPaint executable.

    Returns:
        Optional[RunningTVPaint]: Running TVPaint or None.

    """
    for server_info in get_running_servers():
        if not server_info.is_executable(executable):
            continue

        client = TVPaintRpcClient()
        try:
            client.connect(server_info.url)
            info = client.send_request("get_server_info", timeout=5)
        except (
            TVPaintRpcError,
            ConnectionError,
            TimeoutError,
            OSError,
            aiohttp.ClientError,
        ):
            log.warning(
                "Failed to connect to running TVPaint"
                f" (pid {server_info.pid})",
                exc_info=True
            )
            continue
        finally:
            client.close()
        return RunningTVPaint(server_info, info.get("host_client"))
    return None


class QtTVPaintRpc:
    """Methods called by TVPaint plugin from its menu or by other AYON
    processes through TVPaint plugin.
    """
    def __init__(self, communication_obj):
        from ayon_core.tools.utils import host_tools
        self.tools_helper = host_tools.HostToolsHelper()

        self.communication_obj = communication_obj

    def register(self, rpc_client):
        for name, callback in (
            ("workfiles_tool", self.workfiles_tool),
            ("loader_tool", self.loader_tool),
            ("publish_tool", self.publish_tool),
            ("scene_inventory_tool", self.scene_inventory_tool),
            ("library_loader_tool", self.library_loader_tool),
            ("experimental_tools", self.experimental_tools),
            ("open_workfile", self.open_workfile),
        ):
            rpc_client.add_method(name, callback)

    async def open_workfile(
        self, workfile_path, project_name, folder_path, task_name
    ):
        """Open workfile with context, called by other AYON process.

        The context is stored to the workfile metadata, the project can
        differ from the current one.
        """
        log.info(f"Opening workfile '{workfile_path}' requested by launch")
        item = MainThreadItem(
            self._open_workfile,
            workfile_path,
            project_name,
            folder_path,
            task_name,
        )
        self._execute_in_main_thread(item, wait=False)
        await item.async_wait()

    def _open_workfile(
        self, workfile_path, project_name, folder_path, task_name
    ):
        import ayon_api
        from ayon_core.pipeline import registered_host

        if not os.path.exists(workfile_path):
            raise ValueError(f"Workfile '{workfile_path}' does not exist.")

        folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
        if not folder_entity:
            raise ValueError(f"Folder '{folder_path}' was not found.")
        task_entity = ayon_api.get_task_by_name(
            project_name, folder_entity["id"], task_name
        )
        if not task_entity:
            raise ValueError(
                f"Task '{task_name}' was not found in '{folder_path}'."
            )

        registered_host().open_workfile_in_context(
            workfile_path, project_name, folder_entity, task_entity
        )

    # Panel routes for tools
    def workfiles_tool(self):
        log.info("Triggering Workfile tool")
        item = MainThreadItem(self.tools_helper.show_workfiles)
        self._execute_in_main_thread(item, wait=False)

    def loader_tool(self):
        log.info("Triggering Loader tool")
        item = MainThreadItem(self.tools_helper.show_loader)
        self._execute_in_main_thread(item, wait=False)

    def publish_tool(self):
        log.info("Triggering Publish tool")
        item = MainThreadItem(self.tools_helper.show_publisher_tool)
        self._execute_in_main_thread(item, wait=False)

    def scene_inventory_tool(self):
        log.info("Triggering Scene inventory tool")
        item = MainThreadItem(self.tools_helper.show_scene_inventory)
        self._execute_in_main_thread(item, wait=False)

    def library_loader_tool(self):
        log.info("Triggering Library loader tool")
        item = MainThreadItem(self.tools_helper.show_library_loader)
        self._execute_in_main_thread(item, wait=False)

    def experimental_tools(self):
        log.info("Triggering Experimental tools")
        item = MainThreadItem(self.tools_helper.show_experimental_tools_dialog)
        self._execute_in_main_thread(item, wait=False)

    def _execute_in_main_thread(self, item, **kwargs):
        return self.communication_obj.execute_in_main_thread(item, **kwargs)


class MainThreadItem:
    """Structure to store information about callback in main thread.

    Item should be used to execute callback in main thread which may be needed
    for execution of Qt objects.

    Item store callback (callable variable), arguments and keyword arguments
    for the callback. Item hold information about it's process.
    """
    not_set = object()
    sleep_time = 0.1

    def __init__(self, callback, *args, **kwargs):
        self.done = False
        self.exception = self.not_set
        self.result = self.not_set
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def execute(self):
        """Execute callback and store its result.

        Method must be called from main thread. Item is marked as `done`
        when callback execution finished. Store output of callback of exception
        information when callback raises one.
        """
        log.debug("Executing process in main thread")
        if self.done:
            log.warning("- item is already processed")
            return

        callback = self.callback
        args = self.args
        kwargs = self.kwargs
        log.info("Running callback: {}".format(str(callback)))
        try:
            result = callback(*args, **kwargs)
            self.result = result

        except Exception as exc:
            self.exception = exc

        finally:
            self.done = True

    def wait(self):
        """Wait for result from main thread.

        This method stops current thread until callback is executed.

        Returns:
            object: Output of callback. May be any type or object.

        Raises:
            Exception: Reraise any exception that happened during callback
                execution.
        """
        while not self.done:
            time.sleep(self.sleep_time)

        if self.exception is self.not_set:
            return self.result
        raise self.exception

    async def async_wait(self):
        """Wait for result from main thread.

        Returns:
            object: Output of callback. May be any type or object.

        Raises:
            Exception: Reraise any exception that happened during callback
                execution.
        """
        while not self.done:
            await asyncio.sleep(self.sleep_time)

        if self.exception is self.not_set:
            return self.result
        raise self.exception


class BaseCommunicator:
    def __init__(self):
        self.process = None
        self.rpc_client = None
        self.server_info = None
        self.exit_code = None

    @property
    def is_connected(self):
        if self.rpc_client is None:
            return False
        return self.rpc_client.is_connected

    @property
    def server_is_running(self):
        """Kept for backwards compatibility, use 'is_connected'."""
        return self.is_connected

    def _windows_file_process(self, src_dst_mapping, to_remove):
        """Windows specific file processing asking for admin permissions.

        It is required to have administration permissions to modify plugin
        files in TVPaint installation folder.

        Method requires `pywin32` python module.

        Args:
            src_dst_mapping (list, tuple, set): Mapping of source file to
                destination. Both must be full path. Each item must be iterable
                of size 2 `(C:/src/file.dll, C:/dst/file.dll)`.
            to_remove (list): Fullpath to files that should be removed.
        """

        import pythoncom
        from win32comext.shell import shell

        # Create temp folder where plugin files are temporary copied
        # - reason is that copy to TVPaint requires administartion permissions
        #   but admin may not have access to source folder
        tmp_dir = os.path.normpath(
            tempfile.mkdtemp(prefix="tvpaint_copy_")
        )

        # Copy source to temp folder and create new mapping
        dst_folders = collections.defaultdict(list)
        new_src_dst_mapping = []
        for old_src, dst in src_dst_mapping:
            new_src = os.path.join(tmp_dir, os.path.split(old_src)[1])
            shutil.copy(old_src, new_src)
            new_src_dst_mapping.append((new_src, dst))

        for src, dst in new_src_dst_mapping:
            src = os.path.normpath(src)
            dst = os.path.normpath(dst)
            dst_filename = os.path.basename(dst)
            dst_folder_path = os.path.dirname(dst)
            dst_folders[dst_folder_path].append((dst_filename, src))

        # create an instance of IFileOperation
        fo = pythoncom.CoCreateInstance(
            shell.CLSID_FileOperation,
            None,
            pythoncom.CLSCTX_ALL,
            shell.IID_IFileOperation
        )
        # Add delete command to file operation object
        for filepath in to_remove:
            item = shell.SHCreateItemFromParsingName(
                filepath, None, shell.IID_IShellItem
            )
            fo.DeleteItem(item)

        # here you can use SetOperationFlags, progress Sinks, etc.
        for folder_path, items in dst_folders.items():
            # create an instance of IShellItem for the target folder
            folder_item = shell.SHCreateItemFromParsingName(
                folder_path, None, shell.IID_IShellItem
            )
            for _dst_filename, source_file_path in items:
                # create an instance of IShellItem for the source item
                copy_item = shell.SHCreateItemFromParsingName(
                    source_file_path, None, shell.IID_IShellItem
                )
                # queue the copy operation
                fo.CopyItem(copy_item, folder_item, _dst_filename, None)

        # commit
        fo.PerformOperations()

        # Remove temp folder
        shutil.rmtree(tmp_dir)

    def _prepare_windows_plugin(self, launch_args):
        """Copy plugin to TVPaint plugins and set PATH to dependencies.

        Check if plugin in TVPaint's plugins exist and match to plugin
        version to current implementation version. Based on 64-bit or 32-bit
        version of the plugin. Path to libraries required for plugin is added
        to PATH variable.
        """

        host_executable = launch_args[0]
        executable_file = os.path.basename(host_executable)
        if "64bit" in executable_file:
            subfolder = "windows_x64"
        elif "32bit" in executable_file:
            subfolder = "windows_x86"
        else:
            raise ValueError(
                "Can't determine if executable "
                "leads to 32-bit or 64-bit TVPaint!"
            )

        plugin_files_path = get_plugin_files_path()
        # Folder for right windows plugin files
        source_plugins_dir = os.path.join(plugin_files_path, subfolder)

        # Path to libraries (.dll) required for plugin library
        # - additional libraries can be copied to TVPaint installation folder
        #   (next to executable) or added to PATH environment variable
        additional_libs_folder = os.path.join(
            source_plugins_dir,
            "additional_libraries"
        )
        additional_libs_folder = additional_libs_folder.replace("\\", "/")
        if (
            os.path.exists(additional_libs_folder)
            and additional_libs_folder not in os.environ["PATH"]
        ):
            os.environ["PATH"] += (os.pathsep + additional_libs_folder)

        # Path to TVPaint's plugins folder (where we want to add our plugin)
        host_plugins_path = os.path.join(
            os.path.dirname(host_executable),
            "plugins"
        )

        # Files that must be copied to TVPaint's plugin folder
        plugin_dir = os.path.join(source_plugins_dir, "plugin")

        to_copy = []
        to_remove = []
        # Remove old plugin name
        deprecated_filepath = os.path.join(
            host_plugins_path, "AvalonPlugin.dll"
        )
        if os.path.exists(deprecated_filepath):
            to_remove.append(deprecated_filepath)

        for filename in os.listdir(plugin_dir):
            src_full_path = os.path.join(plugin_dir, filename)
            dst_full_path = os.path.join(host_plugins_path, filename)
            if dst_full_path in to_remove:
                to_remove.remove(dst_full_path)

            if (
                not os.path.exists(dst_full_path)
                or not filecmp.cmp(src_full_path, dst_full_path)
            ):
                to_copy.append((src_full_path, dst_full_path))

        # Skip copy if everything is done
        if not to_copy and not to_remove:
            return

        # Try to copy
        try:
            self._windows_file_process(to_copy, to_remove)
        except Exception:
            log.error("Plugin copy failed", exc_info=True)

        # Validate copy was done
        invalid_copy = []
        for src, dst in to_copy:
            if not os.path.exists(dst) or not filecmp.cmp(src, dst):
                invalid_copy.append((src, dst))

        # Validate delete was dones
        invalid_remove = []
        for filepath in to_remove:
            if os.path.exists(filepath):
                invalid_remove.append(filepath)

        if not invalid_remove and not invalid_copy:
            return

        msg_parts = []
        if invalid_remove:
            msg_parts.append(
                "Failed to remove files: {}".format(", ".join(invalid_remove))
            )

        if invalid_copy:
            _invalid = [
                "\"{}\" -> \"{}\"".format(src, dst)
                for src, dst in invalid_copy
            ]
            msg_parts.append(
                "Failed to copy files: {}".format(", ".join(_invalid))
            )
        raise RuntimeError(" & ".join(msg_parts))

    @staticmethod
    def _get_linux_install_dir(executable):
        """TVPaint installation folder from executable.

        Executable in PATH (e.g. '/usr/bin/tvp-animation-11.7.6-pro') is
        a symlink to executable in TVPaint installation folder.
        """
        executable = shutil.which(executable) or executable
        return os.path.dirname(os.path.realpath(executable))

    def _prepare_linux_plugin(self, launch_args):
        """Copy plugin to TVPaint plugins.

        TVPaint is installed by root, so the copy fails if the user can't
        write to the installation folder. Then the plugin has to be copied
        manually by an administrator.
        """
        plugin_dir = os.path.join(
            get_plugin_files_path(), "linux_x64", "plugin"
        )
        if not os.path.isdir(plugin_dir):
            log.warning(
                "TVPaint plugin for Linux is not available in '%s'.",
                plugin_dir
            )
            return

        host_plugins_path = os.path.join(
            self._get_linux_install_dir(launch_args[0]), "plugins"
        )

        to_copy = []
        for filename in os.listdir(plugin_dir):
            src_full_path = os.path.join(plugin_dir, filename)
            dst_full_path = os.path.join(host_plugins_path, filename)
            if (
                not os.path.exists(dst_full_path)
                or not filecmp.cmp(src_full_path, dst_full_path)
            ):
                to_copy.append((src_full_path, dst_full_path))

        invalid_copy = []
        for src, dst in to_copy:
            try:
                shutil.copyfile(src, dst)
            except OSError:
                log.debug("Plugin copy failed", exc_info=True)
                invalid_copy.append((src, dst))

        if not invalid_copy:
            return

        commands = [
            "sudo cp {} {}".format(shlex.quote(src), shlex.quote(dst))
            for src, dst in invalid_copy
        ]
        raise RuntimeError(
            "Failed to copy AYON plugin to TVPaint plugins. Copy it as"
            " administrator: {}".format(" && ".join(commands))
        )

    def _launch_tv_paint(self, launch_args, env=None):
        kwargs = {}
        if platform.system().lower() == "windows":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True
            # TVPaint looks for its 'data' relative to working directory
            #   and shows modal "file not found" dialog if it's elsewhere.
            kwargs["cwd"] = self._get_linux_install_dir(launch_args[0])
        _env = os.environ.copy()
        if env:
            _env.update(env)
        env = _env
        # Remove QuickTime from PATH on windows
        # - quicktime overrides TVPaint's ffmpeg encode/decode which may
        #   cause issues on loading
        if platform.system().lower() == "windows":
            new_path = []
            for path in env["PATH"].split(os.pathsep):
                if path and "quicktime" not in path.lower():
                    new_path.append(path)
            env["PATH"] = os.pathsep.join(new_path)

        kwargs["env"] = env
        self.process = subprocess.Popen(launch_args, **kwargs)

    def _create_client(self):
        self.rpc_client = TVPaintRpcClient()

    def _stop_client(self):
        if self.rpc_client is not None:
            self.rpc_client.close()

    def _exit(self, exit_code=None):
        self._stop_client()
        if exit_code is not None:
            self.exit_code = exit_code

        if self.exit_code is None:
            self.exit_code = 0

    def stop(self):
        """Stop communication and currently running python process."""
        log.info("Stopping communication")
        self._exit()

    def _wait_for_server(self, launch_id):
        """Wait until TVPaint plugin starts its server.

        Returns:
            Optional[TVPaintServerInfo]: Server info or None if TVPaint
                process ended.

        """
        while True:
            if self.process.poll() is not None:
                return None

            server_info = find_server(launch_id=launch_id)
            if server_info is not None:
                return server_info
            time.sleep(0.5)

    def launch(self, launch_args):
        """Prepare all required data, launch host and connect to it.

        TVPaint plugin starts a websocket server and stores information
        about it to servers directory. The launch id is used to find
        server of the launched process.
        """
        platform_name = platform.system().lower()
        if platform_name == "windows":
            self._prepare_windows_plugin(launch_args)
        elif platform_name == "linux":
            self._prepare_linux_plugin(launch_args)

        self._create_client()

        launch_id = uuid.uuid4().hex
        env = {LAUNCH_ID_ENV_KEY: launch_id}
        log.info("Launching TVPaint")
        self._launch_tv_paint(launch_args, env)

        log.info("Waiting for TVPaint server")
        server_info = self._wait_for_server(launch_id)
        if server_info is None:
            log.debug("Host process is not alive. Exiting")
            self._exit(1)
            return

        self.connect(server_info)

        self._on_client_connect()

        emit_event("application.launched")

    def attach(self, server_info, workfile_path=None):
        """Use already running TVPaint which has no host client.

        TVPaint is single instance application, so it can't be launched
        again. The workfile is opened the same way as if it was passed to
        launched TVPaint, its context is stored on 'application.launched'.

        Args:
            server_info (TVPaintServerInfo): Server of running TVPaint.
            workfile_path (Optional[str]): Workfile to open.

        """
        from ayon_core.pipeline import registered_host

        self._create_client()
        self.process = _RunningProcess(server_info.pid)
        self.connect(server_info)

        self._on_client_connect()

        if workfile_path:
            log.info(f"Opening workfile '{workfile_path}'")
            registered_host().open_workfile(workfile_path)

        emit_event("application.launched")

    def connect(self, server_info):
        """Connect to server of running TVPaint.

        Args:
            server_info (TVPaintServerInfo): Server to connect to.

        """
        log.info(f"Connecting to TVPaint server {server_info.url}")
        self.server_info = server_info
        self.rpc_client.connect(server_info.url)
        log.info("Connected to TVPaint")

    def _on_client_connect(self):
        pass

    def client(self):
        if not self.is_connected:
            log.warning("Communicator is not connected to TVPaint.")
            return None
        return self.rpc_client

    def send_request(self, method, params=None):
        client = self.client()
        if not client:
            return None
        try:
            return client.send_request(method, params)
        except ConnectionError:
            log.warning("Connection to TVPaint was closed.")
            return None

    def send_notification(self, method, params=None):
        client = self.client()
        if not client:
            return
        try:
            client.send_notification(method, params)
        except ConnectionError:
            log.warning("Connection to TVPaint was closed.")

    def execute_george(self, george_script):
        """Execute single line george command in TVPaint.

        Returns:
            Optional[str]: Output of the command, None if not connected.

        """
        return self.send_request(
            "execute_george", [george_script]
        )

    def execute_george_batch(self, commands):
        """Execute single line george commands in TVPaint.

        Commands are executed one after another in a single TVPaint tick.

        Args:
            commands (Iterable[str]): George commands.

        Returns:
            Optional[list[str]]: Output of each command, None if not
                connected.

        """
        commands = list(commands)
        if not commands:
            return []
        return self.send_request("execute_george_batch", [commands])

    def get_layer_ids(self):
        """Ids of all layers in current clip.

        Returns:
            Optional[list[int]]: Layer ids, None if not connected.

        """
        return self.send_request("get_layer_ids")

    def get_group_count(self):
        """Number of color groups, without the default group 0.

        Returns:
            Optional[int]: Number of groups, None if not connected.

        """
        return self.send_request("get_group_count")

    def execute_george_through_file(self, george_script):
        """Execute george script with temp file.

        Deprecated:
            Use 'execute_george' or 'execute_george_batch' with single line
            commands instead. Kept for george scripts which need variables
            or control flow, e.g. scripts sent in worker jobs.

        On windows make sure script does not contain paths with backwards
        slashes in paths, TVPaint won't execute properly in that case.

        Args:
            george_script (str): George script to execute. May be multilined.
        """
        temporary_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="a_tvp_", suffix=".grg", delete=False
        )
        temporary_file.write(george_script)
        temporary_file.close()
        temp_file_path = temporary_file.name.replace("\\", "/")
        self.execute_george("tv_runscript {}".format(temp_file_path))
        os.remove(temp_file_path)


class QtCommunicator(BaseCommunicator):
    label = os.getenv("AYON_MENU_LABEL") or "AYON"
    title = "{} Tools".format(label)
    menu_definitions = {
        "title": title,
        "menu_items": [
            {
                "callback": "workfiles_tool",
                "label": "Workfiles",
                "help": "Open workfiles tool"
            }, {
                "callback": "loader_tool",
                "label": "Load",
                "help": "Open loader tool"
            }, {
                "callback": "scene_inventory_tool",
                "label": "Scene inventory",
                "help": "Open scene inventory tool"
            }, {
                "callback": "publish_tool",
                "label": "Publish",
                "help": "Open publisher"
            }, {
                "callback": "library_loader_tool",
                "label": "Library",
                "help": "Open library loader tool"
            }, {
                "callback": "experimental_tools",
                "label": "Experimental tools",
                "help": "Open experimental tools dialog"
            }
        ]
    }

    def __init__(self, qt_app):
        super().__init__()
        self.callback_queue = collections.deque()
        self.qt_app = qt_app

    def _create_client(self):
        super()._create_client()
        QtTVPaintRpc(self).register(self.rpc_client)

    def execute_in_main_thread(self, main_thread_item, wait=True):
        """Add `MainThreadItem` to callback queue and wait for result."""
        self.callback_queue.append(main_thread_item)
        if wait:
            return main_thread_item.wait()

    async def async_execute_in_main_thread(self, main_thread_item, wait=True):
        """Add `MainThreadItem` to callback queue and wait for result."""
        self.callback_queue.append(main_thread_item)
        if wait:
            return await main_thread_item.async_wait()

    def main_thread_listen(self):
        """Get last `MainThreadItem` from queue.

        Must be called from main thread.

        Method checks if host process is still running as it may cause
        issues if not.
        """
        # check if host still running
        if self.process.poll() is not None:
            self._exit()
            return None

        if self.callback_queue:
            return self.callback_queue.popleft()
        return None

    def _on_client_connect(self):
        self._register_host_client()
        super()._on_client_connect()
        self._build_menu()

    def _register_host_client(self):
        """Let other AYON processes know this process controls TVPaint."""
        try:
            self.rpc_client.send_request(
                "register_host", [get_host_client_info()]
            )
        except TVPaintRpcError:
            log.warning(
                "Failed to register as host client of TVPaint",
                exc_info=True
            )

    def _build_menu(self):
        self.send_request(
            "define_menu", [self.menu_definitions]
        )

    def _exit(self, *args, **kwargs):
        super()._exit(*args, **kwargs)
        emit_event("application.exit")
        self.qt_app.exit(self.exit_code)
