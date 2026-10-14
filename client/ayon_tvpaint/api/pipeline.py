import os
import json
import logging

import requests
import ayon_api
import pyblish.api

from ayon_tvpaint import TVPAINT_ROOT_DIR

from ayon_core.host import (
    HostBase,
    IWorkfileHost,
    ILoadHost,
    IPublishHost,
    ContextChangeData,
    ContextChangeReason,
)
from ayon_core.host.interfaces import get_open_workfile_context
from ayon_core.settings import get_current_project_settings
from ayon_core.lib import register_event_callback
from ayon_core.pipeline import (
    register_loader_plugin_path,
    register_creator_plugin_path,
    AYON_CONTAINER_ID,
)
from ayon_core.pipeline.context_tools import get_global_context

from .lib import (
    execute_george,
    execute_george_batch,
    george_path,
    george_string,
)
from .communication_server import CommunicationWrapper, MainThreadItem

log = logging.getLogger(__name__)


METADATA_SECTION = "avalon"
SECTION_NAME_CONTEXT = "context"
SECTION_NAME_CREATE_CONTEXT = "create_context"
SECTION_NAME_INSTANCES = "instances"
SECTION_NAME_CONTAINERS = "containers"
# Maximum length of metadata chunk string
# TODO find out the max (500 is safe enough)
TVPAINT_CHUNK_LENGTH = 500

"""TVPaint's Metadata

Metadata are stored to TVPaint's workfile.

Workfile works similar to .ini file but has few limitation. Most important
limitation is that value under key has limited length. Due to this limitation
each metadata section/key stores number of "subkeys" that are related to
the section.

Example:
Metadata key `"instances"` may have stored value "2". In that case it is
expected that there are also keys `["instances0", "instances1"]`.

Workfile data looks like:
```
[avalon]
instances0=[{{__dq__}id{__dq__}: {__dq__}ayon.create.instance{__dq__...
instances1=...more data...
instances=2
```
"""


