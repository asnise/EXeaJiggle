import bpy
from . import core
from .operators import JIGGLE_OT_realtime


class VIEW3D_PT_jiggle_main(bpy.types.Panel):
    bl_label = "EXea Jiggle"
    bl_idname = "VIEW3D_PT_jiggle_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "EXea Jiggle"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        box = layout.box()
        row = box.row(align=True)
        running = JIGGLE_OT_realtime._is_running
        icon = 'PAUSE' if running else 'PLAY'
        label = "Stop Real-time" if running else "Start Real-time"
        row.operator("jiggle.toggle_realtime", text=label, icon=icon, depress=running)
        row.operator("jiggle.reset", text="", icon='FILE_REFRESH')

        if not obj or obj.type != 'ARMATURE' or context.mode != 'POSE':
            layout.label(text="Select Armature → Pose Mode", icon='INFO')
            return

        row_util = layout.row(align=True)
        row_util.operator("jiggle.select_all", text="Select All", icon='RESTRICT_SELECT_OFF')
        row_util.operator("jiggle.remove_all", text="Remove All", icon='TRASH')

        pb = context.active_pose_bone
        if not pb:
            layout.label(text="Select a pose bone", icon='INFO')
            return

        has = core.has_jiggle(pb)
        chain = core.get_chain_bones(pb)
        chain_count = sum(1 for b in chain if core.has_jiggle(b))

        box = layout.box()
        row = box.row()
        row.label(text=pb.name, icon='BONE_DATA')
        if has:
            row.label(text="Active", icon='CHECKMARK')
        else:
            row.label(text="Inactive", icon='X')

        if not has:
            col = box.column(align=True)
            col.operator("jiggle.setup", text="Apply Jiggle", icon='PHYSICS')
            col.operator("jiggle.setup_chain", text="Setup Chain (Tail/Hair)", icon='LINKED')
        else:
            row_layer = box.row(align=True)
            row_layer.label(text="Layer:", icon='GROUP_BONE')
            curr_layer = core.get_bone_layer(pb)
            row_layer.label(text=curr_layer)
            for tag in ("Hair", "Tail", "Clothes", "Main"):
                if tag != curr_layer:
                    op_l = row_layer.operator("jiggle.assign_layer", text=tag)
                    op_l.layer_name = tag

            col = box.column(align=True)
            col.prop(pb, '["jiggle_stiffness"]', text="Stiffness", slider=True)
            col.prop(pb, '["jiggle_damping"]', text="Damping", slider=True)
            col.prop(pb, '["jiggle_gravity"]', text="Gravity", slider=True)

            if len(context.selected_pose_bones) > 1:
                col.separator()
                col.operator("jiggle.copy_to_selected", text=f"Copy Settings to {len(context.selected_pose_bones)} Selected", icon='COPYDOWN')

            box.separator()
            row = box.row(align=True)
            row.operator("jiggle.remove", text="Remove", icon='TRASH')
            if len(chain) > 1 and chain_count > 0:
                row.operator("jiggle.remove_chain", text="Remove Chain", icon='UNLINKED')

        if has and len(chain) > 1 and chain_count > 1:
            box.separator()
            box.label(text=f"Chain: {chain_count} bones active", icon='LINKED')

        layout.separator()
        layout.operator("jiggle.bake", text="Bake to Keyframes", icon='ACTION_TWEAK')


def _on_layer_name_changed(self, context):
    old_name = self.get("prev_name", "")
    new_name = self.name.strip()
    if not new_name:
        return
    if old_name and old_name != new_name and context and context.active_object and context.active_object.type == 'ARMATURE':
        core.rename_layer(context.active_object, old_name, new_name)
    self["prev_name"] = new_name


def _on_layer_prop_changed(self, context):
    if not context or not context.active_object or context.active_object.type != 'ARMATURE':
        return
    for pb in context.active_object.pose.bones:
        if core.has_jiggle(pb) and core.get_bone_layer(pb) == self.name:
            pb["jiggle_stiffness"] = self.stiffness
            pb["jiggle_damping"] = self.damping
            pb["jiggle_gravity"] = self.gravity


