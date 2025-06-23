from typing import Any


async def _convert_multilayer_0_3_8(
    overrides: dict[str, Any],
):
    values = overrides
    for key in (
        "publish",
        "ExtractConvertToEXR",
    ):
        if key not in values:
            return
        values = values[key]

    if "multilayer_exr" in values:
        values["multichannel_exr"] = values.pop("multilayer_exr")


async def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    await _convert_multilayer_0_3_8(overrides)
    return overrides