class TVPaintHost(HostBase, IWorkfileHost, ILoadHost, IPublishHost):
    name = "tvpaint"

    def install(self):
        """Install TVPaint-specific functionality."""

        log.info("AYON - Installing TVPaint integration")

        # Create workdir folder if does not exist yet
        workdir = os.getenv("AYON_WORKDIR")
        if not os.path.exists(workdir):
            os.makedirs(workdir)

        plugins_dir = os.path.join(TVPAINT_ROOT_DIR, "plugins")
        publish_dir = os.path.join(plugins_dir, "publish")
        load_dir = os.path.join(plugins_dir, "load")
        create_dir = os.path.join(plugins_dir, "create")

        pyblish.api.register_host("tvpaint")
        pyblish.api.register_plugin_path(publish_dir)
        register_loader_plugin_path(load_dir)
        register_creator_plugin_path(create_dir)

        register_event_callback("application.launched", self.initial_launch)
        register_event_callback("application.exit", self.application_exit)
        register_event_callback(
            "workfile.open.after",
            self._on_workfile_open_after
        )

    def get_current_project_name(self):
        """
        Returns:
            Union[str, None]: Current project name.
        """

        return self.get_current_context().get("project_name")

    def get_current_folder_path(self):
        """
        Returns:
            Union[str, None]: Current folder path.
        """

        return self.get_current_context().get("folder_path")

    def get_current_task_name(self):
        """
        Returns:
            Union[str, None]: Current task name.
        """

        return self.get_current_context().get("task_name")

    def get_current_context(self):
        context = get_current_workfile_context()
        if not context:
            return get_global_context()

        if "project_name" in context:
            if "asset_name" in context:
                context["folder_path"] = context["asset_name"]
            return context
        # This is legacy way how context was stored
        return {
            "project_name": context.get("project"),
            "folder_path": context.get("asset"),
            "task_name": context.get("task")
        }

    # --- Create ---
    def get_context_data(self):
        return get_workfile_metadata(SECTION_NAME_CREATE_CONTEXT, {})

    def update_context_data(self, data, changes):
        return write_workfile_metadata(SECTION_NAME_CREATE_CONTEXT, data)

    def list_instances(self):
        """List all created instances from current workfile."""
        return list_instances()

    def write_instances(self, data):
        return write_instances(data)

    # --- Workfile ---
    def open_workfile(self, filepath):
        return execute_george(
            f"tv_LoadProject {george_string(george_path(filepath))}"
        )

    def open_workfile_in_context(
        self, filepath, project_name, folder_entity, task_entity
    ):
        """Open workfile in context which can be of a different project.

        Current context of TVPaint is stored in workfile metadata, so the
        project changes once the opened workfile has the context stored.
        Mirrors 'open_workfile_with_context' which always uses the current
        project.

        Args:
            filepath (str): Path to workfile.
            project_name (str): Project name.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.

        """
        open_workfile_context = get_open_workfile_context(
            project_name,
            filepath,
            folder_entity,
            task_entity,
            prepared_data=None,
        )
        folder_path = folder_entity["path"]
        task_name = task_entity["name"]

        os.environ["AYON_WORKDIR"] = os.path.dirname(filepath)
        event_data = self._get_workfile_event_data(
            project_name, folder_entity, task_entity, filepath
        )
        self._before_workfile_open(open_workfile_context)
        self._emit_workfile_open_event(event_data, after_open=False)

        self.open_workfile(filepath)

        # Context of the opened workfile becomes the current context
        save_current_workfile_context({
            "project_name": project_name,
            "folder_path": folder_path,
            "task_name": task_name,
        })
        context_change_data = ContextChangeData(
            project_entity=open_workfile_context.project_entity,
            folder_entity=folder_entity,
            task_entity=task_entity,
            reason=ContextChangeReason.workfile_open,
            anatomy=open_workfile_context.anatomy,
        )
        self._before_context_change(context_change_data)
        # Also updates environment variables from the current context
        self._set_current_context(context_change_data)
        self._after_context_change(context_change_data)
        self._emit_context_change_event(project_name, folder_path, task_name)

        self._after_workfile_open(open_workfile_context)
        self._emit_workfile_open_event(event_data)

    def save_workfile(self, filepath=None):
        if not filepath:
            filepath = self.get_current_workfile()
        context = get_global_context()
        save_current_workfile_context(context)

        # Execute george script to save workfile.
        george_script = "tv_SaveProject {}".format(filepath.replace("\\", "/"))
        return execute_george(george_script)

    def work_root(self, session):
        return session["AYON_WORKDIR"]

    def get_current_workfile(self):
        # TVPaint returns a '\' character when no scene is currently opened
        current_workfile = execute_george("tv_GetProjectName")
        if current_workfile == '\\':
            return None
        return current_workfile

    def workfile_has_unsaved_changes(self):
        return None

    def get_workfile_extensions(self):
        return [".tvpp"]

    # --- Load ---
    def get_containers(self):
        return get_containers()

    def initial_launch(self):
        self._set_workfile_attributes()

    def _set_workfile_attributes(self):
        # Setup project context
        # - if was used e.g. template the context might be invalid.
        filepath = self.get_current_workfile()
        if not filepath:
            return

        log.info("Setting up context...")
        global_context = get_global_context()
        project_name = global_context.get("project_name")
        if not project_name:
            return

        save_current_workfile_context(global_context)

        folder_path = global_context.get("folder_path")
        task_name = global_context.get("task_name")

        if not folder_path:
            return

        folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
        if folder_entity and task_name:
            task_entity = ayon_api.get_task_by_name(
                project_name,
                folder_id=folder_entity["id"],
                task_name=task_name)
            context_entity = task_entity
        else:
            log.warning(
                "Falling back to setting context settings using folder entity "
                "because no task was found.")
            context_entity = folder_entity

        set_context_settings(context_entity, filepath)

    def application_exit(self):
        """Logic related to TimerManager.

        Todo:
            This should be handled out of TVPaint integration logic.
        """

        data = get_current_project_settings()
        stop_timer = data["tvpaint"]["stop_timer_on_application_exit"]

        if not stop_timer:
            return

        # Stop application timer.
        webserver_url = os.environ.get("AYON_WEBSERVER_URL")
        rest_api_url = "{}/timers_manager/stop_timer".format(webserver_url)
        requests.post(rest_api_url)

    def _on_workfile_open_after(self):
        # Make sure opened workfile has stored correct context
        global_context = get_global_context()
        save_current_workfile_context(global_context)
        communicator = CommunicationWrapper.communicator
        if hasattr(communicator, "execute_in_main_thread"):
            communicator.execute_in_main_thread(
                MainThreadItem(self._set_workfile_attributes),
                False
            )