class EXEA_JIGGLE_LayerItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Layer Name", default="Main", update=_on_layer_name_changed)
    prev_name: bpy.props.StringProperty(default="Main")
    stiffness: bpy.props.FloatProperty(name="Stiffness", default=0.35, min=0.0, max=1.0, update=_on_layer_prop_changed)
    damping: bpy.props.FloatProperty(name="Damping", default=0.35, min=0.0, max=1.0, update=_on_layer_prop_changed)
    gravity: bpy.props.FloatProperty(name="Gravity", default=0.30, min=0.0, max=2.0, update=_on_layer_prop_changed)


class JIGGLE_UL_layers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        arm_obj = context.active_object
        lname = item.name

        count = sum(1 for pb in arm_obj.pose.bones if core.has_jiggle(pb) and core.get_bone_layer(pb) == lname)

        nl = lname.lower()
        if "hair" in nl:
            custom_icon = 'STRANDS'
        elif "tail" in nl:
            custom_icon = 'OUTLINER_OB_ARMATURE'
        elif any(k in nl for k in ("cloth", "skirt", "dress", "sleeve", "cape", "ribbon")):
            custom_icon = 'MOD_CLOTH'
        else:
            custom_icon = 'GROUP_BONE'

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon=custom_icon)
            row.label(text=f"({count})")

            is_muted = False
            if count > 0:
                for pb in arm_obj.pose.bones:
                    if core.has_jiggle(pb) and core.get_bone_layer(pb) == lname:
                        con = pb.constraints.get(core.CONSTRAINT_NAME)
                        if con and con.mute:
                            is_muted = True
                        break

            mute_icon = 'CHECKBOX_DEHLT' if is_muted else 'CHECKBOX_HLT'
            op_mute = row.operator("jiggle.toggle_layer_mute", text="", icon=mute_icon, emboss=False)
            op_mute.layer_name = lname

            op_sel = row.operator("jiggle.select_layer", text="", icon='RESTRICT_SELECT_OFF', emboss=False)
            op_sel.layer_name = lname
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon=custom_icon)


class VIEW3D_PT_jiggle_layers(bpy.types.Panel):
    bl_label = "Jiggle Layers"
    bl_idname = "VIEW3D_PT_jiggle_layers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "EXea Jiggle"
    bl_parent_id = "VIEW3D_PT_jiggle_main"

    @classmethod
    def poll(cls, ctx):
        obj = ctx.active_object
        return obj and obj.type == 'ARMATURE' and ctx.mode == 'POSE'

    def draw(self, ctx):
        layout = self.layout
        arm_obj = ctx.active_object
        arm = arm_obj.data

        row = layout.row()
        row.template_list("JIGGLE_UL_layers", "", arm, "jiggle_layers", arm, "jiggle_layer_index", rows=4)

        col = row.column(align=True)
        col.operator("jiggle.add_layer", icon='ADD', text="")
        col.operator("jiggle.remove_layer", icon='REMOVE', text="")
        col.separator()
        col.operator("jiggle.rename_layer", icon='GREASEPENCIL', text="")
        col.operator("jiggle.sync_layers", icon='FILE_REFRESH', text="")

        bone_layers = core.get_armature_layers(arm_obj)
        existing_names = {item.name for item in arm.jiggle_layers}
        missing_layers = [l for l in bone_layers if l not in existing_names]
        if missing_layers:
            layout.operator("jiggle.sync_layers", text=f"Sync Detected Layers ({len(missing_layers)})", icon='FILE_REFRESH')

        if arm.jiggle_layers and 0 <= arm.jiggle_layer_index < len(arm.jiggle_layers):
            active_item = arm.jiggle_layers[arm.jiggle_layer_index]
            lname = active_item.name

            box = layout.box()
            row_header = box.row(align=True)
            row_header.prop(active_item, "name", text="Name", icon='GROUP_BONE')
            op_sel = row_header.operator("jiggle.select_layer", text="Select", icon='RESTRICT_SELECT_OFF')
            op_sel.layer_name = lname

            row_p = box.row(align=True)
            row_p.label(text="Preset:")
            for pname in ("Soft", "Medium", "Firm"):
                op_p = row_p.operator("jiggle.apply_layer_preset", text=pname)
                op_p.layer_name = lname
                op_p.preset_name = pname

            col_s = box.column(align=True)
            col_s.prop(active_item, "stiffness", slider=True)
            col_s.prop(active_item, "damping", slider=True)
            col_s.prop(active_item, "gravity", slider=True)

            if ctx.selected_pose_bones:
                box.separator()
                op_assign = box.operator("jiggle.assign_layer", text=f"Assign Selected to '{lname}'", icon='IMPORT')
                op_assign.layer_name = lname


