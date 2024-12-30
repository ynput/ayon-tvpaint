import os
import json

import pyblish.api

from ayon_tvpaint.api.lib import (
    tv_projectselect,
    tv_projectcurrentid,
    tv_get_mark_in,
    tv_get_mark_out,
    tv_get_background_color,
    tv_get_start_frame,
    tv_get_project_info,
    get_layers_data,
    get_groups_data,
)
from ayon_tvpaint.api.pipeline import (
    SECTION_NAME_CONTEXT,
    SECTION_NAME_INSTANCES,
    SECTION_NAME_CONTAINERS,

    get_workfile_metadata_string,
    write_workfile_metadata,
    get_current_workfile_context,
    list_instances,
)


class ResetTVPaintWorkfileMetadata(pyblish.api.Action):
    """Fix invalid metadata in workfile."""
    label = "Reset invalid workfile metadata"
    on = "failed"

    def process(self, context, plugin):
        metadata_keys = {
            SECTION_NAME_CONTEXT: {},
            SECTION_NAME_INSTANCES: [],
            SECTION_NAME_CONTAINERS: []
        }
        for metadata_key, default in metadata_keys.items():
            json_string = get_workfile_metadata_string(metadata_key)
            if not json_string:
                continue

            try:
                return json.loads(json_string)
            except Exception:
                self.log.warning(
                    (
                        "Couldn't parse metadata from key \"{}\"."
                        " Will reset to default value \"{}\"."
                        " Loaded value was: {}"
                    ).format(metadata_key, default, json_string),
                    exc_info=True
                )
                write_workfile_metadata(metadata_key, default)


class CollectWorkfileData(pyblish.api.ContextPlugin):
    label = "Collect Workfile Data"
    order = pyblish.api.CollectorOrder - 0.45
    hosts = ["tvpaint"]
    actions = [ResetTVPaintWorkfileMetadata]

    settings_category = "tvpaint"

    def process(self, context):
        current_project_id = tv_projectcurrentid()
        tv_projectselect(current_project_id)

        # Collect and store current context to have reference
        current_context = {
            "project_name": context.data["projectName"],
            "folder_path": context.data["folderPath"],
            "task_name": context.data["task"]
        }
        self.log.debug("Current context is: {}".format(current_context))

        # Collect context from workfile metadata
        self.log.info("Collecting workfile context")

        workfile_context = get_current_workfile_context()
        if "project" in workfile_context:
            workfile_context = {
                "project_name": workfile_context.get("project"),
                "folder_path": workfile_context.get("asset"),
                "task_name": workfile_context.get("task"),
            }
        # Store workfile context to pyblish context
        context.data["workfile_context"] = workfile_context
        if workfile_context:
            # Change current context with context from workfile
            key_map = (
                ("AYON_FOLDER_PATH", "folder_path"),
                ("AYON_TASK_NAME", "task_name")
            )
            for env_key, key in key_map:
                os.environ[env_key] = workfile_context[key]
            self.log.info("Context changed to: {}".format(workfile_context))

            folder_path = workfile_context["folder_path"]
            task_name = workfile_context["task_name"]

        else:
            folder_path = current_context["folder_path"]
            task_name = current_context["task_name"]
            # Handle older workfiles or workfiles without metadata
            self.log.warning((
                "Workfile does not contain information about context."
                " Using current Session context."
            ))

        # Store context folder path
        context.data["folderPath"] = folder_path
        context.data["task"] = task_name
        self.log.info(
            "Context is set to Folder: \"{}\" and Task: \"{}\"".format(
                folder_path, task_name
            )
        )

        # Collect instances
        self.log.info("Collecting instance data from workfile")
        instance_data = list_instances()
        context.data["workfileInstances"] = instance_data
        self.log.debug(
            "Instance data:\"{}".format(json.dumps(instance_data, indent=4))
        )

        # Collect information about layers
        self.log.info("Collecting layers data from workfile")
        layers_data = get_layers_data()
        layers_by_name = {}
        for layer in layers_data:
            layer_name = layer["name"]
            if layer_name not in layers_by_name:
                layers_by_name[layer_name] = []
            layers_by_name[layer_name].append(layer)
        context.data["layersData"] = layers_data
        context.data["layersByName"] = layers_by_name

        self.log.debug(
            "Layers data:\"{}".format(json.dumps(layers_data, indent=4))
        )

        # Collect information about groups
        self.log.info("Collecting groups data from workfile")
        group_data = get_groups_data()
        context.data["groupsData"] = group_data
        self.log.debug(
            "Group data:\"{}".format(json.dumps(group_data, indent=4))
        )

        self.log.info("Collecting scene data from workfile")
        workfile_info = tv_get_project_info()
        mark_in_frame, mark_in_state = tv_get_mark_in()
        mark_out_frame, mark_out_state = tv_get_mark_out()
        start_frame = tv_get_start_frame()

        scene_data = {
            "currentFile": workfile_info.path,
            "sceneWidth": workfile_info.width,
            "sceneHeight": workfile_info.height,
            "scenePixelAspect": workfile_info.pixel_apsect,
            "sceneFps": workfile_info.frame_rate,
            "sceneFieldOrder": workfile_info.field_order,
            "sceneMarkIn": mark_in_frame,
            "sceneMarkInState": mark_in_state == "set",
            "sceneMarkOut": mark_out_frame,
            "sceneMarkOutState": mark_out_state == "set",
            "sceneStartFrame": start_frame,
            "sceneBgColor": tv_get_background_color(),
        }
        self.log.debug(
            "Scene data: {}".format(json.dumps(scene_data, indent=4))
        )
        context.data.update(scene_data)
