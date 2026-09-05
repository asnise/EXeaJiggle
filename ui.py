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
            col = box.column(align=True)
            col.prop(pb, '["jiggle_stiffness"]', text="Stiffness", slider=True)
            col.prop(pb, '["jiggle_damping"]', text="Damping", slider=True)
            col.prop(pb, '["jiggle_gravity"]', text="Gravity", slider=True)

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
                row.label(text=pb.name, icon='BONE_DATA')
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
    VIEW3D_PT_jiggle_main,
    VIEW3D_PT_jiggle_presets,
    VIEW3D_PT_jiggle_list,
    EXEA_JIGGLE_PT_preferences,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