def containerise(
    name, namespace, members, context, loader, current_containers=None
):
    """Add new container to metadata.

    Args:
        name (str): Container name.
        namespace (str): Container namespace.
        members (list): List of members that were loaded and belongs
            to the container (layer names).
        current_containers (list): Preloaded containers. Should be used only
            on update/switch when containers were modified during the process.

    Returns:
        dict: Container data stored to workfile metadata.
    """

    container_data = {
        "members": members,
        "name": name,
        "namespace": namespace,
        "loader": str(loader),
        "representation": context["representation"]["id"],
        "project_name": context["project"]["name"]
    }
    if current_containers is None:
        current_containers = get_containers()

    # Add container to containers list
    current_containers.append(container_data)

    # Store data to metadata
    write_workfile_metadata(SECTION_NAME_CONTAINERS, current_containers)

    return container_data


def split_metadata_string(text, chunk_length=None):
    """Split string by length.

    Split text to chunks by entered length.
    Example:
        ```python
        text = "ABCDEFGHIJKLM"
        result = split_metadata_string(text, 3)
        print(result)
        >>> ['ABC', 'DEF', 'GHI', 'JKL']
        ```

    Args:
        text (str): Text that will be split into chunks.
        chunk_length (int): Single chunk size. Default chunk_length is
            set to global variable `TVPAINT_CHUNK_LENGTH`.

    Returns:
        list: List of strings with at least one item.
    """
    if chunk_length is None:
        chunk_length = TVPAINT_CHUNK_LENGTH
    chunks = []
    for idx in range(chunk_length, len(text) + chunk_length, chunk_length):
        start_idx = idx - chunk_length
        chunks.append(text[start_idx:idx])
    return chunks


def get_workfile_metadata_string_for_keys(metadata_keys):
    """Read metadata for specific keys from current project workfile.

    All values from entered keys are stored to single string without separator.

    Function is designed to help get all values for one metadata key at once.
    So order of passed keys matteres.

    Args:
        metadata_keys (list, str): Metadata keys for which data should be
            retrieved. Order of keys matters! It is possible to enter only
            single key as string.
    """
    # Add ability to pass only single key
    if isinstance(metadata_keys, str):
        metadata_keys = [metadata_keys]

    section = george_string(METADATA_SECTION)
    outputs = execute_george_batch(
        f'tv_ReadProjectString {section} {george_string(metadata_key)} ""'
        for metadata_key in metadata_keys
    )
    return "".join(outputs)


def get_workfile_metadata_string(metadata_key):
    """Read metadata for specific key from current project workfile."""
    result = get_workfile_metadata_string_for_keys([metadata_key])
    if not result:
        return None

    stripped_result = result.strip()
    if not stripped_result:
        return None

    # NOTE Backwards compatibility when metadata key did not store range of key
    #   indexes but the value itself
    # NOTE We don't have to care about negative values with `isdecimal` check
    if not stripped_result.isdecimal():
        metadata_string = result
    else:
        keys = []
        for idx in range(int(stripped_result)):
            keys.append("{}{}".format(metadata_key, idx))
        metadata_string = get_workfile_metadata_string_for_keys(keys)

    # Replace quotes plaholders with their values
    metadata_string = (
        metadata_string
        .replace("{__sq__}", "'")
        .replace("{__dq__}", "\"")
    )
    return metadata_string


def get_workfile_metadata(metadata_key, default=None):
    """Read and parse metadata for specific key from current project workfile.

    Pipeline use function to store loaded and created instances within keys
    stored in `SECTION_NAME_INSTANCES` and `SECTION_NAME_CONTAINERS`
    constants.

    Args:
        metadata_key (str): Key defying which key should read. It is expected
            value contain json serializable string.
    """
    if default is None:
        default = []

    json_string = get_workfile_metadata_string(metadata_key)
    if json_string:
        try:
            return json.loads(json_string)
        except json.decoder.JSONDecodeError:
            # TODO remove when backwards compatibility of storing metadata
            # will be removed
            print((
                "Fixed invalid metadata in workfile."
                " Not serializable string was: {}"
            ).format(json_string))
            write_workfile_metadata(metadata_key, default)
    return default


