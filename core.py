import bpy
import mathutils
import json
import os
import time
from bpy.app.handlers import persistent

CONSTRAINT_NAME = "Jiggle_DampedTrack"
COLLECTION_NAME = "_JigglePhysics"

DEFAULT_PRESETS = {
    'Soft':   {"jiggle_stiffness": 0.15, "jiggle_damping": 0.20, "jiggle_gravity": 0.50},
    'Medium': {"jiggle_stiffness": 0.35, "jiggle_damping": 0.35, "jiggle_gravity": 0.30},
    'Firm':   {"jiggle_stiffness": 0.70, "jiggle_damping": 0.50, "jiggle_gravity": 0.10},
}

_is_simulating = False
_last_time = 0.0


def _preset_path():
    config_dir = bpy.utils.user_resource('CONFIG', path="exea_jiggle", create=True)
    user_file = os.path.join(config_dir, "user_presets.json")
    legacy_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "user_presets.json")
    if not os.path.exists(user_file) and os.path.exists(legacy_file):
        try:
            import shutil
            shutil.copy2(legacy_file, user_file)
        except Exception:
            pass
    return user_file


def load_user_presets():
    path = _preset_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_user_presets(data):
    with open(_preset_path(), 'w') as f:
        json.dump(data, f, indent=2)


def get_all_presets():
    p = dict(DEFAULT_PRESETS)
    p.update(load_user_presets())
    return p


def is_default_preset(name):
    return name in DEFAULT_PRESETS


def save_preset(name, stiffness, damping, gravity):
    user = load_user_presets()
    user[name] = {
        "jiggle_stiffness": round(stiffness, 4),
        "jiggle_damping": round(damping, 4),
        "jiggle_gravity": round(gravity, 4),
    }
    save_user_presets(user)


def delete_preset(name):
    if is_default_preset(name):
        return False
    user = load_user_presets()
    if name in user:
        del user[name]
        save_user_presets(user)
        return True
    return False


def _collection():
    col = bpy.data.collections.get(COLLECTION_NAME)
    if not col:
        col = bpy.data.collections.new(COLLECTION_NAME)
    scene_col = bpy.context.scene.collection
    if col.name not in scene_col.children:
        scene_col.children.link(col)
    col.hide_viewport = True
    col.hide_render = True
    return col


def has_jiggle(pb):
    con = pb.constraints.get(CONSTRAINT_NAME)
    return con is not None and con.target is not None


def _bone_local_mat(ev_pb, ev_parent):
    rest_local = ev_parent.bone.matrix_local.inverted() @ ev_pb.bone.matrix_local
    return rest_local @ ev_pb.matrix_basis


def get_target_tail(pb, depsgraph):
    arm = pb.id_data
    ev_arm = depsgraph.id_eval_get(arm)
    ev_pb = ev_arm.pose.bones.get(pb.name)
    if not ev_pb:
        return None, None
    par = ev_pb.parent
    if par:
        mat = par.matrix @ _bone_local_mat(ev_pb, par)
    else:
        mat = ev_pb.bone.matrix_local @ ev_pb.matrix_basis
    world = ev_arm.matrix_world @ mat
    head = world @ mathutils.Vector((0, 0, 0))
    tail = world @ mathutils.Vector((0, ev_pb.length, 0))
    return head, tail


DEFAULT_LAYER = "Main"


def guess_layer_from_name(bone_name):
    name_lower = bone_name.lower()
    if any(k in name_lower for k in ("hair", "bang", "fringe", "ponytail", "braid", "ahoge")):
        return "Hair"
    if any(k in name_lower for k in ("tail", "shippo")):
        return "Tail"
    if any(k in name_lower for k in ("cloth", "skirt", "dress", "sleeve", "cape", "ribbon", "belt", "coat")):
        return "Clothes"
    if any(k in name_lower for k in ("ear", "mimi")):
        return "Ears"
    if any(k in name_lower for k in ("breast", "boob", "chest", "bust")):
        return "Chest"
    return DEFAULT_LAYER


def get_bone_layer(pb):
    return pb.get("jiggle_layer", DEFAULT_LAYER)


def set_bone_layer(pb, layer_name):
    lname = layer_name.strip() if (layer_name and layer_name.strip()) else DEFAULT_LAYER
    pb["jiggle_layer"] = lname


def get_armature_layers(armature):
    layers = {}
    for pb in armature.pose.bones:
        if has_jiggle(pb):
            lname = get_bone_layer(pb)
            if lname not in layers:
                layers[lname] = {"bones": [], "muted": True}
            layers[lname]["bones"].append(pb)
            con = pb.constraints.get(CONSTRAINT_NAME)
            if con and not con.mute:
                layers[lname]["muted"] = False
    return layers


