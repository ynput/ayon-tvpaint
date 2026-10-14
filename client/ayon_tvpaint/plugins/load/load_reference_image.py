import collections

from ayon_core.lib.attribute_definitions import BoolDef
from ayon_core.pipeline import registered_host
from ayon_tvpaint.api import plugin
from ayon_tvpaint.api.lib import (
    get_layers_data,
    execute_george_batch,
    george_string,
    import_sequence,
)
from ayon_tvpaint.api.pipeline import (
    write_workfile_metadata,
    SECTION_NAME_CONTAINERS,
    containerise,
)


class LoadImage(plugin.Loader):
    """Load image or image sequence to TVPaint as new layer."""

    product_base_types = {"render", "image", "background", "plate", "review"}
    product_types = product_base_types
    representations = {"*"}
    settings_category = "tvpaint"

    label = "Load Image"
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
        product_name = context["product"]["name"]
        layer_name = self.get_unique_layer_name(folder_name, product_name)

        layer_id = import_sequence(
            self.filepath_from_context(context),
            layer_name,
            stretch=stretch,
            timestretch=timestretch,
            preload=preload,
        )
        loaded_layers = get_layers_data(layer_id)
        if not loaded_layers:
            raise AssertionError(
                f"Loaded layer with id '{layer_id}' was not found."
            )

        layer_names = [loaded_layers[0]["name"]]
        namespace = namespace or layer_name
        return containerise(
            name=name,
            namespace=namespace,
            members=layer_names,
            context=context,
            loader=self.__class__.__name__
        )

    def _remove_layers(self, layer_names=None, layer_ids=None, layers=None):
        if not layer_names and not layer_ids:
            self.log.warning("Got empty layer names list.")
            return

        if layers is None:
            layers = get_layers_data()

        available_ids = set(layer["layer_id"] for layer in layers)

        if layer_ids is None:
            # Backwards compatibility (layer ids were stored instead of names)
            layer_names_are_ids = True
            for layer_name in layer_names:
                if (
                    not isinstance(layer_name, int)
                    and not layer_name.isnumeric()
                ):
                    layer_names_are_ids = False
                    break

            if layer_names_are_ids:
                layer_ids = layer_names

        layer_ids_to_remove = []
        if layer_ids is not None:
            for layer_id in layer_ids:
                if layer_id in available_ids:
                    layer_ids_to_remove.append(layer_id)

        else:
            layers_by_name = collections.defaultdict(list)
            for layer in layers:
                layers_by_name[layer["name"]].append(layer)

            for layer_name in layer_names:
                layers = layers_by_name[layer_name]
                if len(layers) == 1:
                    layer_ids_to_remove.append(layers[0]["layer_id"])

        if not layer_ids_to_remove:
            self.log.warning("No layers to delete.")
            return

        execute_george_batch(
            f"tv_LayerKill {layer_id}"
            for layer_id in layer_ids_to_remove
        )

    def _remove_container(self, container):
        if not container:
            return
        representation = container["representation"]
        members = self.get_members_from_container(container)
        host = registered_host()
        current_containers = host.get_containers()
        pop_idx = None
        for idx, cur_con in enumerate(current_containers):
            cur_members = self.get_members_from_container(cur_con)
            if (
                cur_members == members
                and cur_con["representation"] == representation
            ):
                pop_idx = idx
                break

        if pop_idx is None:
            self.log.warning(
                "Didn't find container in workfile containers. {}".format(
                    container
                )
            )
            return

        current_containers.pop(pop_idx)
        write_workfile_metadata(
            SECTION_NAME_CONTAINERS, current_containers
        )

    def remove(self, container):
        members = self.get_members_from_container(container)
        self.log.warning("Layers to delete {}".format(members))
        self._remove_layers(members)
        self._remove_container(container)

    def switch(self, container, representation):
        self.update(container, representation)

    def update(self, container, context):
        """Replace container with different version.

        New layers are loaded as first step. Then is tried to change data in
        new layers with data from old layers. When that is done old layers are
        removed.
        """

        # Create new containers first
        # Get layer ids from previous container
        old_layer_names = self.get_members_from_container(container)

        # Backwards compatibility (layer ids were stored instead of names)
        old_layers_are_ids = True
        for name in old_layer_names:
            if isinstance(name, int) or name.isnumeric():
                continue
            old_layers_are_ids = False
            break

        old_layers = []
        layers = get_layers_data()
        previous_layer_ids = set(layer["layer_id"] for layer in layers)
        if old_layers_are_ids:
            for layer in layers:
                if layer["layer_id"] in old_layer_names:
                    old_layers.append(layer)
        else:
            layers_by_name = collections.defaultdict(list)
            for layer in layers:
                layers_by_name[layer["name"]].append(layer)

            for layer_name in old_layer_names:
                layers = layers_by_name[layer_name]
                if len(layers) == 1:
                    old_layers.append(layers[0])

        # Prepare few data
        new_start_position = None
        new_group_id = None
        layer_ids_to_remove = set()
        for layer in old_layers:
            layer_ids_to_remove.add(layer["layer_id"])
            position = layer["position"]
            group_id = layer["group_id"]
            if new_start_position is None:
                new_start_position = position
            elif new_start_position > position:
                new_start_position = position

            if new_group_id is None:
                new_group_id = group_id
            elif new_group_id < 0:
                continue
            elif new_group_id != group_id:
                new_group_id = -1

        # Remove old container
        self._remove_container(container)
        # Remove old layers
        self._remove_layers(layer_ids=layer_ids_to_remove)

        name = container["name"]
        namespace = container["namespace"]
        new_container = self.load(context, name, namespace, {})
        new_layer_names = self.get_members_from_container(new_container)

        layers = get_layers_data()

        new_layers = []
        for layer in layers:
            if layer["layer_id"] in previous_layer_ids:
                continue
            if layer["name"] in new_layer_names:
                new_layers.append(layer)

        george_script_lines = []
        # Group new layers to same group as previous container layers had
        # - all old layers must be under same group
        if new_group_id is not None and new_group_id > 0:
            for layer in new_layers:
                line = "tv_layercolor set {} {}".format(
                    layer["layer_id"], new_group_id
                )
                george_script_lines.append(line)

        # Rename new layer to have same name
        # - only if both old and new have one layer
        if len(old_layers) == 1 and len(new_layers) == 1:
            layer_name = old_layers[0]["name"]
            george_script_lines.append(
                "tv_layerrename {} {}".format(
                    new_layers[0]["layer_id"], george_string(layer_name)
                )
            )

        # Change position of new layer
        # - this must be done before remove old layers
        if len(new_layers) == 1 and new_start_position is not None:
            new_layer = new_layers[0]
            george_script_lines.extend([
                "tv_layerset {}".format(new_layer["layer_id"]),
                "tv_layermove {}".format(new_start_position)
            ])

        execute_george_batch(george_script_lines)
