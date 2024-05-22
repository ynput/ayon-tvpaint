import re

from ayon_core.pipeline import LoaderPlugin
from ayon_core.pipeline.create import (
    CreatedInstance,
    get_product_name,
    AutoCreator,
    Creator,
)
from ayon_core.pipeline.create.creator_plugins import cache_and_get_instances

from .lib import get_layers_data


SHARED_DATA_KEY = "ayon.tvpaint.instances"


class TVPaintCreatorCommon:
    @property
    def product_template_product_type(self):
        return self.product_type

    def _cache_and_get_instances(self):
        return cache_and_get_instances(
            self, SHARED_DATA_KEY, self.host.list_instances
        )

    def _collect_create_instances(self):
        instances_by_identifier = self._cache_and_get_instances()
        for instance_data in instances_by_identifier[self.identifier]:
            instance = CreatedInstance.from_existing(instance_data, self)
            self._add_instance_to_context(instance)

    def _update_create_instances(self, update_list):
        if not update_list:
            return

        cur_instances = self.host.list_instances()
        cur_instances_by_id = {}
        for instance_data in cur_instances:
            instance_id = instance_data.get("instance_id")
            if instance_id:
                cur_instances_by_id[instance_id] = instance_data

        for instance, changes in update_list:
            instance_data = changes.new_value
            cur_instance_data = cur_instances_by_id.get(instance.id)
            if cur_instance_data is None:
                cur_instances.append(instance_data)
                continue
            for key in set(cur_instance_data) - set(instance_data):
                cur_instance_data.pop(key)
            cur_instance_data.update(instance_data)
        self.host.write_instances(cur_instances)

    def _custom_get_product_name(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        host_name=None,
        instance=None
    ):
        dynamic_data = self.get_dynamic_data(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
            instance
        )
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]

        return get_product_name(
            project_name,
            task_name,
            task_type,
            host_name,
            self.product_type,
            variant,
            dynamic_data=dynamic_data,
            project_settings=self.project_settings,
            product_type_filter=self.product_template_product_type
        )


class TVPaintCreator(Creator, TVPaintCreatorCommon):
    settings_category = "tvpaint"

    def collect_instances(self):
        self._collect_create_instances()

    def update_instances(self, update_list):
        self._update_create_instances(update_list)

    def remove_instances(self, instances):
        ids_to_remove = {
            instance.id
            for instance in instances
        }
        cur_instances = self.host.list_instances()
        changed = False
        new_instances = []
        for instance_data in cur_instances:
            if instance_data.get("instance_id") in ids_to_remove:
                changed = True
            else:
                new_instances.append(instance_data)

        if changed:
            self.host.write_instances(new_instances)

        for instance in instances:
            self._remove_instance_from_context(instance)

    def get_dynamic_data(self, *args, **kwargs):
        # Change folder and name by current workfile context
        create_context = self.create_context
        folder_path = create_context.get_current_folder_path()
        task_name = create_context.get_current_task_name()
        output = {}
        if folder_path:
            folder_name = folder_path.rsplit("/")[-1]
            output["asset"] = folder_name
            output["folder"] = {"name": folder_name}
            if task_name:
                output["task"] = task_name
        return output

    def get_product_name(self, *args, **kwargs):
        return self._custom_get_product_name(*args, **kwargs)

    def _store_new_instance(self, new_instance):
        instances_data = self.host.list_instances()
        instances_data.append(new_instance.data_to_store())
        self.host.write_instances(instances_data)
        self._add_instance_to_context(new_instance)


class TVPaintAutoCreator(AutoCreator, TVPaintCreatorCommon):
    settings_category = "tvpaint"

    def collect_instances(self):
        self._collect_create_instances()

    def update_instances(self, update_list):
        self._update_create_instances(update_list)

    def get_product_name(self, *args, **kwargs):
        return self._custom_get_product_name(*args, **kwargs)


class Loader(LoaderPlugin):
    hosts = ["tvpaint"]
    settings_category = "tvpaint"

    @staticmethod
    def get_members_from_container(container):
        if "members" not in container and "objectName" in container:
            # Backwards compatibility
            layer_ids_str = container.get("objectName")
            return [
                int(layer_id) for layer_id in layer_ids_str.split("|")
            ]
        return container["members"]

    def get_unique_layer_name(self, namespace, name):
        """Layer name with counter as suffix.

        Find higher 3 digit suffix from all layer names in scene matching regex
        `{namespace}_{name}_{suffix}`. Higher 3 digit suffix is used
        as base for next number if scene does not contain layer matching regex
        `0` is used ase base.

        Args:
            namespace (str): Usually folder name.
            name (str): Name of loaded product.

        Returns:
            str: `{namespace}_{name}_{higher suffix + 1}`
        """
        layer_name_base = "{}_{}".format(namespace, name)

        counter_regex = re.compile(r"_(\d{3})$")

        higher_counter = 0
        for layer in get_layers_data():
            layer_name = layer["name"]
            if not layer_name.startswith(layer_name_base):
                continue
            number_subpart = layer_name[len(layer_name_base):]
            groups = counter_regex.findall(number_subpart)
            if len(groups) != 1:
                continue

            counter = int(groups[0])
            if counter > higher_counter:
                higher_counter = counter
                continue

        return "{}_{:0>3d}".format(layer_name_base, higher_counter + 1)