def set_layer_mute(armature, layer_name, mute_state):
    for pb in armature.pose.bones:
        if has_jiggle(pb) and get_bone_layer(pb) == layer_name:
            con = pb.constraints.get(CONSTRAINT_NAME)
            if con:
                con.mute = mute_state


def toggle_layer_mute(armature, layer_name):
    layers = get_armature_layers(armature)
    curr_muted = layers.get(layer_name, {}).get("muted", False)
    set_layer_mute(armature, layer_name, not curr_muted)
    return not curr_muted


def remove_layer_bones(armature, layer_name):
    count = 0
    for pb in list(armature.pose.bones):
        if has_jiggle(pb) and get_bone_layer(pb) == layer_name:
            cleanup_bone(pb)
            count += 1
    return count


def rename_layer(armature, old_name, new_name):
    new_name = new_name.strip() if (new_name and new_name.strip()) else DEFAULT_LAYER
    if old_name == new_name:
        return 0
    count = 0
    for pb in armature.pose.bones:
        if has_jiggle(pb) and get_bone_layer(pb) == old_name:
            set_bone_layer(pb, new_name)
            count += 1
    return count


def sync_armature_layers(armature):
    if not armature or armature.type != 'ARMATURE':
        return
    arm = armature.data
    if not hasattr(arm, "jiggle_layers"):
        return
    existing_items = {item.name: item for item in arm.jiggle_layers}
    bone_layers = get_armature_layers(armature)

    for lname, ldata in bone_layers.items():
        if lname not in existing_items:
            item = arm.jiggle_layers.add()
            item["prev_name"] = lname
            item.name = lname
            if ldata["bones"]:
                first_b = ldata["bones"][0]
                item.stiffness = first_b.get("jiggle_stiffness", 0.35)
                item.damping = first_b.get("jiggle_damping", 0.35)
                item.gravity = first_b.get("jiggle_gravity", 0.30)
    if len(arm.jiggle_layers) > 0 and arm.jiggle_layer_index >= len(arm.jiggle_layers):
        arm.jiggle_layer_index = max(0, len(arm.jiggle_layers) - 1)


def find_chain_root(selected_bones, active_pb=None):
    if not selected_bones:
        return active_pb
    sel_set = set(selected_bones)
    if len(sel_set) == 1:
        return list(sel_set)[0]
    roots = [b for b in selected_bones if (not b.parent) or (b.parent not in sel_set)]
    if roots:
        if active_pb and active_pb in sel_set:
            for r in roots:
                curr = active_pb
                while curr:
                    if curr == r:
                        return r
                    curr = curr.parent
        return roots[0]
    return active_pb or selected_bones[0]


def setup_bone(pb, layer_name=None):
    arm = pb.id_data
    col = _collection()
    name = f"_jig_{arm.name}_{pb.name}"
    empty = bpy.data.objects.get(name)
    if not empty:
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = 'SPHERE'
        empty.empty_display_size = 0.02
        col.objects.link(empty)
    wm = arm.matrix_world @ pb.matrix
    empty.location = wm @ mathutils.Vector((0, pb.length, 0))
    empty.hide_viewport = True
    empty.hide_render = True
    for k in ("vel_x", "vel_y", "vel_z"):
        empty[k] = 0.0
    con = pb.constraints.get(CONSTRAINT_NAME)
    if not con:
        con = pb.constraints.new('DAMPED_TRACK')
        con.name = CONSTRAINT_NAME
    con.target = empty
    con.track_axis = 'TRACK_Y'

    if layer_name:
        set_bone_layer(pb, layer_name)
    elif "jiggle_layer" not in pb:
        set_bone_layer(pb, guess_layer_from_name(pb.name))

    defaults = {"jiggle_stiffness": 0.35, "jiggle_damping": 0.35, "jiggle_gravity": 0.30}
    for prop, val in defaults.items():
        if prop not in pb:
            pb[prop] = val
            try:
                pb.id_properties_ensure()
                ui = pb.id_properties_ui(prop)
                if "gravity" in prop:
                    ui.update(min=0.0, max=2.0, default=val, soft_min=0.0, soft_max=1.0)
                else:
                    ui.update(min=0.0, max=1.0, default=val)
            except Exception:
                pass
    return empty


def cleanup_bone(pb):
    con = pb.constraints.get(CONSTRAINT_NAME)
    if con:
        target = con.target
        pb.constraints.remove(con)
        if target and target.name in bpy.data.objects:
            bpy.data.objects.remove(target, do_unlink=True)
    for prop in ("jiggle_stiffness", "jiggle_damping", "jiggle_gravity", "jiggle_layer"):
        if prop in pb:
            del pb[prop]


