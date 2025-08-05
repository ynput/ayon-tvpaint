"""Plugin converting png files from ExtractSequence into exrs.

Requires:
    ExtractSequence - source of PNG
    ExtractReview - review was already created so we can convert to any exr
"""
import os
import collections
import copy

import clique
import pyblish.api

from ayon_core.lib import (
    get_oiio_tool_args,
    ToolNotFoundError,
    run_subprocess,
)
from ayon_core.pipeline import PublishError


class ExtractConvertToEXR(pyblish.api.ContextPlugin):
    # Offset to get after ExtractSequence plugin.
    order = pyblish.api.ExtractorOrder + 0.1
    label = "Extract Sequence EXR"
    hosts = ["tvpaint"]

    settings_category = "tvpaint"

    enabled = False

    # Replace source PNG files or just add
    replace_pngs = True
    # EXR compression
    exr_compression = "ZIP"
    multichannel_exr = False
    auto_trim = True

    def process(self, context):
        render_layer_items = []
        render_pass_items = []

        for instance in context:
            if instance.data.get("publish") is False:
                continue

            if instance.data["family"] != "render":
                continue

            if instance.data.get("farm"):
                self.log.debug(
                    "Skipping instance, is marked for farm rendering."
                )
                continue

            repres = instance.data.get("representations") or []
            src_repre = next(
                (
                    repre
                    for repre in repres
                    if repre["name"] == "png"
                ),
                None
            )
            if not src_repre:
                self.log.debug("Skipping instance, no PNG representation.")
                continue

            creator_identifier = instance.data.get("creator_identifier")
            if creator_identifier == "render.layer":
                render_layer_items.append((instance, src_repre))
            elif creator_identifier == "render.pass":
                render_pass_items.append((instance, src_repre))

        if not render_layer_items and not render_pass_items:
            return

        try:
            base_oiio_args = get_oiio_tool_args("oiiotool")
        except ToolNotFoundError:
            # Raise an exception when oiiotool is not available
            # - this can currently happen on MacOS machines
            raise PublishError(
                "OpenImageIO tool is not available on this machine."
            )

        if self.multichannel_exr:
            self._multichannel_exr_conversion(
                render_layer_items,
                render_pass_items,
                base_oiio_args
            )
        else:
            for item in render_layer_items + render_pass_items:
                instance, src_repre = item
                self._simple_exr_conversion(
                    instance, src_repre, base_oiio_args
                )

    def _simple_exr_conversion(self, instance, repre, base_oiio_args):
        repres = instance.data["representations"]

        src_filepaths = set()
        new_filenames = []

        output_arg = "-o"
        if self.auto_trim:
            output_arg = "-o:autotrim=1"
        for src_filename in repre["files"]:
            dst_filename = os.path.splitext(src_filename)[0] + ".exr"
            new_filenames.append(dst_filename)

            src_filepath = os.path.join(repre["stagingDir"], src_filename)
            dst_filepath = os.path.join(repre["stagingDir"], dst_filename)

            src_filepaths.add(src_filepath)

            args = copy.deepcopy(base_oiio_args)
            args.extend([
                src_filepath,
                "--colorconvert", "sRGB", "linear",
                "--compression", self.exr_compression,
                output_arg, dst_filepath
            ])
            run_subprocess(args)

        repres.append(
            {
                "name": "exr",
                "ext": "exr",
                "files": new_filenames,
                "stagingDir": repre["stagingDir"],
                "tags": list(repre["tags"])
            }
        )

        if self.replace_pngs:
            instance.data["representations"].remove(repre)

            for filepath in src_filepaths:
                instance.context.data["cleanupFullPaths"].append(filepath)

    def _multichannel_exr_conversion(
        self,
        render_layer_items,
        render_pass_items,
        base_oiio_args
    ):
        render_pass_items_by_layer_id = collections.defaultdict(list)
        for (instance, repre) in render_pass_items:
            creator_attributes = instance.data["creator_attributes"]
            render_layer_id = creator_attributes[
                "render_layer_instance_id"
            ]
            render_pass_items_by_layer_id[render_layer_id].append(
                (instance, repre)
            )

        for (render_layer_instance, src_layer_repre) in render_layer_items:
            render_layer_id = render_layer_instance.data["instance_id"]
            render_pass_items = render_pass_items_by_layer_id[
                render_layer_id
            ]

            layer_staging_dir = src_layer_repre["stagingDir"]
            layer_filename = src_layer_repre["files"]
            is_sequence = isinstance(layer_filename, list)
            dst_filename = None
            padding = frame_start = frame_end = None
            if is_sequence:
                cols, _ = clique.assemble(layer_filename)
                col = cols[0]
                padding = col.padding
                frame_start = min(col.indexes)
                frame_end = max(col.indexes)
                layer_filename = col.format("{head}#{tail}")

                # Prepare the destination filename for sequences
                template = col.format("{head}{padding}{tail}")
                template = os.path.splitext(template)[0] + ".exr"
                dst_filename = [
                    template % idx
                    for idx in col.indexes
                ]

            basename, _ = os.path.splitext(layer_filename)
            new_filename = f"{basename}.exr"
            if not is_sequence:
                dst_filename = new_filename

            dst_path = os.path.join(layer_staging_dir, new_filename)

            # Prepare the arguments for the oiio tool
            src_beauty_path = os.path.join(layer_staging_dir, layer_filename)

            args = copy.deepcopy(base_oiio_args)
            args.append("-no-autopremult")
            if padding is not None:
                args.extend([
                    "--frames", f"{frame_start}-{frame_end}",
                    "--framepadding", str(padding),
                ])

            args.extend([
                "-i", src_beauty_path,
                "--ch", "R,G,B,A",
            ])

            for (render_pass_instance, pass_repre) in render_pass_items:
                product_name = render_pass_instance.data["productName"]
                pass_filename = pass_repre["files"]
                if isinstance(pass_filename, list):
                    cols, _ = clique.assemble(pass_filename)
                    col = cols[0]
                    pass_filename = col.format("{head}#{tail}")
                pass_staging_dir = pass_repre["stagingDir"]
                path = os.path.join(pass_staging_dir, pass_filename)
                # Add the render pass representation
                channel_names = [f"{product_name}.{ch_n}" for ch_n in "RGBA"]
                args.extend([
                    "-i", path,
                    "--chnames", ",".join(channel_names),
                    "--chappend",
                ])

            output_arg = "-o"
            if self.auto_trim:
                output_arg = "-o:autotrim=1"

            args.extend([
                "--compression", self.exr_compression,
                output_arg, dst_path,
            ])
            self.log.debug("Running oiiotool with args: %s", args)
            run_subprocess(args)

            layer_repres = render_layer_instance.data["representations"]
            layer_repres.append(
                {
                    "name": "exr",
                    "ext": "exr",
                    "files": dst_filename,
                    "stagingDir": layer_staging_dir,
                    "tags": list(src_layer_repre["tags"])
                }
            )
            context = render_layer_instance.context
            # Remove render pass instances from the context
            # - Remove all files of all render pass representations and then
            #   the instances.
            for (render_pass_instance, _) in render_pass_items:
                render_pass_instance.data["publish"] = False
                for repre in render_pass_instance.data["representations"]:
                    staging_dir = repre["stagingDir"]
                    filenames = repre["files"]
                    if not isinstance(filenames, list):
                        filenames = [filenames]
                    src_filepaths = [
                        os.path.join(staging_dir, filename)
                        for filename in filenames
                    ]
                    context.data["cleanupFullPaths"].extend(src_filepaths)
                context.remove(render_pass_instance)

            # Remove the source representation of the render layer
            if self.replace_pngs:
                layer_repres.remove(src_layer_repre)
                staging_dir = repre["stagingDir"]
                filenames = repre["files"]
                if not isinstance(filenames, list):
                    filenames = [filenames]
                src_filepaths = [
                    os.path.join(staging_dir, filename)
                    for filename in filenames
                ]
                context.data["cleanupFullPaths"].extend(src_filepaths)
