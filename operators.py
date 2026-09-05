import bpy
import os
import time
from . import core


class JIGGLE_OT_setup(bpy.types.Operator):
    bl_idname = "jiggle.setup"
    bl_label = "Apply Jiggle"
    bl_description = "Apply jiggle physics to selected bones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.selected_pose_bones)

    def execute(self, ctx):
        count = 0
        for pb in ctx.selected_pose_bones:
            core.setup_bone(pb)
            count += 1
        self.report({'INFO'}, f"Jiggle applied to {count} bone(s)")
        return {'FINISHED'}


class JIGGLE_OT_setup_chain(bpy.types.Operator):
    bl_idname = "jiggle.setup_chain"
    bl_label = "Setup Chain"
    bl_description = "Setup jiggle on entire bone chain (tail/hair). Select root bone"
    bl_options = {'REGISTER', 'UNDO'}

    falloff: bpy.props.FloatProperty(
        name="Falloff",
        description="Stiffness reduction per bone level (lower = tips more floppy)",
        default=0.85,
        min=0.1,
        max=1.0,
    )

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.active_pose_bone)

    def execute(self, ctx):
        root = ctx.active_pose_bone
        chain = core.setup_chain(root, self.falloff)
        self.report({'INFO'}, f"Chain: {len(chain)} bones (falloff {self.falloff:.2f})")
        return {'FINISHED'}


class JIGGLE_OT_remove(bpy.types.Operator):
    bl_idname = "jiggle.remove"
    bl_label = "Remove Jiggle"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.selected_pose_bones)

    def execute(self, ctx):
        count = 0
        for pb in ctx.selected_pose_bones:
            if core.has_jiggle(pb):
                core.cleanup_bone(pb)
                count += 1
        self.report({'INFO'}, f"Removed from {count} bone(s)")
        return {'FINISHED'}


class JIGGLE_OT_remove_chain(bpy.types.Operator):
    bl_idname = "jiggle.remove_chain"
    bl_label = "Remove Chain"
    bl_description = "Remove jiggle from entire bone chain"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.active_pose_bone)

    def execute(self, ctx):
        chain = core.get_chain_bones(ctx.active_pose_bone)
        count = 0
        for pb in chain:
            if core.has_jiggle(pb):
                core.cleanup_bone(pb)
                count += 1
        self.report({'INFO'}, f"Removed chain: {count} bones")
        return {'FINISHED'}


class JIGGLE_OT_reset(bpy.types.Operator):
    bl_idname = "jiggle.reset"
    bl_label = "Reset Simulation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return ctx.active_object and ctx.active_object.type == 'ARMATURE'

    def execute(self, ctx):
        dg = ctx.evaluated_depsgraph_get()
        core.simulate_all(ctx.scene, dg, 0, is_reset=True)
        self.report({'INFO'}, "Simulation reset")
        return {'FINISHED'}


class JIGGLE_OT_apply_preset(bpy.types.Operator):
    bl_idname = "jiggle.apply_preset"
    bl_label = "Apply Preset"

    name: bpy.props.StringProperty()

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.selected_pose_bones)

    def execute(self, ctx):
        for pb in ctx.selected_pose_bones:
            if core.has_jiggle(pb):
                core.apply_preset_to_bone(pb, self.name)
        self.report({'INFO'}, f"Applied '{self.name}'")
        return {'FINISHED'}


class JIGGLE_OT_save_preset(bpy.types.Operator):
    bl_idname = "jiggle.save_preset"
    bl_label = "Save Preset"
    bl_description = "Save current bone settings as a reusable preset"

    preset_name: bpy.props.StringProperty(name="Name", default="My Preset")

    @classmethod
    def poll(cls, ctx):
        return ctx.active_pose_bone and core.has_jiggle(ctx.active_pose_bone)

    def invoke(self, ctx, event):
        return ctx.window_manager.invoke_props_dialog(self)

    def execute(self, ctx):
        name = self.preset_name.strip()
        if not name:
            self.report({'WARNING'}, "Name cannot be empty")
            return {'CANCELLED'}
        if core.is_default_preset(name):
            self.report({'WARNING'}, f"Cannot overwrite default preset '{name}'")
            return {'CANCELLED'}
        pb = ctx.active_pose_bone
        core.save_preset(
            name,
            pb.get("jiggle_stiffness", 0.35),
            pb.get("jiggle_damping", 0.35),
            pb.get("jiggle_gravity", 0.30),
        )
        self.report({'INFO'}, f"Saved preset '{name}'")
        return {'FINISHED'}


class JIGGLE_OT_delete_preset(bpy.types.Operator):
    bl_idname = "jiggle.delete_preset"
    bl_label = "Delete Preset"

    name: bpy.props.StringProperty()

    def execute(self, ctx):
        if core.is_default_preset(self.name):
            self.report({'WARNING'}, f"Cannot delete default preset '{self.name}'")
            return {'CANCELLED'}
        if core.delete_preset(self.name):
            self.report({'INFO'}, f"Deleted '{self.name}'")
        else:
            self.report({'WARNING'}, f"Preset '{self.name}' not found")
        return {'FINISHED'}


