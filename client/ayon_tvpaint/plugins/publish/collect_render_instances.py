import copy
import pyblish.api
from ayon_core.lib import prepare_template_data


class CollectRenderInstances(pyblish.api.InstancePlugin):
    label = "Collect Render Instances"
    order = pyblish.api.CollectorOrder - 0.4
    hosts = ["tvpaint"]
    families = ["render", "review"]

    settings_category = "tvpaint"
    ignore_render_pass_transparency = False

    def process(self, instance):
        context = instance.context
        creator_identifier = instance.data["creator_identifier"]
        if creator_identifier == "render.layer":
            self._collect_data_for_render_layer(instance)

        elif creator_identifier == "render.pass":
            self._collect_data_for_render_pass(instance)

        elif creator_identifier == "render.scene":
            self._collect_data_for_render_scene(instance)

        else:
            if creator_identifier == "scene.review":
                self._collect_data_for_review(instance)
            return

        product_name = instance.data["productName"]
        instance.data["name"] = product_name
        instance.data["label"] = "{} [{}-{}]".format(
            product_name,
            context.data["sceneMarkIn"] + 1,
            context.data["sceneMarkOut"] + 1
        )

    def _collect_data_for_render_layer(self, instance):
        instance.data["families"].append("renderLayer")
        creator_attributes = instance.data["creator_attributes"]
        group_id = creator_attributes["group_id"]
        if creator_attributes["mark_for_review"]:
            instance.data["families"].append("review")

        layers_data = instance.context.data["layersData"]
        instance.data["layers"] = [
            copy.deepcopy(layer)
            for layer in layers_data
            if layer["group_id"] == group_id
        ]

    def _collect_data_for_render_pass(self, instance):
        instance.data["families"].append("renderPass")

        layer_names = set(instance.data["layer_names"])
        layers_data = instance.context.data["layersData"]

        creator_attributes = instance.data["creator_attributes"]
        if creator_attributes["mark_for_review"]:
            instance.data["families"].append("review")

        instance.data["layers"] = [
            copy.deepcopy(layer)
            for layer in layers_data
            if layer["name"] in layer_names
        ]

        instance.data["ignoreLayersTransparency"] = (
            self.ignore_render_pass_transparency
        )

        render_layer_data = None
        render_layer_id = creator_attributes["render_layer_instance_id"]
        for in_data in instance.context.data["workfileInstances"]:
            if (
                in_data.get("creator_identifier") == "render.layer"
                and in_data["instance_id"] == render_layer_id
            ):
                render_layer_data = in_data
                break

        instance.data["renderLayerData"] = copy.deepcopy(render_layer_data)
        # Invalid state
        if render_layer_data is None:
            return

        project_settings = instance.context.data["project_settings"]
        render_pass_settings = (
            project_settings
            ["tvpaint"]
            ["create"]
            ["create_render_pass"]
        )
        render_pass_template = render_pass_settings["render_pass_template"]
        layer_idx_offset = render_pass_settings["layer_idx_offset"]
        layer_idx_padding = render_pass_settings["layer_idx_padding"]
        layers_count = len(layers_data)
        layer_pos = 1
        if instance.data["layers"]:
            self.log.debug(instance.data["layers"][0])
            max_pos = max(
                layer["position"] for layer in instance.data["layers"]
            )
            layer_pos = layers_count - max_pos

        layer_template = "{}"
        if layer_idx_padding:
            layer_template = f"{{:0>{layer_idx_padding}}}"

        layer_index = layer_template.format(layer_pos * layer_idx_offset)

        render_pass_name = render_pass_template.format(
            **prepare_template_data({
                "variant": instance.data["variant"],
                "layer_index": layer_index,
            })
        )

        render_layer_name = render_layer_data["variant"]
        product_name = instance.data["productName"]
        instance.data["productName"] = product_name.format(
            **prepare_template_data({
                "renderlayer": render_layer_name,
                "renderpass": render_pass_name,
            })
        )

    def _collect_data_for_render_scene(self, instance):
        instance.data["families"].append("renderScene")

        creator_attributes = instance.data["creator_attributes"]
        if creator_attributes["mark_for_review"]:
            instance.data["families"].append("review")

        instance.data["layers"] = copy.deepcopy(
            instance.context.data["layersData"]
        )

        render_pass_name = (
            instance.data["creator_attributes"]["render_pass_name"]
        )
        product_name = instance.data["productName"]
        instance.data["productName"] = product_name.format(
            **prepare_template_data({"renderpass": render_pass_name})
        )

    def _collect_data_for_review(self, instance):
        instance.data["layers"] = copy.deepcopy(
            instance.context.data["layersData"]
        )
