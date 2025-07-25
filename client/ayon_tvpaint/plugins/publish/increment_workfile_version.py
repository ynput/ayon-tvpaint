import os

import pyblish.api

from ayon_core.lib import version_up
from ayon_core.host import IWorkfileHost
from ayon_core.pipeline import registered_host


class IncrementWorkfileVersion(pyblish.api.ContextPlugin):
    """Increment current workfile version."""

    order = pyblish.api.IntegratorOrder + 1
    label = "Increment Workfile Version"
    optional = True
    hosts = ["tvpaint"]

    settings_category = "tvpaint"

    def process(self, context):

        assert all(result["success"] for result in context.data["results"]), (
            "Publishing not successful so version is not increased.")

        host: IWorkfileHost = registered_host()
        current_filepath: str = context.data["currentFile"]
        try:
            from ayon_core.pipeline.workfile import save_next_version
            from ayon_core.host.interfaces import SaveWorkfileOptionalData

            current_filename = os.path.basename(current_filepath)
            save_next_version(
                description=(
                    f"Incremented by publishing from {current_filename}"
                ),
                # Optimize the save by reducing needed queries for context
                prepared_data=SaveWorkfileOptionalData(
                    project_entity=context.data["projectEntity"],
                    project_settings=context.data["project_settings"],
                    anatomy=context.data["anatomy"],
                )
            )
            new_filepath = host.get_current_workfile()
        except ImportError:
            # Backwards compatibility before ayon-core 1.5.0
            self.log.debug(
                "Using legacy `version_up`. Update AYON core addon to "
                "use newer `save_next_version` function."
            )
            new_filepath = version_up(current_filepath)
            host.save_workfile(new_filepath)

        self.log.debug(f"Incrementing workfile version to: {new_filepath}")
