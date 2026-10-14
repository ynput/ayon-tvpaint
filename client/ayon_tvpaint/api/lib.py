"""George commands

Commands are sent to TVPaint one by one, each must be a single line. George
script features like variables, 'PARSE' or loops are not available, the
logic is done in python. Use 'execute_george_batch' to execute multiple
commands at once.

Arguments of george commands are parsed differently by each command:
- file path of 'tv_SaveProject' and 'tv_SaveImage' is the rest of the line,
    it must not be quoted
- other strings (names, paths in 'tv_LoadProject', 'tv_LoadSequence', ...)
    must be wrapped with double quotes, use 'george_string'
- keywords like 'set' in 'tv_LayerColor' must not be quoted
- it is not possible to pass double quotes inside of a string
"""

import logging

from .communication_server import CommunicationWrapper

log = logging.getLogger(__name__)


def george_string(value):
    """Wrap value into double quotes to be passed as one george argument.

    Args:
        value (Any): Value to pass, converted to string.

    Returns:
        str: Value in double quotes.

    Raises:
        ValueError: Value can't be passed to george command.

    """
    value = str(value)
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError(
            f"George string can't contain double quotes or new lines: {value}"
        )
    return f'"{value}"'


def george_path(path):
    """Path with forward slashes, TVPaint can't handle backslashes."""
    return path.replace("\\", "/")


def execute_george(george_script, communicator=None):
    """Execute single line george command.

    Args:
        george_script (str): George command.
        communicator (Optional[BaseCommunicator]): Communicator.

    Returns:
        Optional[str]: Output of the command.

    """
    if not communicator:
        communicator = CommunicationWrapper.communicator
    return communicator.execute_george(george_script)


def execute_george_batch(commands, communicator=None):
    """Execute multiple single line george commands.

    All commands are executed during a single TVPaint tick, so nothing
    happens between them.

    Args:
        commands (Iterable[str]): George commands.
        communicator (Optional[BaseCommunicator]): Communicator.

    Returns:
        list[str]: Output of each command.

    """
    if not communicator:
        communicator = CommunicationWrapper.communicator
    outputs = communicator.execute_george_batch(commands)
    if outputs is None:
        return []
    return outputs


def execute_george_through_file(george_script, communicator=None):
    """Execute george script with temp file.

    Deprecated:
        Use 'execute_george' or 'execute_george_batch' instead.

    On windows make sure script does not contain paths with backwards
    slashes in paths, TVPaint won't execute properly in that case.

    Args:
        george_script (str): George script to execute. May be multilined.
    """
    if not communicator:
        communicator = CommunicationWrapper.communicator

    return communicator.execute_george_through_file(george_script)


def get_layer_ids(communicator=None):
    """Ids of all layers in current clip.

    Returns:
        list[int]: Layer ids in order of layers.

    """
    if not communicator:
        communicator = CommunicationWrapper.communicator
    return communicator.get_layer_ids() or []


def _unquote(value):
    if len(value) > 1 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_layer_info(layer_id, group_id, layer_info, current_layer_id):
    """Parse output of 'tv_LayerInfo' to layer data.

    Args:
        layer_id (int): Layer id.
        group_id (str): Output of 'tv_LayerColor get'.
        layer_info (str): Output of 'tv_LayerInfo'.
        current_layer_id (str): Output of 'tv_LayerCurrentID'.

    Returns:
        dict[str, Any]: Layer data.

    """
    # Example: 'ON 0 0 "layer name" Sequence 0 10 0 0 0 1 OFF'
    # - name is in quotes and can contain spaces
    visible, position, _opacity, rest = layer_info.split(" ", 3)
    (
        name,
        layer_type,
        frame_start,
        frame_end,
        prelighttable,
        postlighttable,
        selected,
        editable,
        sencil_state,
    ) = rest.rsplit(" ", 8)
    is_current = str(layer_id) == current_layer_id.strip()
    return {
        "layer_id": int(layer_id),
        "group_id": int(group_id),
        "visible": visible == "ON",
        "position": int(position),
        # Opacity from 'tv_layerinfo' is always set to '0' so it's unusable
        # "opacity": int(opacity),
        "name": _unquote(name),
        "type": layer_type,
        "frame_start": int(frame_start),
        "frame_end": int(frame_end),
        "prelighttable": prelighttable == "1",
        "postlighttable": postlighttable == "1",
        # Current layer is always selected
        "selected": selected == "1" or is_current,
        "editable": editable == "1",
        "sencil_state": sencil_state,
        "is_current": is_current,
    }


