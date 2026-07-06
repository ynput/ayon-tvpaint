import sys
import subprocess

# ... other methods ...

def _launch_tv_paint(self, launch_args):
    # ... previous code ...
    # Fix for macOS compatibility: DETACHED_PROCESS is Windows-only
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS
        start_new_session = False
    else:
        creationflags = 0
        start_new_session = True

    process = subprocess.Popen(
        launch_args,
        creationflags=creationflags,
        start_new_session=start_new_session
    )
    # ... remaining code ...
