import pyblish.api

from ayon_core.lib import version_up
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

        host = registered_host()
        path = context.data["currentFile"]
        host.save_workfile(version_up(path))
        self.log.info('Incrementing workfile version')
