import os
import re
import glob
import configparser

from ayon_applications import PreLaunchHook, LaunchTypes


class TvpaintGeorgeWritePopup(PreLaunchHook):
    """Disable TVPaint's modal "Write to file" permission popup.

    Metadata storage and any george script output are based on george
    file writes. Each of them is blocked by the popup until the
    preference is disabled, which nobody can confirm when TVPaint is
    launched headlessly.
    """

    app_groups = {"tvpaint"}
    launch_types = {LaunchTypes.local}
    platforms = {"windows"}

    def execute(self):
        # NOTE config.ini does contain special byte characters that's why
        #     configparser.ConfigParser is NOT used to work with the file.
        key = b"georgecanwritefiledisplaypopup"
        found_config = False
        for config_path in self._iter_tvpaint_config_files():
            found_config = True
            with open(config_path, "rb") as stream:
                content = stream.read()

            match = re.search(key + rb"[ \t]*=[ \t]*(\d+)", content)
            if match is None:
                self.log.warning(
                    f"Preference \"{key.decode()}\""
                    f" not found in \"{config_path}\"."
                )
                continue

            if match.group(1) == b"0":
                continue

            content = (
                content[:match.start()] + key + b"=0"
                + content[match.end():]
            )
            with open(config_path, "wb") as stream:
                stream.write(content)

            self.log.info(
                f"Disabled george write popup in \"{config_path}\"."
            )

        if not found_config:
            self.log.warning("Did not find any TVPaint 'config.ini'.")

    def _iter_tvpaint_config_files(self):
        """Iterate over config files of installed TVPaint versions.

        Yields:
            str: Path to 'config.ini' of a TVPaint configuration.
        """

        appdata = os.environ.get("APPDATA")
        if not appdata:
            return

        for base in glob.glob(os.path.join(appdata, "tvp animation *")):
            profile = "default"
            system_ini = os.path.join(base, "system.ini")
            if os.path.exists(system_ini):
                parser = configparser.ConfigParser()
                try:
                    parser.read(system_ini)
                    profile = parser.get(
                        "system", "config", fallback=profile
                    )
                except configparser.Error:
                    pass

            config_path = os.path.join(base, profile, "config.ini")
            if os.path.exists(config_path):
                yield config_path
