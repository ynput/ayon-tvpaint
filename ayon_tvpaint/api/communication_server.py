import sys
import subprocess

# ... (other imports and code)

class CommunicationServer:
    # ... (other methods)

    def _launch_tv_paint(self, launch_args):
        # Determine creationflags based on platform
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS
        else:
            creationflags = 0

        # ... (rest of method, using creationflags)
        # Example: subprocess.Popen(launch_args, creationflags=creationflags, ...)
