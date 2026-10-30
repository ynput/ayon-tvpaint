from ayon_core.lib.attribute_definitions import BoolDef
from ayon_tvpaint.api import plugin
from ayon_tvpaint.api.lib import import_sequence


class ImportImage(plugin.Loader):
    """Load image or image sequence to TVPaint as new layer."""

    product_base_types = {"render", "image", "background", "plate", "review"}
    product_types = product_base_types
    representations = {"*"}
    settings_category = "tvpaint"

    label = "Import Image"
    order = 1
    icon = "image"
    color = "white"

    defaults = {
        "stretch": True,
        "timestretch": True,
        "preload": True
    }

    @classmethod
    def get_options(cls, contexts):
        return [
            BoolDef(
                "stretch",
                label="Stretch to project size",
                default=cls.defaults["stretch"],
                tooltip="Stretch loaded image/s to project resolution?"
            ),
            BoolDef(
                "timestretch",
                label="Stretch to timeline length",
                default=cls.defaults["timestretch"],
                tooltip="Clip loaded image/s to timeline length?"
            ),
            BoolDef(
                "preload",
                label="Preload loaded image/s",
                default=cls.defaults["preload"],
                tooltip="Preload image/s?"
            )
        ]

    def load(self, context, name, namespace, options):
        stretch = options.get("stretch", self.defaults["stretch"])
        timestretch = options.get("timestretch", self.defaults["timestretch"])
        preload = options.get("preload", self.defaults["preload"])

        # Prepare layer name
        folder_name = context["folder"]["name"]
        version_name = context["version"]["name"]
        layer_name = "{}_{}_v{:0>3}".format(
            folder_name,
            name,
            version_name
        )
        import_sequence(
            self.filepath_from_context(context),
            layer_name,
            stretch=stretch,
            timestretch=timestretch,
            preload=preload,
        )
