"""Re-imports the exported FBX files and checks them against the source .glb:
the world position of key bones must match at sampled frames of every clip.
    python3 blender/verify_fbx.py
"""
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_fbx as ex  # noqa: E402

BONES = ['Hand_R', 'Hand_L', 'Head', 'Nozzle', 'Flashlight', 'Eye_L', 'MouthLower', 'Foot_L', 'Hose05', 'GrabPoint', 'Index2_L', 'Cap']


FACE = {'Eye_L', 'Eye_R', 'Pupil_L', 'LidUpper_L', 'LidLower_R', 'BrowIn_L', 'BrowOut_R', 'MouthLower', 'MouthCorner_L', 'Cheek_R'}


def sample(arm, frames, bones):
    ex.rest_pose(arm)
    out = {}
    for f in frames:
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        out[f] = {b: (arm.matrix_world @ arm.pose.bones[b].head).copy() for b in bones}
    return out


def main():
    info = {c['name']: c for c in ex.clip_info()}
    clips = list(info)
    bones = lambda n: sorted(FACE) if info[n]['faceOnly'] else BONES
    ex.reset()
    arm, _ = ex.import_glb()
    actions = {a.name: a for a in bpy.data.actions}
    ref = {}
    for name in clips:
        act = actions.get(name) or next(a for n, a in actions.items() if n.startswith(name))
        ex.assign(arm, act)
        s, e = (int(round(v)) for v in act.frame_range)
        ref[name] = (s, e, sample(arm, sorted({s, (s + e) // 2, e - 1}), bones(name)))
    worst = (0, None)
    for name in clips:
        ex.reset()
        bpy.ops.import_scene.fbx(filepath=os.path.join(ex.OUT, 'anim', f'{name}.fbx'))
        arm2 = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
        act2 = arm2.animation_data.action
        s2, e2 = (int(round(v)) for v in act2.frame_range)
        s, e, frames = ref[name]
        got = sample(arm2, [s2 + (f - s) for f in frames], bones(name))
        for f, pos in frames.items():
            for b, p in pos.items():
                d = (got[s2 + (f - s)][b] - p).length
                if d > worst[0]:
                    worst = (d, f'{name} frame {f} {b}')
    print(f'worst bone position difference GLB vs FBX: {worst[0] * 1000:.2f} mm ({worst[1]})')
    if worst[0] > 0.005:
        raise SystemExit('FBX does not match the GLB')


if __name__ == '__main__':
    main()
