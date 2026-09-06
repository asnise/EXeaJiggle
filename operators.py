import bpy
import os
import time
from . import core


def _search_layer_names(self, context, edit_text):
    if not context or not context.active_object or context.active_object.type != 'ARMATURE':
        return []
    arm = context.active_object.data
    if not hasattr(arm, "jiggle_layers"):
        return []
    return [item.name for item in arm.jiggle_layers if (not edit_text or edit_text.lower() in item.name.lower())]


class JIGGLE_OT_setup(bpy.types.Operator):
    bl_idname = "jiggle.setup"
    bl_label = "Apply Jiggle"
    bl_description = "Apply jiggle physics to selected bones into a shared group"
    bl_options = {'REGISTER', 'UNDO'}

    layer_name: bpy.props.StringProperty(
        name="Group Name",
        description="Layer / Group name to assign all selected bones to",
        default="",
        search=_search_layer_names,
    )

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.selected_pose_bones)

    def _determine_default_layer(self, ctx):
        arm = ctx.active_object.data if ctx.active_object else None
        existing = {item.name for item in arm.jiggle_layers} if (arm and hasattr(arm, "jiggle_layers")) else set()

        hint = ""
        if ctx.active_pose_bone:
            g = core.guess_layer_from_name(ctx.active_pose_bone.name)
            if g != core.DEFAULT_LAYER:
                hint = g
        if not hint and ctx.selected_pose_bones:
            for pb in ctx.selected_pose_bones:
                g = core.guess_layer_from_name(pb.name)
                if g != core.DEFAULT_LAYER:
                    hint = g
                    break

        if hint:
            return hint

        idx = 1
        while f"Group {idx}" in existing:
            idx += 1
        return f"Group {idx}"

    def invoke(self, ctx, event):
        self.layer_name = self._determine_default_layer(ctx)
        return ctx.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, ctx):
        layout = self.layout
        count = len(ctx.selected_pose_bones) if ctx.selected_pose_bones else 0
        layout.label(text=f"Assign {count} selected bone(s) to group:", icon='GROUP_BONE')
        layout.prop(self, "layer_name", text="Name")

    def execute(self, ctx):
        name = self.layer_name.strip()
        if not name:
            name = self._determine_default_layer(ctx)

        count = 0
        for pb in ctx.selected_pose_bones:
            core.setup_bone(pb, layer_name=name)
            count += 1

        core.sync_armature_layers(ctx.active_object)

        arm = ctx.active_object.data
        if hasattr(arm, "jiggle_layers"):
            for i, item in enumerate(arm.jiggle_layers):
                if item.name == name:
                    arm.jiggle_layer_index = i
                    break

        self.report({'INFO'}, f"Jiggle applied to {count} bone(s) in '{name}'")
        return {'FINISHED'}


class JIGGLE_OT_setup_chain(bpy.types.Operator):
    bl_idname = "jiggle.setup_chain"
    bl_label = "Setup Chain"
    bl_description = "Setup jiggle on entire bone chain (tail/hair). Auto-detects root if multiple bones selected"
    bl_options = {'REGISTER', 'UNDO'}

    falloff: bpy.props.FloatProperty(
        name="Falloff",
        description="Stiffness reduction per bone level (lower = tips more floppy)",
        default=0.85,
        min=0.1,
        max=1.0,
    )

    layer_name: bpy.props.StringProperty(
        name="Layer Name",
        description="Assign chain bones to this layer (leave empty to auto-detect)",
        default="",
        search=_search_layer_names,
    )

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and (ctx.active_pose_bone or ctx.selected_pose_bones))

    def invoke(self, ctx, event):
        root = core.find_chain_root(ctx.selected_pose_bones, ctx.active_pose_bone)
        if not self.layer_name and root:
            self.layer_name = core.guess_layer_from_name(root.name)
        return ctx.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, ctx):
        layout = self.layout
        root = core.find_chain_root(ctx.selected_pose_bones, ctx.active_pose_bone)
        chain_len = len(core.get_chain_bones(root)) if root else 0
        root_name = root.name if root else ''
        layout.label(text=f"Setup Chain: {chain_len} bone(s) from '{root_name}'", icon='LINKED')
        layout.prop(self, "layer_name", text="Group Name")
        layout.prop(self, "falloff", text="Falloff", slider=True)

    def execute(self, ctx):
        root = core.find_chain_root(ctx.selected_pose_bones, ctx.active_pose_bone)
        if not root:
            self.report({'ERROR'}, "No active or selected bone found")
            return {'CANCELLED'}

        layer = self.layer_name.strip() if self.layer_name else None
        chain = core.setup_chain(root, self.falloff, layer_name=layer)
        layer_used = core.get_bone_layer(root)
        core.sync_armature_layers(ctx.active_object)

        arm = ctx.active_object.data
        if hasattr(arm, "jiggle_layers"):
            for i, item in enumerate(arm.jiggle_layers):
                if item.name == layer_used:
                    arm.jiggle_layer_index = i
                    break

        self.report({'INFO'}, f"Chain: {len(chain)} bones in '{layer_used}' (falloff {self.falloff:.2f})")
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


