import sys
import subprocess
# ... other imports ...

class CommunicationServer:
    # ... other methods ...

    def _launch_tv_paint(self, launch_args):
        # ... setup ...
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            self._process = subprocess.Popen(
                launch_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
        else:
            # macOS/Linux: use start_new_session to detach process
            self._process = subprocess.Popen(
                launch_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
        # ... rest of method ...