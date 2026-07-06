import subprocess
import sys
# ... other imports and code ...

class CommunicationServer:
    # ... other methods ...

    def _launch_tv_paint(self, launch_args):
        # ... setup code ...
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(launch_args, **kwargs)
        # ... remaining code ...