def _set_bone_selection(pb, state: bool):
    if hasattr(pb, "select"):
        try:
            pb.select = state
            return
        except Exception:
            pass
    if hasattr(pb, "bone") and hasattr(pb.bone, "select"):
        try:
            pb.bone.select = state
            return
        except Exception:
            pass
    if hasattr(pb, "select_set"):
        try:
            pb.select_set(state)
            return
        except Exception:
            pass
    if hasattr(pb, "bone") and hasattr(pb.bone, "select_set"):
        try:
            pb.bone.select_set(state)
            return
        except Exception:
            pass


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
        try:
            bpy.ops.pose.select_all(action='DESELECT')
        except Exception:
            for pb in ctx.active_object.pose.bones:
                _set_bone_selection(pb, False)

        count = 0
        last_pb = None
        for pb in ctx.active_object.pose.bones:
            if core.has_jiggle(pb):
                _set_bone_selection(pb, True)
                last_pb = pb
                count += 1

        if last_pb:
            try:
                ctx.active_object.data.bones.active = last_pb.bone
            except Exception:
                pass

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
        arm = ctx.active_object.data
        if hasattr(arm, "jiggle_layers"):
            arm.jiggle_layers.clear()
            arm.jiggle_layer_index = 0
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


class JIGGLE_OT_select_layer(bpy.types.Operator):
    bl_idname = "jiggle.select_layer"
    bl_label = "Select Layer Bones"
    bl_description = "Select all bones belonging to this Jiggle Layer"
    bl_options = {'REGISTER', 'UNDO'}

    layer_name: bpy.props.StringProperty(name="Layer Name", default="Main")

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE' and ctx.mode == 'POSE')

    def execute(self, ctx):
        try:
            bpy.ops.pose.select_all(action='DESELECT')
        except Exception:
            for pb in ctx.active_object.pose.bones:
                _set_bone_selection(pb, False)

        count = 0
        last_pb = None
        for pb in ctx.active_object.pose.bones:
            if core.has_jiggle(pb) and core.get_bone_layer(pb) == self.layer_name:
                _set_bone_selection(pb, True)
                last_pb = pb
                count += 1

        if last_pb:
            try:
                ctx.active_object.data.bones.active = last_pb.bone
            except Exception:
                pass

        self.report({'INFO'}, f"Selected {count} bone(s) in layer '{self.layer_name}'")
        return {'FINISHED'}


class JIGGLE_OT_toggle_layer_mute(bpy.types.Operator):
    bl_idname = "jiggle.toggle_layer_mute"
    bl_label = "Toggle Layer Mute"
    bl_description = "Enable or mute simulation for all bones in this layer"
    bl_options = {'REGISTER', 'UNDO'}

    layer_name: bpy.props.StringProperty(name="Layer Name", default="Main")

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE' and ctx.mode == 'POSE')

    def execute(self, ctx):
        new_muted = core.toggle_layer_mute(ctx.active_object, self.layer_name)
        state_str = "Muted" if new_muted else "Unmuted"
        self.report({'INFO'}, f"Layer '{self.layer_name}' {state_str}")
        return {'FINISHED'}


