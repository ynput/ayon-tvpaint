import json

import pyblish.api
from ayon_core.pipeline import (
    PublishXmlValidationError,
    OptionalPyblishPluginMixin,
)


# TODO @iLliCiTiT add fix action for fps
class ValidateProjectSettings(
    OptionalPyblishPluginMixin,
    pyblish.api.ContextPlugin
):
    """Validate scene settings against database."""

    label = "Validate Scene Settings"
    order = pyblish.api.ValidatorOrder

    settings_category = "tvpaint"
    optional = True

    def process(self, context):
        if not self.is_active(context.data):
            return

        task_attributes = context.data["taskEntity"]["attrib"]
        scene_data = {
            "fps": context.data.get("sceneFps"),
            "resolutionWidth": context.data.get("sceneWidth"),
            "resolutionHeight": context.data.get("sceneHeight"),
            "pixelAspect": context.data.get("scenePixelAspect")
        }
        invalid = {}
        for k in scene_data.keys():
            expected_value = task_attributes[k]
            if scene_data[k] != expected_value:
                invalid[k] = {
                    "current": scene_data[k], "expected": expected_value
                }

        if not invalid:
            return

        raise PublishXmlValidationError(
            self,
            "Scene settings does not match database:\n{}".format(
                json.dumps(invalid, sort_keys=True, indent=4)
            ),
            formatting_data={
                "expected_fps": task_attributes["fps"],
                "current_fps": scene_data["fps"],
                "expected_width": task_attributes["resolutionWidth"],
                "expected_height": task_attributes["resolutionHeight"],
                "current_width": scene_data["resolutionWidth"],
                "current_height": scene_data["resolutionHeight"],
                "expected_pixel_ratio": task_attributes["pixelAspect"],
                "current_pixel_ratio": scene_data["pixelAspect"]
            }
        )
