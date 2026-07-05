import os
import sys
import subprocess
import platform

# ... other code ...

def _launch_tv_paint(self, launch_args):
    # Determine platform and set appropriate flags
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = subprocess.DETACHED_PROCESS
    else:
        # On macOS and Linux, use start_new_session to detach process
        pass  # handled via start_new_session in Popen call

    try:
        self._process = subprocess.Popen(
            launch_args,
            creationflags=creationflags,
            start_new_session=(platform.system() != "Windows")
        )
    except AttributeError:
        # Fallback for older Python versions where DETACHED_PROCESS may not exist
        self._process = subprocess.Popen(
            launch_args,
            start_new_session=True
        )
    # ... rest of method ...