class VIEW3D_PT_jiggle_presets(bpy.types.Panel):
    bl_label = "Presets"
    bl_idname = "VIEW3D_PT_jiggle_presets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "EXea Jiggle"
    bl_parent_id = "VIEW3D_PT_jiggle_main"

    @classmethod
    def poll(cls, ctx):
        pb = ctx.active_pose_bone
        return pb and core.has_jiggle(pb)

    def draw(self, ctx):
        layout = self.layout

        row = layout.row(align=True)
        row.label(text="Default:", icon='PRESET')
        for name in ("Soft", "Medium", "Firm"):
            op = row.operator("jiggle.apply_preset", text=name)
            op.name = name

        user_presets = core.load_user_presets()
        if user_presets:
            layout.separator()
            layout.label(text="Custom:", icon='USER')
            for name, vals in user_presets.items():
                row = layout.row(align=True)
                op = row.operator("jiggle.apply_preset", text=name)
                op.name = name
                s = vals.get("jiggle_stiffness", 0)
                d = vals.get("jiggle_damping", 0)
                row.label(text=f"S:{s:.2f} D:{d:.2f}")
                op = row.operator("jiggle.delete_preset", text="", icon='X')
                op.name = name

        layout.separator()
        row_save = layout.row(align=True)
        row_save.operator("jiggle.save_preset", text="Save Preset", icon='ADD')
        row_save.operator("jiggle.open_presets_folder", text="", icon='FOLDER_REDIRECT')


class VIEW3D_PT_jiggle_list(bpy.types.Panel):
    bl_label = "Active Jiggle Bones"
    bl_idname = "VIEW3D_PT_jiggle_list"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "EXea Jiggle"
    bl_parent_id = "VIEW3D_PT_jiggle_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, ctx):
        obj = ctx.active_object
        return obj and obj.type == 'ARMATURE' and ctx.mode == 'POSE'

    def draw(self, ctx):
        layout = self.layout
        obj = ctx.active_object
        found = False
        for pb in obj.pose.bones:
            if core.has_jiggle(pb):
                row = layout.row()
                layer_tag = core.get_bone_layer(pb)
                row.label(text=f"{pb.name} [{layer_tag}]", icon='BONE_DATA')
                s = pb.get("jiggle_stiffness", 0)
                d = pb.get("jiggle_damping", 0)
                g = pb.get("jiggle_gravity", 0)
                row.label(text=f"S:{s:.2f} D:{d:.2f} G:{g:.2f}")
                found = True
        if not found:
            layout.label(text="No jiggle bones yet", icon='INFO')


class EXEA_JIGGLE_PT_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__.split(".")[0] if __package__ else "exea_jiggle"

    def draw(self, context):
        layout = self.layout
        col = layout.column(spacing=6)
        box = col.box()
        box.label(text="Presets Storage", icon='PRESET')
        row = box.row()
        row.operator("jiggle.open_presets_folder", icon='FOLDER_REDIRECT')
        box2 = col.box()
        box2.label(text="Documentation & Support", icon='HELP')
        row2 = box2.row()
        row2.operator("wm.url_open", text="GitHub Repo", icon='URL').url = "https://github.com/asnise/EXeaJiggle"
        row2.operator("wm.url_open", text="Report Issues", icon='QUESTION').url = "https://github.com/asnise/EXeaJiggle/issues"


classes = (
    EXEA_JIGGLE_LayerItem,
    JIGGLE_UL_layers,
    VIEW3D_PT_jiggle_main,
    VIEW3D_PT_jiggle_layers,
    VIEW3D_PT_jiggle_presets,
    VIEW3D_PT_jiggle_list,
    EXEA_JIGGLE_PT_preferences,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Armature.jiggle_layers = bpy.props.CollectionProperty(type=EXEA_JIGGLE_LayerItem)
    bpy.types.Armature.jiggle_layer_index = bpy.props.IntProperty(name="Active Jiggle Layer", default=0)


def unregister():
    if hasattr(bpy.types.Armature, "jiggle_layers"):
        del bpy.types.Armature.jiggle_layers
    if hasattr(bpy.types.Armature, "jiggle_layer_index"):
        del bpy.types.Armature.jiggle_layer_index
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

