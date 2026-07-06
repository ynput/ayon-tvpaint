# ... (rest of file unchanged) ...

    def _launch_tv_paint(self, launch_args):
        """Launch TVPaint application with given arguments."""
        import sys
        import subprocess

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.DETACHED_PROCESS
        else:
            # On macOS and Linux, use start_new_session to detach
            creationflags = 0  # Not used on Unix, but keep for compatibility

        try:
            self._process = subprocess.Popen(
                launch_args,
                startupinfo=startupinfo,
                creationflags=creationflags,
                start_new_session=(sys.platform != "win32"),  # Detach on Unix
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            self._log.error("Failed to launch TVPaint: %s", e)
            raise
# ... (rest of file unchanged) ...