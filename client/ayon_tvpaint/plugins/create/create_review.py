from ayon_core.pipeline import CreatedInstance
from ayon_tvpaint.api.plugin import TVPaintAutoCreator


class TVPaintReviewCreator(TVPaintAutoCreator):
    product_type = "review"
    product_base_type = "review"
    identifier = "scene.review"
    label = "Review"
    icon = "ei.video"

    settings_name = "create_review"

    # Settings
    active_on_create = True

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
            project_name=project_entity["name"],
            folder_entity=folder_entity,
            task_entity=task_entity,
            variant=self.default_variant,
            host_name=self.create_context.host_name,
            project_entity=project_entity,
        )
        data = {
            "folderPath": folder_entity["path"],
            "task": task_entity["name"],
            "variant": self.default_variant,
        }

        if not self.active_on_create:
            data["active"] = False

        new_instance = CreatedInstance(
            self.product_base_type,
            product_name,
            data,
            self,
        )
        instances_data = self.host.list_instances()
        instances_data.append(new_instance.data_to_store())
        self.host.write_instances(instances_data)
        self._add_instance_to_context(new_instance)
