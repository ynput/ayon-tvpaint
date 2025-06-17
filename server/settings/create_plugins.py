from ayon_server.settings import BaseSettingsModel, SettingsField


class CreateWorkfileModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    default_variant: str = SettingsField(title="Default variant")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default variants")


class CreateReviewModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    active_on_create: bool = SettingsField(True, title="Active by default")
    default_variant: str = SettingsField(title="Default variant")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default variants")


class CreateRenderSceneModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    active_on_create: bool = SettingsField(True, title="Active by default")
    mark_for_review: bool = SettingsField(True, title="Review by default")
    default_pass_name: str = SettingsField(title="Default beauty pass")
    default_variant: str = SettingsField(title="Default variant")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default variants")


class CreateRenderLayerModel(BaseSettingsModel):
    mark_for_review: bool = SettingsField(True, title="Review by default")
    default_pass_name: str = SettingsField(title="Default beauty pass")
    default_variant: str = SettingsField(title="Default variant")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default variants")


class LayerNameTemplateModel(BaseSettingsModel):
    enabled: bool = SettingsField(False, title="Enabled")
    template: str = SettingsField(
        "G{group_id:0>3}_L{layer_id:0>3}_{variant}",
        title="Layer name template",
        description="Available keys '{group_id}' '{layer_id}' '{variant}'",
        placeholder="G{group_id:0>3}_L{layer_id:0>3}_{variant}",
    )
    group_id_start: int = SettingsField(
        10,
        title="Group index first value",
        ge=0,
    )
    group_id_increment: int = SettingsField(
        10,
        title="Group index increment",
        ge=1,
    )
    layer_id_start: int = SettingsField(
        10,
        title="Layer index first value",
        ge=0,
    )
    layer_id_increment: int = SettingsField(
        10,
        title="Layer index increment",
        ge=1,
    )


class CreateRenderPassModel(BaseSettingsModel):
    mark_for_review: bool = SettingsField(True, title="Review by default")
    default_variant: str = SettingsField(title="Default variant")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default variants"
    )
    render_pass_template: str = SettingsField(
        "{variant}",
        title="Render pass name template",
        description="Available keys '{layer_pos}' '{variant}'",
        placeholder="L{layer_pos:0>3}_{variant}",
    )
    layer_name_template: LayerNameTemplateModel = SettingsField(
        default_factory=LayerNameTemplateModel,
        title="Layer name template",
        description="Automatically change TVPaint layer name using template.",
    )


class AutoDetectCreateRenderModel(BaseSettingsModel):
    """The creator tries to auto-detect Render Layers and Render Passes in scene.

    For Render Layers is used group name as a variant and for Render Passes is
    used TVPaint layer name.

    Group names can be renamed by their used order in scene. The renaming
    template where can be used '{group_index}' formatting key which is
    filled by "used position index of group".
    - Template: 'G{group_index}'
    - Group offset: '10'
    - Group padding: '3'

    Would create group names "G010", "G020", ...
    """

    enabled: bool = SettingsField(True)
    allow_group_rename: bool = SettingsField(title="Allow group rename")
    group_name_template: str = SettingsField(title="Group name template")
    group_idx_offset: int = SettingsField(
        10, title="Group index Offset", ge=1
    )
    group_idx_padding: int = SettingsField(
        3, title="Group index Padding", ge=0
    )


class CreatePluginsModel(BaseSettingsModel):
    use_current_context: bool = SettingsField(
        True,
        title="Force to use current context",
    )
    create_workfile: CreateWorkfileModel = SettingsField(
        default_factory=CreateWorkfileModel,
        title="Create Workfile"
    )
    create_review: CreateReviewModel = SettingsField(
        default_factory=CreateReviewModel,
        title="Create Review"
    )
    create_render_scene: CreateRenderSceneModel = SettingsField(
        default_factory=CreateReviewModel,
        title="Create Render Scene"
    )
    create_render_layer: CreateRenderLayerModel = SettingsField(
        default_factory=CreateRenderLayerModel,
        title="Create Render Layer"
    )
    create_render_pass: CreateRenderPassModel = SettingsField(
        default_factory=CreateRenderPassModel,
        title="Create Render Pass"
    )
    auto_detect_render: AutoDetectCreateRenderModel = SettingsField(
        default_factory=AutoDetectCreateRenderModel,
        title="Auto-Detect Create Render",
    )


DEFAULT_CREATE_SETTINGS = {
    "use_current_context": True,
    "create_workfile": {
        "enabled": True,
        "default_variant": "Main",
        "default_variants": []
    },
    "create_review": {
        "enabled": True,
        "active_on_create": True,
        "default_variant": "Main",
        "default_variants": []
    },
    "create_render_scene": {
        "enabled": True,
        "active_on_create": False,
        "mark_for_review": True,
        "default_pass_name": "beauty",
        "default_variant": "Main",
        "default_variants": []
    },
    "create_render_layer": {
        "mark_for_review": False,
        "default_pass_name": "beauty",
        "default_variant": "Main",
        "default_variants": []
    },
    "create_render_pass": {
        "mark_for_review": False,
        "default_variant": "Main",
        "default_variants": []
    },
    "auto_detect_render": {
        "enabled": False,
        "allow_group_rename": True,
        "group_name_template": "G{group_index}",
        "group_idx_offset": 10,
        "group_idx_padding": 3
    }
}
