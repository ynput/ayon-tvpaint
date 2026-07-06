import os
import sys
import subprocess
import platform

# ... (other imports and code)

class CommunicationServer:
    # ...
    def _launch_tv_paint(self, launch_args):
        # ... existing code up to subprocess creation
        if platform.system() == 'Windows':
            creationflags = subprocess.DETACHED_PROCESS
        else:
            creationflags = 0
        try:
            self._process = subprocess.Popen(
                launch_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                start_new_session=(platform.system() != 'Windows')
            )
        except Exception as e:
            raise RuntimeError(f"Failed to launch TVPaint: {e}")
        # ... rest of the method
