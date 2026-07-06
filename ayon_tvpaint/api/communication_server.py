import subprocess
import sys

def _launch_tv_paint(self, launch_args):
    # ... existing code before the subprocess call ...
    if sys.platform == "win32":
        creation_flags = subprocess.DETACHED_PROCESS
    else:
        creation_flags = 0  # No special flags on macOS/Linux
    self._process = subprocess.Popen(
        launch_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creation_flags
    )
    # ... rest of method ...