def write_workfile_metadata(metadata_key, value):
    """Write metadata for specific key into current project workfile.

    George script has specific way how to work with quotes which should be
    solved automatically with this function.

    Args:
        metadata_key (str): Key defying under which key value will be stored.
        value (dict,list,str): Data to store they must be json serializable.
    """
    if isinstance(value, (dict, list)):
        value = json.dumps(value)

    if not value:
        value = ""

    # Handle quotes in dumped json string
    # - replace single and double quotes with placeholders
    value = (
        value
        .replace("'", "{__sq__}")
        .replace("\"", "{__dq__}")
    )
    chunks = split_metadata_string(value)
    chunks_len = len(chunks)

    section = george_string(METADATA_SECTION)
    # Add information about chunks length to metadata key itself
    commands = [
        f"tv_WriteProjectString {section}"
        f" {george_string(metadata_key)} {george_string(chunks_len)}"
    ]
    # Add chunk values to indexed metadata keys
    for idx, chunk_value in enumerate(chunks):
        sub_key = f"{metadata_key}{idx}"
        commands.append(
            f"tv_WriteProjectString {section}"
            f" {george_string(sub_key)} {george_string(chunk_value)}"
        )

    execute_george_batch(commands)


def get_current_workfile_context():
    """Return context in which was workfile saved."""
    return get_workfile_metadata(SECTION_NAME_CONTEXT, {})


def save_current_workfile_context(context):
    """Save context which was used to create a workfile."""
    return write_workfile_metadata(SECTION_NAME_CONTEXT, context)


def list_instances():
    """List all created instances from current workfile."""
    return get_workfile_metadata(SECTION_NAME_INSTANCES)


def write_instances(data):
    return write_workfile_metadata(SECTION_NAME_INSTANCES, data)


def get_containers():
    output = get_workfile_metadata(SECTION_NAME_CONTAINERS)
    if output:
        for item in output:
            item["schema"] = "ayon:container-3.0"
            item["id"] = AYON_CONTAINER_ID
            if "objectName" not in item and "members" in item:
                members = item["members"]
                if isinstance(members, list):
                    members = "|".join([str(member) for member in members])
                item["objectName"] = members
    return output


def set_context_settings(context_entity, filepath):
    """Set workfile settings by folder entity attributes.

    Change fps, resolution and frame start/end.

    Args:
        context_entity (dict[str, Any]): Task or folder entity.
        filepath (str): Current workfile.

    """
    if not context_entity:
        return

    attributes = context_entity["attrib"]

    width = attributes.get("resolutionWidth")
    height = attributes.get("resolutionHeight")
    if width is None or height is None:
        print("Resolution was not found!")
    else:
        current_width = int(execute_george("tv_getwidth"))
        current_height = int(execute_george("tv_getheight"))
        if current_width != width or current_height != height:
            message = (
                f"Expected project resolution is {width}x{height}"
                f" but current is {current_width}x{current_height}."
                "\nDo you want to resize the project?"
                "\nWARNING: This step will resize content of the project."
                "|Yes|No"
            )
            result = execute_george(f"tv_request {message}")
            if result == "1":
                p1, p2 = os.path.splitext(filepath)
                idx = 0
                while True:
                    bckup_path = f"{p1}_backup{idx}{p2}"
                    if not os.path.exists(bckup_path):
                        break
                    idx += 1
                bckup_path = bckup_path.replace("\\", "/")
                filepath = filepath.replace("\\", "/")
                execute_george(f"tv_saveproject {bckup_path}")
                execute_george(f"tv_resizepage {width} {height} 1")
                execute_george(f"tv_saveproject {filepath}")

    framerate = attributes.get("fps")

    if framerate is None:
        print("Framerate was not found!")
    else:
        execute_george(
            f"tv_framerate {framerate} \"timestretch\""
        )

    frame_start = attributes.get("frameStart")
    frame_end = attributes.get("frameEnd")

    if frame_start is None or frame_end is None:
        print("Frame range was not found!")
        return

    handle_start = attributes.get("handleStart") or 0
    handle_end = attributes.get("handleEnd") or 0

    # Use current Mark In and set only Mark Out
    mark_in_frame, _mark_in_state, _ = execute_george("tv_markin").split(" ")
    mark_in = int(mark_in_frame)
    mark_out = mark_in + (frame_end - frame_start) + handle_start + handle_end

    execute_george(f"tv_markin {mark_in} set")
    execute_george(f"tv_markout {mark_out} set")