def parse_layers_data(data):
    """Parse layers data in format of old george script.

    Deprecated:
        Data are not stored to a file anymore, use 'get_layers_data'.

    """
    layers = []
    layers_raw = data.split("\n")
    for layer_raw in layers_raw:
        layer_raw = layer_raw.strip()
        if not layer_raw:
            continue
        (
            layer_id, group_id, visible, position, _opacity, name,
            layer_type,
            frame_start, frame_end, prelighttable, postlighttable,
            selected, editable, sencil_state, is_current
        ) = layer_raw.split("|")
        layer = {
            "layer_id": int(layer_id),
            "group_id": int(group_id),
            "visible": visible == "ON",
            "position": int(position),
            "name": name,
            "type": layer_type,
            "frame_start": int(frame_start),
            "frame_end": int(frame_end),
            "prelighttable": prelighttable == "1",
            "postlighttable": postlighttable == "1",
            "selected": selected == "1",
            "editable": editable == "1",
            "sencil_state": sencil_state,
            "is_current": is_current == "1"
        }
        layers.append(layer)
    return layers


def layers_data(layer_ids=None, communicator=None):
    """Backwards compatible function of 'get_layers_data'."""
    return get_layers_data(layer_ids, communicator)


def get_layers_data(layer_ids=None, communicator=None):
    """Collect layers information from currently opened workfile.

    Args:
        layer_ids (Optional[Union[int, Iterable[int]]]): Layers to get, all
            layers are returned if not passed. Missing layers are skipped.
        communicator (Optional[BaseCommunicator]): Communicator.

    Returns:
        list[dict[str, Any]]: Layers data.

    """
    if layer_ids is None:
        layer_ids = get_layer_ids(communicator)
    elif isinstance(layer_ids, int):
        layer_ids = [layer_ids]
    layer_ids = list(layer_ids)

    commands = ["tv_LayerCurrentID"]
    for layer_id in layer_ids:
        commands.append(f"tv_LayerColor get {layer_id}")
        commands.append(f"tv_LayerInfo {layer_id}")
    outputs = execute_george_batch(commands, communicator)
    if not outputs:
        return []

    current_layer_id = outputs[0]
    layers = []
    for idx, layer_id in enumerate(layer_ids):
        group_id = outputs[1 + idx * 2]
        layer_info = outputs[2 + idx * 2]
        # Layer does not exist
        if not layer_info:
            continue
        layers.append(
            parse_layer_info(layer_id, group_id, layer_info, current_layer_id)
        )
    return layers


def parse_group_data(data):
    """Parse group data in format of old george script.

    Deprecated:
        Data are not stored to a file anymore, use 'get_groups_data'.

    """
    output = []
    groups_raw = data.split("\n")
    for group_raw in groups_raw:
        group_raw = group_raw.strip()
        if not group_raw:
            continue

        parts = group_raw.split("|")
        # Check for length and concatenate 2 last items until length match
        # - this happens if name contain spaces
        while len(parts) > 6:
            last_item = parts.pop(-1)
            parts[-1] = "|".join([parts[-1], last_item])
        clip_id, group_id, red, green, blue, name = parts

        group = {
            "group_id": int(group_id),
            "name": name,
            "clip_id": int(clip_id),
            "red": int(red),
            "green": int(green),
            "blue": int(blue),
        }
        output.append(group)
    return output


def parse_group_color(group_color):
    """Parse output of 'tv_LayerColor getcolor' to group data.

    Returns:
        Optional[dict[str, Any]]: Group data, None if output is invalid.

    """
    # Example: '0 1 250 0 0 "group name"'
    parts = group_color.strip().split(" ", 5)
    if len(parts) != 6:
        return None
    clip_id, group_id, red, green, blue, name = parts
    return {
        "group_id": int(group_id),
        "name": _unquote(name),
        "clip_id": int(clip_id),
        "red": int(red),
        "green": int(green),
        "blue": int(blue),
    }


def groups_data(communicator=None):
    """Backwards compatible function of 'get_groups_data'."""
    return get_groups_data(communicator)


