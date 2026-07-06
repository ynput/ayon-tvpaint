import sys
import os
import subprocess

class CommunicationServer:
    def _launch_tv_paint(self, launch_args):
        # ... other code ...
        # Fix DETACHED_PROCESS for macOS
        if sys.platform == "win32":
            process = subprocess.Popen(launch_args, creationflags=subprocess.DETACHED_PROCESS)
        else:
            process = subprocess.Popen(launch_args, preexec_fn=os.setsid)
        # ... rest of method ...
        return process
