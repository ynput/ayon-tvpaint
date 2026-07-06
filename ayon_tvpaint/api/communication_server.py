import sys
import subprocess
import os
import json
import platform
import socket
import threading
import time
import logging
from pathlib import Path

# ... (other imports and code, unchanged except the _launch_tv_paint method)

class CommunicationServer:
    # ...

    def _launch_tv_paint(self, launch_args):
        import subprocess
        tvpaint_path = self._get_tvpaint_path()
        if not tvpaint_path:
            raise RuntimeError("TVPaint executable not found")

        # Build command
        cmd = [tvpaint_path] + launch_args

        # Cross-platform process creation flags
        creationflags = 0
        start_new_session = False
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS  # Windows: detach from console
        else:
            start_new_session = True  # POSIX: start new session to detach

        try:
            process = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                start_new_session=start_new_session,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE
            )
            self._tvpaint_process = process
            self._process_pid = process.pid
        except Exception as e:
            raise RuntimeError(f"Failed to launch TVPaint: {e}")

    # ... rest of the class
