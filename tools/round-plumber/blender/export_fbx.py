"""Convert public/round-plumber.glb into Roblox-ready FBX files with Blender.

Run with a Python that has the `bpy` module (Blender as a Python module, e.g.
`pip install bpy` on Python 3.11) or inside Blender:
    python3 blender/export_fbx.py
    blender -b -P blender/export_fbx.py

Writes to tools/round-plumber/exports/fbx/:
    RoundPlumber_Rig.fbx          skinned meshes + armature + embedded texture (no animation)
    RoundPlumber_AllClips.fbx     armature + every clip as its own take (Unity / Godot / Blender)
    anim/<Clip>.fbx               armature + one clip each (Roblox: Animation Editor > Import > From FBX Animation)
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
GLB = os.path.normpath(os.path.join(ROOT, '..', '..', 'public', 'round-plumber.glb'))
OUT = os.path.join(ROOT, 'exports', 'fbx')
FPS = 30

COMMON = dict(
    use_selection=True,
    add_leaf_bones=False,
    apply_scale_options='FBX_SCALE_UNITS',
    axis_forward='-Z',
    axis_up='Y',
    primary_bone_axis='Y',
    secondary_bone_axis='X',
    use_armature_deform_only=False,
    bake_anim_simplify_factor=0.5,
)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = FPS


def import_glb():
    bpy.ops.import_scene.gltf(filepath=GLB)
    arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    return arm, meshes


def rest_pose(arm):
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)


def clip_info():
    with open(os.path.join(ROOT, 'exports', 'clips.json')) as f:
        return json.load(f)


def assign(arm, action):
    ad = arm.animation_data or arm.animation_data_create()
    for track in list(ad.nla_tracks):
        ad.nla_tracks.remove(track)
    ad.action = None
    rest_pose(arm)  # bones a clip does not animate must not inherit the previous clip's pose
    ad.action = action
    if action is not None and hasattr(ad, 'action_slot') and getattr(action, 'slots', None):
        ad.action_slot = action.slots[0]


def select(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def clip_names():
    return [c['name'] for c in clip_info()]


def main():
    os.makedirs(os.path.join(OUT, 'anim'), exist_ok=True)
    reset()
    arm, meshes = import_glb()
    actions = {a.name: a for a in bpy.data.actions}
    wanted = clip_names()
    # the glTF importer may suffix action names with the object name
    by_clip = {}
    for name in wanted:
        match = actions.get(name) or next((a for n, a in actions.items() if n.startswith(name + '_') or n.startswith(name + '.')), None)
        if match is None:
            raise SystemExit(f'action for clip {name} not found; have {sorted(actions)}')
        by_clip[name] = match
    # remove animation from meshes (shape keys / object actions) - only the armature animates
    for m in meshes:
        if m.animation_data:
            m.animation_data_clear()

    # 1) rig + meshes, no animation
    assign(arm, None)
    arm.data.pose_position = 'REST'
    select([arm, *meshes])
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, 'RoundPlumber_Rig.fbx'), object_types={'ARMATURE', 'MESH'},
                             bake_anim=False, path_mode='COPY', embed_textures=True, mesh_smooth_type='FACE', **COMMON)
    arm.data.pose_position = 'POSE'

    # 2) one FBX per clip (armature only)
    scene = bpy.context.scene
    for name, action in by_clip.items():
        assign(arm, action)
        start, end = action.frame_range
        scene.frame_start, scene.frame_end = int(round(start)), int(round(end))
        select([arm])
        bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, 'anim', f'{name}.fbx'), object_types={'ARMATURE'},
                                 bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                                 bake_anim_force_startend_keying=True, bake_anim_step=1.0, **COMMON)

    # 3) all clips as takes
    for action in by_clip.values():
        action.use_fake_user = True
    assign(arm, next(iter(by_clip.values())))
    select([arm, *meshes])
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, 'RoundPlumber_AllClips.fbx'), object_types={'ARMATURE', 'MESH'},
                             bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, path_mode='COPY', embed_textures=True,
                             mesh_smooth_type='FACE', **COMMON)
    print(f'exported rig, {len(by_clip)} clip files and the all-clips file to {OUT}')


if __name__ == '__main__':
    main()