class JIGGLE_OT_assign_layer(bpy.types.Operator):
    bl_idname = "jiggle.assign_layer"
    bl_label = "Assign to Layer"
    bl_description = "Assign selected jiggle bone(s) to this layer"
    bl_options = {'REGISTER', 'UNDO'}

    layer_name: bpy.props.StringProperty(name="Layer Name", default="Main")

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.selected_pose_bones)

    def execute(self, ctx):
        count = 0
        for pb in ctx.selected_pose_bones:
            if core.has_jiggle(pb):
                core.set_bone_layer(pb, self.layer_name)
                count += 1
        core.sync_armature_layers(ctx.active_object)
        arm = ctx.active_object.data
        if hasattr(arm, "jiggle_layers"):
            for i, item in enumerate(arm.jiggle_layers):
                if item.name == self.layer_name:
                    arm.jiggle_layer_index = i
                    break
        self.report({'INFO'}, f"Assigned {count} bone(s) to layer '{self.layer_name}'")
        return {'FINISHED'}


class JIGGLE_OT_add_layer(bpy.types.Operator):
    bl_idname = "jiggle.add_layer"
    bl_label = "Add Jiggle Layer"
    bl_description = "Add a new Jiggle Layer"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="Layer Name", default="")

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE' and ctx.mode == 'POSE')

    def execute(self, ctx):
        arm = ctx.active_object.data
        name = self.name.strip()
        if not name:
            existing = {item.name for item in arm.jiggle_layers}
            idx = 1
            while f"Layer {idx}" in existing:
                idx += 1
            name = f"Layer {idx}"

        item = arm.jiggle_layers.add()
        item.name = name
        item["prev_name"] = name
        arm.jiggle_layer_index = len(arm.jiggle_layers) - 1

        if ctx.selected_pose_bones:
            count = 0
            for pb in ctx.selected_pose_bones:
                if core.has_jiggle(pb):
                    core.set_bone_layer(pb, name)
                    count += 1
            if count > 0:
                self.report({'INFO'}, f"Created layer '{name}' with {count} bone(s)")
                return {'FINISHED'}

        self.report({'INFO'}, f"Added layer '{name}'")
        return {'FINISHED'}


class JIGGLE_OT_rename_layer(bpy.types.Operator):
    bl_idname = "jiggle.rename_layer"
    bl_label = "Rename Jiggle Layer"
    bl_description = "Rename this Jiggle Layer and update all associated bones"
    bl_options = {'REGISTER', 'UNDO'}

    old_name: bpy.props.StringProperty(name="Old Name", default="")
    new_name: bpy.props.StringProperty(name="New Name", default="")

    def invoke(self, ctx, event):
        arm = ctx.active_object.data
        if not self.old_name and 0 <= arm.jiggle_layer_index < len(arm.jiggle_layers):
            self.old_name = arm.jiggle_layers[arm.jiggle_layer_index].name
        self.new_name = self.old_name
        return ctx.window_manager.invoke_props_dialog(self)

    def draw(self, ctx):
        layout = self.layout
        layout.prop(self, "new_name", text="Name")

    def execute(self, ctx):
        new_name = self.new_name.strip()
        if not new_name or new_name == self.old_name:
            return {'CANCELLED'}
        arm = ctx.active_object.data
        count = core.rename_layer(ctx.active_object, self.old_name, new_name)
        for item in arm.jiggle_layers:
            if item.name == self.old_name:
                item.name = new_name
                item["prev_name"] = new_name
        self.report({'INFO'}, f"Renamed layer '{self.old_name}' to '{new_name}' ({count} bones)")
        return {'FINISHED'}


