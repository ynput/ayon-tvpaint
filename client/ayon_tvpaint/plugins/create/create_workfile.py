from ayon_core.pipeline import CreatedInstance
from ayon_tvpaint.api.plugin import TVPaintAutoCreator


class TVPaintWorkfileCreator(TVPaintAutoCreator):
    product_type = "workfile"
    identifier = "workfile"
    label = "Workfile"
    icon = "fa.file-o"

    def apply_settings(self, project_settings):
        plugin_settings = (
            project_settings["tvpaint"]["create"]["create_workfile"]
        )
        self.default_variant = plugin_settings["default_variant"]
        self.default_variants = plugin_settings["default_variants"]

    def create(self):
        existing_instance = None
        for instance in self.create_context.instances:
            if instance.creator_identifier == self.identifier:
                existing_instance = instance
                break

        if existing_instance is not None:
            self._update_instance_context(existing_instance)
            return

        project_entity = self.create_context.get_current_project_entity()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()
        product_name = self.get_product_name(
            project_entity["name"],
            folder_entity,
            task_entity,
            self.default_variant,
            self.create_context.host_name,
            project_entity=project_entity,
        )
        data = {
            "folderPath": folder_entity["path"],
            "task": task_entity["name"],
            "variant": self.default_variant
        }

        new_instance = CreatedInstance(
            self.product_type, product_name, data, self
        )
        instances_data = self.host.list_instances()
        instances_data.append(new_instance.data_to_store())
        self.host.write_instances(instances_data)
        self._add_instance_to_context(new_instance)
