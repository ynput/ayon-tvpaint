import sys
import subprocess

# ... other imports and code ...

class CommunicationServer:
    # ... other methods ...

    def _launch_tv_paint(self, launch_args):
        # ... existing code before creationflags ...
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS
            popen_kwargs = {"creationflags": creationflags}
        else:
            # On macOS and Linux, use start_new_session to detach process
            popen_kwargs = {"start_new_session": True}
        # ... rest of launch logic using popen_kwargs ...
        self._process = subprocess.Popen(
            launch_args,
            **popen_kwargs
        )
        # ... rest of method ...
