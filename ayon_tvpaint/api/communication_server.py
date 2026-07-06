import sys
import subprocess
from ayon_tvpaint.api import launch_script

class CommunicationServer:
    # ... other methods ...

    def _launch_tv_paint(self, launch_args):
        """Launch TVPaint with given arguments."""
        executable = self.get_tvpaint_executable()
        if not executable:
            raise RuntimeError("TVPaint executable not found")

        cmd = [executable] + launch_args
        # On Windows, use DETACHED_PROCESS to avoid console window
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS
        self._process = subprocess.Popen(cmd, **kwargs)
}