class JIGGLE_OT_bake(bpy.types.Operator):
    bl_idname = "jiggle.bake"
    bl_label = "Bake to Keyframes"
    bl_description = "Bake jiggle physics simulation to keyframes and clear physics constraints"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.selected_pose_bones)

    def execute(self, ctx):
        was_running = JIGGLE_OT_realtime._is_running
        if was_running:
            JIGGLE_OT_realtime._is_running = False

        dg = ctx.evaluated_depsgraph_get()
        core.simulate_all(ctx.scene, dg, 0, is_reset=True)

        arm = ctx.active_object
        target_empties = []
        for pb in ctx.selected_pose_bones:
            con = pb.constraints.get(core.CONSTRAINT_NAME)
            if con and con.target:
                target_empties.append(con.target)

        original_action = None
        if arm and arm.animation_data and arm.animation_data.action:
            original_action = arm.animation_data.action
            baked_action = original_action.copy()
            baked_action.name = f"{original_action.name}_baked"
            arm.animation_data.action = baked_action

        use_current = original_action is not None

        bpy.ops.nla.bake(
            frame_start=ctx.scene.frame_start,
            frame_end=ctx.scene.frame_end,
            only_selected=True,
            visual_keying=True,
            clear_constraints=True,
            use_current_action=use_current,
            bake_types={'POSE'},
        )

        for empty in target_empties:
            if empty and empty.name in bpy.data.objects:
                bpy.data.objects.remove(empty, do_unlink=True)

        for pb in ctx.selected_pose_bones:
            for prop in ("jiggle_stiffness", "jiggle_damping", "jiggle_gravity"):
                if prop in pb:
                    del pb[prop]

        self.report({'INFO'}, "Baked to keyframes and cleaned constraints")
        return {'FINISHED'}


class JIGGLE_OT_select_all(bpy.types.Operator):
    bl_idname = "jiggle.select_all"
    bl_label = "Select All Jiggle Bones"
    bl_description = "Select all pose bones on active armature with active jiggle physics"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE')

    def execute(self, ctx):
        count = 0
        for pb in ctx.active_object.pose.bones:
            if core.has_jiggle(pb):
                pb.bone.select = True
                count += 1
            else:
                pb.bone.select = False
        self.report({'INFO'}, f"Selected {count} jiggle bone(s)")
        return {'FINISHED'}


class JIGGLE_OT_remove_all(bpy.types.Operator):
    bl_idname = "jiggle.remove_all"
    bl_label = "Remove All Jiggle"
    bl_description = "Remove jiggle physics from all bones on the active armature"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE')

    def execute(self, ctx):
        count = 0
        for pb in ctx.active_object.pose.bones:
            if core.has_jiggle(pb):
                core.cleanup_bone(pb)
                count += 1
        self.report({'INFO'}, f"Removed jiggle from {count} bone(s)")
        return {'FINISHED'}


class JIGGLE_OT_open_presets_folder(bpy.types.Operator):
    bl_idname = "jiggle.open_presets_folder"
    bl_label = "Open Presets Folder"
    bl_description = "Open the directory where user presets are stored"

    def execute(self, ctx):
        path = os.path.dirname(core._preset_path())
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        bpy.ops.wm.path_open(filepath=path)
        return {'FINISHED'}


class JIGGLE_OT_realtime(bpy.types.Operator):
    bl_idname = "jiggle.toggle_realtime"
    bl_label = "Toggle Real-time"
    bl_description = "Start/stop real-time jiggle simulation in viewport"

    _is_running = False
    _timer = None
    _prev_time = 0.0

    def modal(self, ctx, event):
        if not self.__class__._is_running:
            self._cleanup(ctx)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            now = time.time()
            dt = now - self._prev_time
            self._prev_time = now
            dt = min(max(dt, 0.001), 0.1)

            try:
                dg = ctx.evaluated_depsgraph_get()
                core.simulate_all(ctx.scene, dg, dt)
            except Exception:
                pass

            if ctx.screen:
                for area in ctx.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        return {'PASS_THROUGH'}

    def invoke(self, ctx, event):
        cls = self.__class__
        if cls._is_running:
            cls._is_running = False
            self.report({'INFO'}, "Real-time jiggle stopped")
            return {'FINISHED'}

        cls._is_running = True
        self._prev_time = time.time()
        self._timer = ctx.window_manager.event_timer_add(1.0 / 60.0, window=ctx.window)
        ctx.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Real-time jiggle started")
        return {'RUNNING_MODAL'}

    def _cleanup(self, ctx):
        if self._timer:
            try:
                ctx.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        self.__class__._is_running = False

    def cancel(self, ctx):
        self._cleanup(ctx)


classes = (
    JIGGLE_OT_setup,
    JIGGLE_OT_setup_chain,
    JIGGLE_OT_remove,
    JIGGLE_OT_remove_chain,
    JIGGLE_OT_reset,
    JIGGLE_OT_apply_preset,
    JIGGLE_OT_save_preset,
    JIGGLE_OT_delete_preset,
    JIGGLE_OT_bake,
    JIGGLE_OT_select_all,
    JIGGLE_OT_remove_all,
    JIGGLE_OT_open_presets_folder,
    JIGGLE_OT_realtime,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    JIGGLE_OT_realtime._is_running = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
