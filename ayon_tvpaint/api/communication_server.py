import sys
import subprocess
# ... other imports ...

class CommunicationServer:
    # ... other methods ...

    def _launch_tv_paint(self, launch_args):
        """Launch TVPaint with given arguments."""
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS
        
        self._process = subprocess.Popen(
            launch_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags
        )