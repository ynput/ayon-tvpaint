from ayon_tvpaint.api import plugin
from ayon_tvpaint.api.lib import (
    execute_george,
    george_path,
    george_string,
)


class ImportSound(plugin.Loader):
    """Load sound to TVPaint.

    Sound layers does not have ids but only position index so we can't
    reference them as we can't say which is which input.

    We might do that (in future) by input path. Which may be identifier if
    we'll allow only one loaded instance of the representation as an audio.

    This plugin does not work for all version of TVPaint. Known working
    version is TVPaint 11.0.10 .

    It is allowed to load video files as sound but it does not check if video
    file contain any audio.
    """

    product_base_types = {"audio", "review", "plate"}
    product_types = product_base_types
    representations = {"*"}

    label = "Import Sound"
    order = 1
    icon = "image"
    color = "white"

    def load(self, context, name, namespace, options):
        path = self.filepath_from_context(context)
        # Try to get sound clip info to check if we are in TVPaint that can
        #   load sound, it returns empty string if it can't
        clip_id = execute_george("tv_ClipCurrentID")
        clip_info = execute_george(f"tv_SoundClipInfo {clip_id} 0")
        if clip_info == "":
            success = ""
        else:
            success = execute_george(
                f"tv_SoundClipNew {george_string(george_path(path))}"
            )
        if success is not None:
            success = success.strip()

        # Successfully loaded sound
        if success == "0":
            return

        if success == "":
            raise ValueError(
                "Your TVPaint version does not support loading of"
                " sound through George script. Please use manual load."
            )

        if success is None:
            raise ValueError(
                "Unknown error happened during load."
                " Please report and try to use manual load."
            )

        # Possible errors by TVPaint documentation
        # https://www.tvpaint.com/doc/tvpaint-animation-11/george-commands#tv_soundclipnew
        if success == "-1":
            raise ValueError(
                "BUG: George command did not get enough arguments."
            )

        if success == "-2":
            # Who know what does that mean?
            raise ValueError("No current clip without mixer.")

        if success == "-3":
            raise ValueError("TVPaint couldn't read the file.")

        if success == "-4":
            raise ValueError("TVPaint couldn't add the track.")

        raise ValueError("BUG: Unknown success value {}.".format(success))