def get_groups_data(communicator=None):
    """Information about groups from current workfile."""
    # There are 26 groups which is ATM maximum possible (in 11.7)
    # - ref: https://www.tvpaint.com/forum/viewtopic.php?t=13880
    outputs = execute_george_batch(
        [f"tv_LayerColor getcolor 0 {idx}" for idx in range(1, 27)],
        communicator
    )
    output = []
    for group_color in outputs:
        group = parse_group_color(group_color)
        if group is not None:
            output.append(group)
    return output


def get_layers_pre_post_behavior(layer_ids, communicator=None):
    """Collect data about pre and post behavior of layer ids.

    Pre and Post behaviors is enumerator of possible values:
    - "none"
    - "repeat"
    - "pingpong"
    - "hold"

    Example output:
    ```json
    {
        0: {
            "pre": "none",
            "post": "repeat"
        }
    }
    ```

    Returns:
        dict: Key is layer id value is dictionary with "pre" and "post" keys.
    """
    # Skip if is empty
    if not layer_ids:
        return {}

    # Auto convert to list
    if not isinstance(layer_ids, (list, set, tuple)):
        layer_ids = [layer_ids]
    layer_ids = list(layer_ids)

    commands = []
    for layer_id in layer_ids:
        commands.append(f"tv_LayerPreBehavior {layer_id}")
        commands.append(f"tv_LayerPostBehavior {layer_id}")
    outputs = execute_george_batch(commands, communicator)

    output = {}
    for idx, layer_id in enumerate(layer_ids):
        pre_beh = outputs[idx * 2]
        post_beh = outputs[idx * 2 + 1]
        # Layer does not exist
        if pre_beh.upper().startswith("ERROR"):
            continue
        output[int(layer_id)] = {
            "pre": pre_beh.lower(),
            "post": post_beh.lower()
        }
    return output


def _get_exposure_frames(frame_ranges_by_layer_id, communicator=None):
    """Find exposure frames of layers.

    Exposure is read from current layer, so layers are made current one by
    one. Current layer is restored at the end.

    Args:
        frame_ranges_by_layer_id (dict[int, tuple[int, int]]): First and
            last frame by layer id.
        communicator (Optional[BaseCommunicator]): Communicator.

    Returns:
        dict[int, list[int]]: Frames where exposure is set to "Head".

    """
    current_layer_id = execute_george("tv_LayerCurrentID", communicator)
    commands = []
    frames_by_layer_id = {}
    for layer_id, (first_frame, last_frame) in (
        frame_ranges_by_layer_id.items()
    ):
        commands.append(f"tv_LayerSet {layer_id}")
        frames = list(range(first_frame, last_frame + 1))
        frames_by_layer_id[layer_id] = (len(commands), frames)
        commands.extend(f"tv_ExposureInfo {frame}" for frame in frames)

    if current_layer_id:
        commands.append(f"tv_LayerSet {current_layer_id}")
    outputs = execute_george_batch(commands, communicator)

    output = {}
    for layer_id, (start_idx, frames) in frames_by_layer_id.items():
        output[layer_id] = [
            frame
            for frame, exposure in zip(frames, outputs[start_idx:])
            if exposure == "Head"
        ]
    return output


def get_layers_exposure_frames(layer_ids, layers_data=None, communicator=None):
    """Get exposure frames.

    Easily said returns frames where keyframes are. Recognized with george
    function `tv_exposureinfo` returning "Head".

    Args:
        layer_ids (list): Ids of a layers for which exposure frames should
            look for.
        layers_data (list): Precollected layers data. If are not passed then
            'get_layers_data' is used.
        communicator (BaseCommunicator): Communicator used for communication
            with TVPaint.

    Returns:
        dict: Frames where exposure is set to "Head" by layer id.
    """

    if layers_data is None:
        layers_data = get_layers_data(layer_ids, communicator)
    layers_by_id = {
        layer["layer_id"]: layer
        for layer in layers_data
    }

    output = {layer_id: [] for layer_id in layer_ids}
    frame_ranges_by_layer_id = {}
    for layer_id in layer_ids:
        layer = layers_by_id.get(layer_id)
        if layer:
            frame_ranges_by_layer_id[layer_id] = (
                layer["frame_start"], layer["frame_end"]
            )
    output.update(
        _get_exposure_frames(frame_ranges_by_layer_id, communicator)
    )
    return output


