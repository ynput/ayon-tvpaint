import os
import sys
import signal
import traceback
import ctypes
import platform
import logging

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import style
from ayon_core.pipeline import install_host
from ayon_tvpaint.api import (
    TVPaintHost,
    CommunicationWrapper,
)
from ayon_tvpaint.api.communication_server import (
    find_running_tvpaint,
    get_host_client_info,
    get_workfile_from_launch_args,
)

log = logging.getLogger(__name__)


def safe_excepthook(*args):
    traceback.print_exception(*args)


def _show_error(message):
    log.error(message)
    QtWidgets.QMessageBox.critical(None, "AYON TVPaint", message)


def _open_in_running_tvpaint(running_tvpaint, launch_args):
    """Let AYON process controlling running TVPaint open the workfile.

    Returns:
        int: Exit code.

    """
    host_client = running_tvpaint.host_client
    if not running_tvpaint.is_compatible():
        current = get_host_client_info()
        _show_error(
            "TVPaint is already running with AYON bundle"
            f" '{host_client.get('bundle_name')}'"
            f" ({host_client.get('variant')}).\n\n"
            "Close TVPaint before launching it with bundle"
            f" '{current['bundle_name']}' ({current['variant']})."
        )
        return 1

    workfile_path = get_workfile_from_launch_args(launch_args)
    if not workfile_path:
        log.info("TVPaint is already running, there is no workfile to open.")
        return 0

    log.info(
        "Opening workfile in running TVPaint"
        f" (pid {running_tvpaint.server_info.pid})"
    )
    try:
        running_tvpaint.open_workfile(
            workfile_path,
            os.getenv("AYON_PROJECT_NAME"),
            os.getenv("AYON_FOLDER_PATH"),
            os.getenv("AYON_TASK_NAME"),
        )
    except Exception as exc:
        _show_error(f"Failed to open workfile in running TVPaint.\n\n{exc}")
        return 1
    return 0


def main(launch_args):
    # Be sure server won't crash at any moment but just print traceback
    sys.excepthook = safe_excepthook

    # Create QtApplication for tools
    # - QApplicaiton is also main thread/event loop of the server
    qt_app = QtWidgets.QApplication([])
    qt_app.setStyleSheet(style.load_stylesheet())

    # TVPaint is single instance application, launching it again would
    #   only pass the arguments to the running TVPaint.
    running_tvpaint = find_running_tvpaint(launch_args[0])
    if running_tvpaint is not None and running_tvpaint.has_host_client:
        sys.exit(_open_in_running_tvpaint(running_tvpaint, launch_args))

    tvpaint_host = TVPaintHost()
    # Execute pipeline installation
    install_host(tvpaint_host)

    # Create Communicator object and trigger launch
    # - this must be done before anything is processed
    communicator = CommunicationWrapper.create_qt_communicator(qt_app)
    if running_tvpaint is None:
        communicator.launch(launch_args)
    else:
        # Running TVPaint without AYON, e.g. launched by user
        communicator.attach(
            running_tvpaint.server_info,
            get_workfile_from_launch_args(launch_args),
        )

    def process_in_main_thread():
        """Execution of `MainThreadItem`."""
        item = communicator.main_thread_listen()
        if item:
            item.execute()

    timer = QtCore.QTimer()
    timer.setInterval(100)
    timer.timeout.connect(process_in_main_thread)
    timer.start()

    # Register terminal signal handler
    def signal_handler(*_args):
        print("You pressed Ctrl+C. Process ended.")
        communicator.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    qt_app.setQuitOnLastWindowClosed(False)

    # Load AYON icon
    icon_path = style.app_icon_path()
    if icon_path:
        icon = QtGui.QIcon(icon_path)
        qt_app.setWindowIcon(icon)

    # Set application name to be able show application icon in task bar
    if platform.system().lower() == "windows":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u"WebsocketServer"
        )

    # Run Qt application event processing
    sys.exit(qt_app.exec_())


if __name__ == "__main__":
    args = list(sys.argv)
    if os.path.abspath(__file__) == os.path.normpath(args[0]):
        # Pop path to script
        args.pop(0)
    main(args)