class JIGGLE_OT_remove_layer(bpy.types.Operator):
    bl_idname = "jiggle.remove_layer"
    bl_label = "Remove Layer"
    bl_description = "Remove jiggle physics from all bones in this layer"
    bl_options = {'REGISTER', 'UNDO'}

    layer_name: bpy.props.StringProperty(name="Layer Name", default="")

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE' and ctx.mode == 'POSE')

    def execute(self, ctx):
        arm = ctx.active_object.data
        target_name = self.layer_name
        if not target_name and 0 <= arm.jiggle_layer_index < len(arm.jiggle_layers):
            target_name = arm.jiggle_layers[arm.jiggle_layer_index].name
        if not target_name:
            return {'CANCELLED'}

        count = core.remove_layer_bones(ctx.active_object, target_name)
        idx_to_remove = None
        for i, item in enumerate(arm.jiggle_layers):
            if item.name == target_name:
                idx_to_remove = i
                break
        if idx_to_remove is not None:
            arm.jiggle_layers.remove(idx_to_remove)
            arm.jiggle_layer_index = max(0, min(arm.jiggle_layer_index, len(arm.jiggle_layers) - 1))

        self.report({'INFO'}, f"Removed {count} bone(s) from layer '{target_name}'")
        return {'FINISHED'}


class JIGGLE_OT_apply_layer_preset(bpy.types.Operator):
    bl_idname = "jiggle.apply_layer_preset"
    bl_label = "Apply Preset to Layer"
    bl_description = "Apply preset settings to all bones in this layer"
    bl_options = {'REGISTER', 'UNDO'}

    layer_name: bpy.props.StringProperty(name="Layer Name", default="Main")
    preset_name: bpy.props.StringProperty(name="Preset Name", default="Medium")

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE' and ctx.mode == 'POSE')

    def execute(self, ctx):
        count = 0
        for pb in ctx.active_object.pose.bones:
            if core.has_jiggle(pb) and core.get_bone_layer(pb) == self.layer_name:
                core.apply_preset_to_bone(pb, self.preset_name)
                count += 1
        self.report({'INFO'}, f"Applied '{self.preset_name}' to {count} bone(s) in layer '{self.layer_name}'")
        return {'FINISHED'}


class JIGGLE_OT_copy_to_selected(bpy.types.Operator):
    bl_idname = "jiggle.copy_to_selected"
    bl_label = "Copy to Selected"
    bl_description = "Copy stiffness, damping, gravity, and layer from active bone to all selected bones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE'
                and ctx.mode == 'POSE' and ctx.active_pose_bone
                and len(ctx.selected_pose_bones) > 1)

    def execute(self, ctx):
        src = ctx.active_pose_bone
        stiff = src.get("jiggle_stiffness", 0.35)
        damp = src.get("jiggle_damping", 0.35)
        grav = src.get("jiggle_gravity", 0.30)
        layer = core.get_bone_layer(src)

        count = 0
        for pb in ctx.selected_pose_bones:
            if pb != src and core.has_jiggle(pb):
                pb["jiggle_stiffness"] = stiff
                pb["jiggle_damping"] = damp
                pb["jiggle_gravity"] = grav
                core.set_bone_layer(pb, layer)
                count += 1
        self.report({'INFO'}, f"Copied settings to {count} selected bone(s)")
        return {'FINISHED'}


class JIGGLE_OT_sync_layers(bpy.types.Operator):
    bl_idname = "jiggle.sync_layers"
    bl_label = "Sync Layers"
    bl_description = "Synchronize layer list with bones on active armature"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return (ctx.active_object and ctx.active_object.type == 'ARMATURE' and ctx.mode == 'POSE')

    def execute(self, ctx):
        core.sync_armature_layers(ctx.active_object)
        self.report({'INFO'}, "Jiggle layers synchronized")
        return {'FINISHED'}


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
    JIGGLE_OT_select_layer,
    JIGGLE_OT_toggle_layer_mute,
    JIGGLE_OT_assign_layer,
    JIGGLE_OT_add_layer,
    JIGGLE_OT_rename_layer,
    JIGGLE_OT_remove_layer,
    JIGGLE_OT_apply_layer_preset,
    JIGGLE_OT_copy_to_selected,
    JIGGLE_OT_sync_layers,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    JIGGLE_OT_realtime._is_running = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