def get_exposure_frames(
    layer_id, first_frame=None, last_frame=None, communicator=None
):
    """Get exposure frames.

    Easily said returns frames where keyframes are. Recognized with george
    function `tv_exposureinfo` returning "Head".

    Args:
        layer_id (int): Id of a layer for which exposure frames should
            look for.
        first_frame (int): From which frame will look for exposure frames.
            Used layers first frame if not entered.
        last_frame (int): Last frame where will look for exposure frames.
            Used layers last frame if not entered.

    Returns:
        list: Frames where exposure is set to "Head".
    """
    if first_frame is None or last_frame is None:
        layer = layers_data(layer_id, communicator)[0]
        if first_frame is None:
            first_frame = layer["frame_start"]
        if last_frame is None:
            last_frame = layer["frame_end"]

    output = _get_exposure_frames(
        {layer_id: (first_frame, last_frame)}, communicator
    )
    return output[layer_id]


def get_scene_data(communicator=None):
    """Scene data of currently opened scene.

    Result contains resolution, pixel aspect, fps mark in/out with states,
    frame start and background color.

    Returns:
        dict: Scene data collected in many ways.
    """
    (
        workfile_info,
        mark_in_result,
        mark_out_result,
        start_frame,
        bg_color,
    ) = execute_george_batch(
        [
            "tv_ProjectInfo",
            "tv_MarkIn",
            "tv_MarkOut",
            "tv_StartFrame",
            "tv_Background",
        ],
        communicator
    )
    workfile_info_parts = workfile_info.split(" ")

    # Project frame start - not used
    workfile_info_parts.pop(-1)
    field_order = workfile_info_parts.pop(-1)
    frame_rate = float(workfile_info_parts.pop(-1))
    pixel_apsect = float(workfile_info_parts.pop(-1))
    height = int(workfile_info_parts.pop(-1))
    width = int(workfile_info_parts.pop(-1))

    # Marks return as "{frame - 1} {state} ", example "0 set".
    mark_in_frame, mark_in_state, _ = mark_in_result.split(" ")
    mark_out_frame, mark_out_state, _ = mark_out_result.split(" ")

    return {
        "width": width,
        "height": height,
        "pixel_aspect": pixel_apsect,
        "fps": frame_rate,
        "field_order": field_order,
        "mark_in": int(mark_in_frame),
        "mark_in_state": mark_in_state,
        "mark_in_set": mark_in_state == "set",
        "mark_out": int(mark_out_frame),
        "mark_out_state": mark_out_state,
        "mark_out_set": mark_out_state == "set",
        "start_frame": int(start_frame),
        "bg_color": parse_bg_color(bg_color),
    }


def parse_bg_color(bg_color):
    """Parse output of 'tv_Background'.

    Returns:
        Optional[list[str]]: Background type followed by color values,
            e.g. '["color", "255", "255", "255"]'.

    """
    bg_color = (bg_color or "").strip()
    if not bg_color:
        return None
    return bg_color.split(" ")


def get_scene_bg_color(communicator=None):
    """Background color set on scene.

    Is important for review exporting where scene bg color is used as
    background.
    """
    return parse_bg_color(execute_george("tv_Background", communicator))


def import_sequence(
    filepath,
    layer_name,
    stretch=False,
    timestretch=False,
    preload=False,
    communicator=None,
):
    """Load image or image sequence as new layer.

    Args:
        filepath (str): Path to image or first image of sequence.
        layer_name (str): Name of created layer.
        stretch (bool): Stretch image to project resolution.
        timestretch (bool): Stretch sequence to project frame rate.
        preload (bool): Preload images.
        communicator (Optional[BaseCommunicator]): Communicator.

    Returns:
        int: Id of created layer.

    Raises:
        RuntimeError: TVPaint failed to load the file.

    """
    command_parts = [
        "tv_LoadSequence", george_string(george_path(filepath))
    ]
    for enabled, option in (
        (stretch, "stretch"),
        (timestretch, "timestretch"),
        (preload, "preload"),
    ):
        if enabled:
            command_parts.append(option)

    result = execute_george(" ".join(command_parts), communicator) or ""
    try:
        layer_id = int(result.split(" ")[0])
    except ValueError:
        layer_id = -1
    if layer_id < 0:
        raise RuntimeError(
            f"TVPaint failed to load '{filepath}'. Output: {result}"
        )

    execute_george(
        f"tv_LayerRename {layer_id} {george_string(layer_name)}",
        communicator
    )
    return layer_id
