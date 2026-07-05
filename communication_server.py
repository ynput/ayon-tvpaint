import subprocess
import sys

def _launch_tv_paint(self, launch_args):
    # ... existing code ...
    creationflags = 0
    if sys.platform == 'win32':
        creationflags = subprocess.DETACHED_PROCESS
    try:
        self._process = subprocess.Popen(
            launch_args,
            creationflags=creationflags
        )
    except AttributeError:
        # Fallback for platforms without DETACHED_PROCESS
        self._process = subprocess.Popen(launch_args)
    # ... rest of method ...