def apply_preset_to_bone(pb, preset_name):
    presets = get_all_presets()
    vals = presets.get(preset_name)
    if vals:
        for prop, val in vals.items():
            pb[prop] = val


def reset_bone(pb, depsgraph):
    con = pb.constraints.get(CONSTRAINT_NAME)
    if not con or not con.target:
        return
    empty = con.target
    _, tail = get_target_tail(pb, depsgraph)
    if tail:
        empty.location = tail
    for k in ("vel_x", "vel_y", "vel_z"):
        empty[k] = 0.0


def get_chain_bones(root_pb):
    chain = [root_pb]
    for child in root_pb.children:
        chain.extend(get_chain_bones(child))
    return chain


def setup_chain(root_pb, falloff=0.85, base_preset='Medium', layer_name=None):
    chain = get_chain_bones(root_pb)
    if not layer_name:
        layer_name = guess_layer_from_name(root_pb.name)
    base = DEFAULT_PRESETS.get(base_preset, DEFAULT_PRESETS['Medium'])
    for i, pb in enumerate(chain):
        setup_bone(pb, layer_name=layer_name)
        factor = falloff ** i
        pb["jiggle_stiffness"] = round(base["jiggle_stiffness"] * factor, 4)
        pb["jiggle_damping"] = round(max(0.05, base["jiggle_damping"] * factor), 4)
        pb["jiggle_gravity"] = base["jiggle_gravity"]
    return chain


def _bone_depth(pb):
    d = 0
    p = pb.parent
    while p:
        d += 1
        p = p.parent
    return d


def _find_chains_and_singles(armature):
    jiggle_bones = set()
    for pb in armature.pose.bones:
        if has_jiggle(pb):
            jiggle_bones.add(pb.name)

    in_chain = set()
    chains = []

    roots = []
    for pb in armature.pose.bones:
        if pb.name not in jiggle_bones:
            continue
        is_root = (not pb.parent) or (pb.parent.name not in jiggle_bones)
        if is_root:
            roots.append(pb)

    for root in roots:
        chain = _walk_linear_chain(root, jiggle_bones)
        if len(chain) > 1:
            chains.append(chain)
            for b in chain:
                in_chain.add(b.name)

    singles = [armature.pose.bones[n] for n in jiggle_bones if n not in in_chain]
    return chains, singles


def _walk_linear_chain(pb, jiggle_set):
    chain = [pb]
    current = pb
    while True:
        jiggle_children = [c for c in current.children if c.name in jiggle_set]
        if len(jiggle_children) == 0:
            break
        elif len(jiggle_children) == 1:
            chain.append(jiggle_children[0])
            current = jiggle_children[0]
        else:
            chain.append(jiggle_children[0])
            current = jiggle_children[0]
            break
    return chain


def _get_chain_goals(chain, depsgraph):
    arm = chain[0].id_data
    ev_arm = depsgraph.id_eval_get(arm)

    bone_mats = []
    joints = []

    for i, pb in enumerate(chain):
        ev_pb = ev_arm.pose.bones.get(pb.name)
        if not ev_pb:
            return []

        if i == 0:
            par = ev_pb.parent
            if par:
                bone_mat = par.matrix @ _bone_local_mat(ev_pb, par)
            else:
                bone_mat = ev_pb.bone.matrix_local @ ev_pb.matrix_basis
        else:
            prev_ev = ev_arm.pose.bones.get(chain[i - 1].name)
            bone_mat = bone_mats[i - 1] @ _bone_local_mat(ev_pb, prev_ev)

        bone_mats.append(bone_mat)
        world = ev_arm.matrix_world @ bone_mat
        head = world @ mathutils.Vector((0, 0, 0))
        tail = world @ mathutils.Vector((0, ev_pb.length, 0))
        joints.append((head, tail))

    return joints


def simulate_bone(pb, depsgraph, dt):
    con = pb.constraints.get(CONSTRAINT_NAME)
    if not con or not con.target or con.mute:
        return
    empty = con.target
    head, target = get_target_tail(pb, depsgraph)
    if head is None:
        return

    vel = mathutils.Vector((
        empty.get("vel_x", 0.0),
        empty.get("vel_y", 0.0),
        empty.get("vel_z", 0.0),
    ))
    pos = empty.location.copy()

    k = 50.0 + pb.get("jiggle_stiffness", 0.35) * 450.0
    c = 1.0 + pb.get("jiggle_damping", 0.35) * 24.0
    g = pb.get("jiggle_gravity", 0.30) * 2.0
    grav = mathutils.Vector((0, 0, -g))

    steps = max(1, int(dt * 120))
    sub_dt = dt / steps

    for _ in range(steps):
        force = (target - pos) * k - vel * c + grav
        vel += force * sub_dt
        pos += vel * sub_dt

    d = pos - head
    if d.length > 1e-6:
        pos = head + d.normalized() * pb.length

    empty.location = pos
    empty["vel_x"] = vel.x
    empty["vel_y"] = vel.y
    empty["vel_z"] = vel.z


