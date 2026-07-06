import sys
import subprocess
import platform

class CommunicationServer:
    # ... other methods ...

    def _launch_tv_paint(self, launch_args):
        # ... prepare args ...
        creationflags = 0
        if platform.system() == 'Windows':
            creationflags = subprocess.DETACHED_PROCESS
        try:
            self._process = subprocess.Popen(
                launch_args,
                creationflags=creationflags
            )
        except Exception:
            # fallback for non-Windows
            self._process = subprocess.Popen(launch_args)
        # ... rest of method ...
}