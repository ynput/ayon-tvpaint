import pyblish.api

from ayon_tvpaint.api.lib import execute_george


class CollectCurrentFile(pyblish.api.ContextPlugin):
    label = "Collect Current File"
    order = pyblish.api.CollectorOrder - 0.5
    hosts = ["tvpaint"]

    def process(self, context):
        current_project_id = execute_george("tv_projectcurrentid")
        execute_george(f"tv_projectselect {current_project_id}")

        self.log.debug("Collecting scene data from workfile")
        workfile_info_parts = execute_george("tv_projectinfo").split(" ")

        # Project frame start - not used
        workfile_info_parts.pop(-1)
        field_order = workfile_info_parts.pop(-1)
        frame_rate = float(workfile_info_parts.pop(-1))
        pixel_apsect = float(workfile_info_parts.pop(-1))
        height = int(workfile_info_parts.pop(-1))
        width = int(workfile_info_parts.pop(-1))
        workfile_path = " ".join(workfile_info_parts).replace("\"", "")

        scene_data = {
            "currentFile": workfile_path,
            "sceneWidth": width,
            "sceneHeight": height,
            "scenePixelAspect": pixel_apsect,
            "sceneFps": frame_rate,
            "sceneFieldOrder": field_order,
            "sceneBgColor": self._get_bg_color(),
        }
        self.log.debug(f"Scene data: {scene_data}")
        context.data.update(scene_data)