def simulate_chain(chain, depsgraph, dt):
    if all(pb.constraints.get(CONSTRAINT_NAME) and pb.constraints[CONSTRAINT_NAME].mute for pb in chain):
        return

    goals = _get_chain_goals(chain, depsgraph)
    if not goals:
        return

    pin = goals[0][0].copy()

    particles = [pin]
    vels = [mathutils.Vector((0, 0, 0))]
    for pb in chain:
        empty = pb.constraints[CONSTRAINT_NAME].target
        particles.append(empty.location.copy())
        vels.append(mathutils.Vector((
            empty.get("vel_x", 0.0),
            empty.get("vel_y", 0.0),
            empty.get("vel_z", 0.0),
        )))

    steps = max(1, int(dt * 120))
    sub_dt = dt / steps

    for _ in range(steps):
        for i in range(1, len(particles)):
            pb = chain[i - 1]
            goal = goals[i - 1][1]

            stiff = pb.get("jiggle_stiffness", 0.35)
            damp = pb.get("jiggle_damping", 0.35)
            grav_val = pb.get("jiggle_gravity", 0.3)

            k = 50.0 + stiff * 450.0
            c = 1.0 + damp * 24.0
            g = grav_val * 2.0

            force = (goal - particles[i]) * k - vels[i] * c + mathutils.Vector((0, 0, -g))
            vels[i] += force * sub_dt
            particles[i] += vels[i] * sub_dt

        particles[0] = pin
        for i in range(1, len(particles)):
            bone_len = chain[i - 1].length
            delta = particles[i] - particles[i - 1]
            dist = delta.length
            if dist > 1e-8:
                correction = delta.normalized() * bone_len
                particles[i] = particles[i - 1] + correction
                proj = vels[i].dot(delta.normalized())
                tangent = vels[i] - delta.normalized() * proj
                radial = delta.normalized() * max(proj, 0)
                vels[i] = tangent + radial
            else:
                goal_dir = goals[i - 1][1] - goals[i - 1][0]
                if goal_dir.length > 1e-8:
                    particles[i] = particles[i - 1] + goal_dir.normalized() * bone_len
                else:
                    particles[i] = particles[i - 1] + mathutils.Vector((0, 0, -bone_len))
                vels[i] = mathutils.Vector((0, 0, 0))

    for i, pb in enumerate(chain):
        empty = pb.constraints[CONSTRAINT_NAME].target
        empty.location = particles[i + 1]
        empty["vel_x"] = vels[i + 1].x
        empty["vel_y"] = vels[i + 1].y
        empty["vel_z"] = vels[i + 1].z


def simulate_all(scene, depsgraph, dt, is_reset=False):
    global _is_simulating
    if _is_simulating:
        return
    _is_simulating = True
    try:
        for obj in scene.objects:
            if obj.type != 'ARMATURE':
                continue

            if is_reset:
                for pb in obj.pose.bones:
                    if has_jiggle(pb):
                        reset_bone(pb, depsgraph)
                continue

            chains, singles = _find_chains_and_singles(obj)

            for chain in chains:
                simulate_chain(chain, depsgraph, dt)

            singles.sort(key=_bone_depth)
            for pb in singles:
                simulate_bone(pb, depsgraph, dt)
    finally:
        _is_simulating = False


_prev_frame = None

@persistent
def _on_frame_change(scene, depsgraph):
    from . import operators
    if operators.JIGGLE_OT_realtime._is_running:
        return
    global _prev_frame
    cur = scene.frame_current
    if _prev_frame is None:
        _prev_frame = cur
        return
    frame_diff = cur - _prev_frame
    fps = scene.render.fps / scene.render.fps_base
    base_dt = 1.0 / fps if fps > 0 else 0.016
    is_reset = (frame_diff <= 0) or (cur == scene.frame_start) or (frame_diff > 10)
    dt = min(max(frame_diff * base_dt, 0.001), 0.2) if not is_reset else 0.0
    _prev_frame = cur
    simulate_all(scene, depsgraph, dt, is_reset)


@persistent
def _on_load(dummy):
    global _prev_frame
    _prev_frame = None


def register():
    if _on_frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_on_frame_change)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_on_frame_change)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
