import platform
...

    def _launch_tv_paint(self, launch_args):
        ...
        if platform.system() == "Windows":
            process = subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS)
        else:
            process = subprocess.Popen(cmd, start_new_session=True)
        ...