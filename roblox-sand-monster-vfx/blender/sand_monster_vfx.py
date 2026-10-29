"""
Sand Monster VFX -> Roblox
==========================
Blender 4.2+ (getestet mit 4.5 LTS)

Baut prozedural einen Sand-Golem, der brüllt und danach von oben nach unten zu
Sand zerfällt (Sandkörner + Staubwolken + wachsender Sandhaufen). Das Ganze wird
mit Cycles gerendert und zu Roblox-tauglichen Flipbook-Spritesheets
(1024x1024, Grid 8x8 / 4x4) zusammengesetzt. Zusätzlich entstehen:

  * SandBurst_8x8.png      - nur die Sandexplosion (ohne Körper), als Overlay für
                             ein echtes 3D-Modell, das in Roblox zerbröselt
  * SandMonster_Rise_8x8   - rückwärts: Golem setzt sich aus Sand zusammen
  * SandGrain.png / SandDust.png - Einzeltexturen für Roblox-ParticleEmitter
  * SandGolem.fbx          - der Golem als 16 MeshParts (Kopf, Arme, ...)
  * vfx_meta.json          - Timing / Größen für das Luau-Modul

Kommandozeile (Hintergrund-Render):
  blender -b -P sand_monster_vfx.py -- --out ./output
  blender -b -P sand_monster_vfx.py -- --out ./output --quick          # schneller Test
  blender -b -P sand_monster_vfx.py -- --build-only --save SandMonster.blend

In der Blender-Oberfläche: Scripting-Tab > Öffnen > "Run Script" baut nur die
Szene auf (zum Anschauen / Anpassen, Leertaste spielt die Simulation ab).
"""

import argparse
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector, noise

# ----------------------------------------------------------------------------
# Einstellungen
# ----------------------------------------------------------------------------
FPS = 30
FRAME_END = 154          # Simulation läuft bis hier
ROAR_PEAK = 16           # Golem reißt die Arme hoch
COLLAPSE_START = 30      # Zerfall beginnt am Kopf ...
COLLAPSE_END = 76        # ... und erreicht hier die Füße
Z_TOP, Z_BOTTOM = 2.15, -0.15
N_BANDS = 8              # Höhenbänder für die Partikel-Emission

GRAIN_COUNT = 60000      # schwere Sandkörner (bleiben liegen)
CHUNK_COUNT = 2500       # größere Sandbrocken
DUST_COUNT = 90000       # feiner Staub (verweht + blendet aus)
TRAIL_COUNT = 2500       # Sand, der schon vor dem Zerfall vom Körper rieselt
SIM_TIMESTEP = 0.03      # < 1/FPS = leichte Zeitlupe, wirkt schwerer

SAND = {
    "dark": "#4e3a2b",
    "mid": "#8a6c52",
    "light": "#ad8f72",
    "pile": "#b89f84",
    "dust": "#a88c70",
}

RENDER_RES = 512         # pro Frame, wird für die Sheets herunterskaliert
SAMPLES = 16
ORTHO_SCALE = 3.9        # Bildbreite in Blender-Metern
CAM_TARGET = (0.0, 0.0, 1.1)
CAM_TILT = 14            # Grad nach unten

# name: (Render-Pass, Frames, Grid). Jedes Sheet ist 1024x1024.
SHEETS = {
    "SandMonster_Collapse_8x8": ("full", list(range(1, 128, 2)), 8),
    "SandMonster_Collapse_4x4": ("full", list(range(1, 128, 8)), 4),
    "SandBurst_8x8": ("burst", list(range(28, 155, 2)), 8),
}
SHEET_SIZE = 1024
SHEET_FPS = 15           # 64 Frames bei 15 fps = 4.27 s (Lifetime in Roblox)

# Golem-Skelett (Z oben, Golem schaut nach -Y, +X = seine linke Seite)
JOINTS = {
    "pelvis": (0.0, 0.00, 0.98),
    "spine": (0.0, 0.02, 1.20),
    "chest": (0.0, 0.04, 1.44),
    "clav": (0.0, 0.04, 1.55),
    "neck": (0.0, 0.00, 1.64),
    "head": (0.0, -0.05, 1.77),
    "headtop": (0.0, -0.06, 1.98),
    "shoulder.L": (0.30, 0.04, 1.56),
    "elbow.L": (0.47, 0.07, 1.22),
    "wrist.L": (0.53, 0.00, 0.93),
    "hand.L": (0.55, -0.04, 0.78),
    "hip.L": (0.14, 0.00, 0.96),
    "knee.L": (0.17, -0.04, 0.53),
    "ankle.L": (0.18, 0.03, 0.11),
    "toe.L": (0.19, -0.14, 0.04),
}
for _k, _v in list(JOINTS.items()):
    if _k.endswith(".L"):
        JOINTS[_k[:-2] + ".R"] = (-_v[0], _v[1], _v[2])

# (Knochen, Kopf-Gelenk, Spitzen-Gelenk, Elternknochen, Roblox-Teil)
BONES = [
    ("hips", "pelvis", "spine", None, "LowerTorso"),
    ("spine", "spine", "chest", "hips", "MidTorso"),
    ("chest", "chest", "neck", "spine", "UpperTorso"),
    ("head", "neck", "headtop", "chest", "Head"),
]
for _s, _side in (("L", "Left"), ("R", "Right")):
    BONES += [
        (f"clavicle.{_s}", "clav", f"shoulder.{_s}", "chest", "UpperTorso"),
        (f"upperarm.{_s}", f"shoulder.{_s}", f"elbow.{_s}", f"clavicle.{_s}", f"{_side}UpperArm"),
        (f"forearm.{_s}", f"elbow.{_s}", f"wrist.{_s}", f"upperarm.{_s}", f"{_side}LowerArm"),
        (f"hand.{_s}", f"wrist.{_s}", f"hand.{_s}", f"forearm.{_s}", f"{_side}Hand"),
        (f"thigh.{_s}", f"hip.{_s}", f"knee.{_s}", "hips", f"{_side}UpperLeg"),
        (f"shin.{_s}", f"knee.{_s}", f"ankle.{_s}", f"thigh.{_s}", f"{_side}LowerLeg"),
        (f"foot.{_s}", f"ankle.{_s}", f"toe.{_s}", f"shin.{_s}", f"{_side}Foot"),
    ]


def _mirror(spec):
    """Spiegelt eine Pose von .L auf .R (Y- und Z-Rotationen drehen sich um)."""
    out = dict(spec)
    for bone, rots in spec.items():
        if bone.endswith(".L"):
            out[bone[:-2] + ".R"] = [(a, -d if a in "YZ" else d) for a, d in rots]
    return out


# Posen: Rotationen im Armature-Raum (Achse, Grad). +X am Rumpf = nach vorn beugen,
# -Y am linken Oberarm = Arm seitlich heben, -X an Arm/Oberschenkel = nach vorn.
POSES = {
    1: _mirror({
        "chest": [("X", 6)], "head": [("X", 8)],
        "upperarm.L": [("Y", -8)], "forearm.L": [("X", -15)],
        "thigh.L": [("X", -6)], "shin.L": [("X", 10)],
    }),
    ROAR_PEAK: _mirror({
        "hips": [("X", -4)], "spine": [("X", -6)], "chest": [("X", -12)], "head": [("X", -24)],
        "upperarm.L": [("X", -35), ("Y", -52)], "forearm.L": [("X", -45)], "hand.L": [("X", -20)],
        "thigh.L": [("X", -14)], "shin.L": [("X", 24)], "foot.L": [("X", -10)],
    }),
    COLLAPSE_START: _mirror({
        "spine": [("X", -2)], "chest": [("X", -6)], "head": [("X", -14)],
        "upperarm.L": [("X", -30), ("Y", -45)], "forearm.L": [("X", -40)],
        "thigh.L": [("X", -16)], "shin.L": [("X", 28)], "foot.L": [("X", -12)],
    }),
    52: _mirror({
        "spine": [("X", 12)], "chest": [("X", 26)], "head": [("X", 34)],
        "upperarm.L": [("X", -12), ("Y", -18)], "forearm.L": [("X", -25)],
        "thigh.L": [("X", -30)], "shin.L": [("X", 52)], "foot.L": [("X", -22)],
    }),
    COLLAPSE_END: _mirror({
        "spine": [("X", 18)], "chest": [("X", 36)], "head": [("X", 40)],
        "upperarm.L": [("X", -5), ("Y", -10)], "forearm.L": [("X", -20)],
        "thigh.L": [("X", -40)], "shin.L": [("X", 70)], "foot.L": [("X", -30)],
    }),
}
# Wackeln am Höhepunkt des Brüllens
for _i, _f in enumerate(range(ROAR_PEAK + 2, COLLAPSE_START - 1, 3)):
    _s = 1 if _i % 2 == 0 else -1
    _p = {k: list(v) for k, v in POSES[ROAR_PEAK].items()}
    _p["chest"] = _p["chest"] + [("Z", 4 * _s)]
    _p["head"] = _p["head"] + [("Z", -6 * _s)]
    POSES[_f] = _p
# Höhe/Position des ganzen Rigs (sackt beim Zerfall in sich zusammen)
RIG_LOCATION = {1: (0, 0, 0), ROAR_PEAK: (0, 0, -0.04), COLLAPSE_START: (0, 0, -0.05),
                52: (0, -0.04, -0.17), COLLAPSE_END: (0, -0.06, -0.32)}


# ----------------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------------
def log(*a):
    print("[sand-vfx]", *a, flush=True)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def color(name, alpha=1.0):
    h = SAND[name].lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (alpha,)


def link_obj(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def reset_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for data in (bpy.data.objects, bpy.data.meshes, bpy.data.metaballs, bpy.data.armatures,
                 bpy.data.materials, bpy.data.particles, bpy.data.cameras, bpy.data.lights,
                 bpy.data.textures, bpy.data.actions, bpy.data.collections, bpy.data.worlds):
        for item in list(data):
            data.remove(item)


class Nodes:
    """Kleiner Helfer, um Shader-Nodes kompakt zu verdrahten."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()

    def new(self, type_, x=0, y=0, **inputs):
        n = self.nt.nodes.new(type_)
        n.location = (x, y)
        for k, v in inputs.items():
            self.set(n.inputs[k.replace("_", " ")], v)
        return n

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=None, x=0, y=0, clamp=False):
        n = self.new("ShaderNodeMath", x, y)
        n.operation = op
        n.use_clamp = clamp
        self.set(n.inputs[0], a)
        if b is not None:
            self.set(n.inputs[1], b)
        return n.outputs[0]

    def ramp(self, fac, stops, x=0, y=0):
        n = self.new("ShaderNodeValToRGB", x, y)
        els = n.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position, el.color = pos, col
        self.set(n.inputs["Fac"], fac)
        return n.outputs["Color"]

    def output(self, shader):
        out = self.new("ShaderNodeOutputMaterial", 1200, 0)
        self.nt.links.new(shader, out.inputs["Surface"])


def principled(nd, base, rough=1.0, x=600, y=0):
    b = nd.new("ShaderNodeBsdfPrincipled", x, y, Roughness=rough)
    nd.set(b.inputs["Base Color"], base)
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.15
    return b


# ----------------------------------------------------------------------------
# Golem
# ----------------------------------------------------------------------------
def build_golem_mesh():
    mb = bpy.data.metaballs.new("GolemMB")
    mb.resolution = mb.render_resolution = 0.02
    mb.threshold = 0.6
    obj = link_obj(bpy.data.objects.new("GolemMB", mb))
    k = 1 / 0.575  # Radius einer Metaball-Kugel -> tatsächliche Oberfläche (Steifigkeit 2, Schwelle 0.6)
    J = {n: Vector(p) for n, p in JOINTS.items()}

    def capsule(a, b, r):
        d = J[b] - J[a]
        el = mb.elements.new(type='CAPSULE')
        el.co = (J[a] + J[b]) / 2
        el.size_x = d.length / 2
        el.radius = r * k
        el.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())

    def blob(c, sx, sy, sz):
        el = mb.elements.new(type='ELLIPSOID')
        el.co = c
        el.radius = k
        el.size_x, el.size_y, el.size_z = sx, sy, sz

    blob((0, 0.04, 1.43), 0.30, 0.19, 0.23)   # Brust
    blob((0, 0.02, 1.18), 0.22, 0.16, 0.20)   # Bauch
    blob((0, 0.01, 0.97), 0.22, 0.15, 0.14)   # Becken
    blob((0, -0.05, 1.79), 0.11, 0.12, 0.13)  # Kopf
    capsule("clav", "neck", 0.09)
    for s in "LR":
        blob(J[f"shoulder.{s}"], 0.13, 0.12, 0.12)
        capsule(f"shoulder.{s}", f"elbow.{s}", 0.10)
        capsule(f"elbow.{s}", f"wrist.{s}", 0.09)
        capsule(f"wrist.{s}", f"hand.{s}", 0.07)
        capsule(f"hip.{s}", f"knee.{s}", 0.115)
        capsule(f"knee.{s}", f"ankle.{s}", 0.09)
        capsule(f"ankle.{s}", f"toe.{s}", 0.065)

    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    me.name = "SandGolem"
    bpy.data.objects.remove(obj)
    bpy.data.metaballs.remove(mb)

    body = link_obj(bpy.data.objects.new("SandGolem", me))
    tex = bpy.data.textures.new("SandLumps", 'CLOUDS')
    tex.noise_scale = 0.09
    tex.noise_depth = 2
    disp = body.modifiers.new("Lumps", 'DISPLACE')
    disp.texture = tex
    disp.strength = 0.035
    disp.texture_coords = 'LOCAL'
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(body.evaluated_get(dg))
    body.modifiers.clear()
    body.data = me2
    bpy.data.meshes.remove(me)
    bpy.data.textures.remove(tex)
    me2.name = "SandGolem"

    # Füße auf den Boden stellen
    co = np.empty(len(me2.vertices) * 3, dtype=np.float32)
    me2.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    dz = -co[:, 2].min()
    co[:, 2] += dz
    me2.vertices.foreach_set("co", co.ravel())
    for n, p in JOINTS.items():
        JOINTS[n] = (p[0], p[1], p[2] + dz)
    me2.polygons.foreach_set("use_smooth", [True] * len(me2.polygons))
    me2.update()
    log(f"Golem: {len(me2.vertices)} Vertices, {len(me2.polygons)} Faces")
    return body


def build_rig(body):
    arm_data = bpy.data.armatures.new("GolemRig")
    arm = link_obj(bpy.data.objects.new("GolemRig", arm_data))
    arm_data.display_type = 'STICK'
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for name, h, t, parent, _part in BONES:
        eb = arm_data.edit_bones.new(name)
        eb.head, eb.tail = JOINTS[h], JOINTS[t]
        if parent:
            eb.parent = arm_data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')

    # Gewichte: inverse Distanz zu den Knochen-Segmenten, die 2 nächsten Knochen
    me = body.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    dist = []
    for name, h, t, _p, _part in BONES:
        a, b = np.array(JOINTS[h]), np.array(JOINTS[t])
        ab = b - a
        tt = np.clip(((co - a) @ ab) / ab.dot(ab), 0, 1)
        dist.append(np.linalg.norm(a + tt[:, None] * ab - co, axis=1))
    w = 1 / (np.stack(dist, 1) + 0.02) ** 4
    top2 = np.argsort(-w, axis=1)[:, :2]
    rows = np.arange(len(co))[:, None]
    w2 = w[rows, top2]
    w2 /= w2.sum(1, keepdims=True)
    groups = [body.vertex_groups.new(name=b[0]) for b in BONES]
    for vi in range(len(co)):
        for j in range(2):
            groups[top2[vi, j]].add([vi], float(w2[vi, j]), 'REPLACE')

    mod = body.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    body.parent = arm
    return arm, top2[:, 0]


def animate_rig(arm):
    for frame in sorted(POSES):
        spec = POSES[frame]
        for pb in arm.pose.bones:
            R = Matrix.Identity(3)
            for axis, deg in spec.get(pb.name, []):
                R = Matrix.Rotation(math.radians(deg), 3, axis) @ R
            M3 = pb.bone.matrix_local.to_3x3()
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = (M3.inverted() @ R @ M3).to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=frame)
    for frame, loc in RIG_LOCATION.items():
        arm.location = loc
        arm.keyframe_insert("location", frame=frame)


def front_frame(z):
    """Frame, in dem die Zerfalls-Front die Höhe z erreicht."""
    t = (Z_TOP - z) / (Z_TOP - Z_BOTTOM)
    return COLLAPSE_START + t * (COLLAPSE_END - COLLAPSE_START)


def bake_dissolve_height(body):
    """Speichert pro Vertex die Höhe in der Pose zu Zerfallsbeginn (+ Rauschen).

    Shader (Transparenz) und Partikel-Bänder benutzen denselben Wert, damit der
    Sand genau dort herausbricht, wo der Körper verschwindet.
    """
    scene = bpy.context.scene
    scene.frame_set(COLLAPSE_START)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg).data
    co = np.empty(len(ev.vertices) * 3, dtype=np.float32)
    ev.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(body.matrix_world)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    rest = np.empty(len(body.data.vertices) * 3, dtype=np.float32)
    body.data.vertices.foreach_get("co", rest)
    rest = rest.reshape(-1, 3)
    dz = np.array([co[i, 2] + 0.12 * noise.noise(Vector(rest[i]) * 2.2) for i in range(len(co))],
                  dtype=np.float32)
    attr = body.data.attributes.new("dissolve_z", 'FLOAT', 'POINT')
    attr.data.foreach_set("value", dz)
    scene.frame_set(1)

    # Zelt-förmige Bänder (Summe der Gewichte = 1)
    h = (Z_TOP - Z_BOTTOM) / N_BANDS
    centers = [Z_BOTTOM + (i + 0.5) * h for i in range(N_BANDS)]
    zc = np.clip(dz, centers[0], centers[-1])
    weights = [np.clip(1 - np.abs(zc - c) / h, 0, 1) for c in centers]
    me = body.data
    areas = np.empty(len(me.polygons), dtype=np.float32)
    me.polygons.foreach_get("area", areas)
    band_area = np.zeros(N_BANDS)
    for p, a in zip(me.polygons, areas):
        vs = list(p.vertices)
        for i in range(N_BANDS):
            band_area[i] += a * weights[i][vs].mean()
    bands = []
    for i, c in enumerate(centers):
        vg = body.vertex_groups.new(name=f"band_{i}")
        for vi in np.nonzero(weights[i] > 0)[0]:
            vg.add([int(vi)], float(weights[i][vi]), 'REPLACE')
        start = max(1, front_frame(c + h))
        end = front_frame(c - h)
        bands.append((vg.name, band_area[i] / band_area.sum(), start, end))
    return bands


# ----------------------------------------------------------------------------
# Materialien
# ----------------------------------------------------------------------------
def body_material():
    mat = bpy.data.materials.new("SandGolem")
    nd = Nodes(mat)
    tc = nd.new("ShaderNodeTexCoord", -1200, 0)
    vor = nd.new("ShaderNodeTexVoronoi", -1000, 250, Scale=30)
    nd.set(vor.inputs["Vector"], tc.outputs["Object"])
    big = nd.new("ShaderNodeTexNoise", -1000, 0, Scale=3.5, Detail=4)
    nd.set(big.inputs["Vector"], tc.outputs["Object"])
    pits = nd.new("ShaderNodeMapRange", -800, 250, From_Min=0.0, From_Max=0.22, To_Min=0.0, To_Max=1.0)
    nd.set(pits.inputs["Value"], vor.outputs["Distance"])
    shade = nd.math('MULTIPLY', nd.math('ADD', big.outputs["Fac"], pits.outputs["Result"], -600, 100),
                    0.62, -450, 100)
    base = nd.ramp(shade, [(0.25, color("dark")), (0.55, color("mid")), (0.85, color("light"))], -300, 100)
    bump = nd.new("ShaderNodeBump", -300, -150, Strength=0.6, Distance=0.02)
    nd.set(bump.inputs["Height"], pits.outputs["Result"])
    bsdf = principled(nd, base, 0.95, 200, 200)
    nd.set(bsdf.inputs["Normal"], bump.outputs["Normal"])

    # Zerfall: sichtbar, solange dissolve_z (+ feines Rauschen) unter der Front liegt
    attr = nd.new("ShaderNodeAttribute", -1000, -350)
    attr.attribute_name = "dissolve_z"
    fine = nd.new("ShaderNodeTexNoise", -1000, -550, Scale=22, Detail=3)
    nd.set(fine.inputs["Vector"], tc.outputs["Object"])
    dz = nd.math('ADD', attr.outputs["Fac"],
                 nd.math('MULTIPLY', nd.math('SUBTRACT', fine.outputs["Fac"], 0.5, -800, -550), 0.1, -650, -550),
                 -500, -400)
    front = nd.new("ShaderNodeValue", -500, -650)
    front.name = front.label = "DissolveFront"
    visible = nd.new("ShaderNodeValue", -300, -650)
    visible.name = visible.label = "BodyVisible"
    visible.outputs[0].default_value = 1.0
    alpha = nd.math('MULTIPLY', nd.math('SUBTRACT', front.outputs[0], dz, -350, -450), 40, -200, -450, clamp=True)
    alpha = nd.math('MULTIPLY', alpha, visible.outputs[0], -50, -450)
    # Rückseiten (Blick ins Innere an der Zerfallskante) = massiver Sand statt dunkler Höhle
    geo = nd.new("ShaderNodeNewGeometry", 200, -300)
    inner = nd.new("ShaderNodeEmission", 400, -300, Strength=0.55)
    nd.set(inner.inputs["Color"], base)
    solid = nd.new("ShaderNodeMixShader", 600, 0)
    nd.set(solid.inputs[0], geo.outputs["Backfacing"])
    nd.set(solid.inputs[1], bsdf.outputs[0])
    nd.set(solid.inputs[2], inner.outputs[0])
    transp = nd.new("ShaderNodeBsdfTransparent", 600, -200)
    mix = nd.new("ShaderNodeMixShader", 900, 0)
    nd.set(mix.inputs[0], alpha)
    nd.set(mix.inputs[1], transp.outputs[0])
    nd.set(mix.inputs[2], solid.outputs[0])
    nd.output(mix.outputs[0])

    prefs = bpy.context.preferences.edit
    interp, prefs.keyframe_new_interpolation_type = prefs.keyframe_new_interpolation_type, 'LINEAR'
    for frame, val in ((1, Z_TOP + 0.3), (COLLAPSE_START, Z_TOP), (COLLAPSE_END, Z_BOTTOM),
                       (FRAME_END, Z_BOTTOM - 0.6)):
        front.outputs[0].default_value = val
        front.outputs[0].keyframe_insert("default_value", frame=frame)
    prefs.keyframe_new_interpolation_type = interp
    return mat


def grain_material():
    mat = bpy.data.materials.new("SandGrain")
    nd = Nodes(mat)
    info = nd.new("ShaderNodeObjectInfo", -400, 0)
    base = nd.ramp(info.outputs["Random"], [(0.0, color("dark")), (0.5, color("mid")), (1.0, color("light"))],
                   -200, 0)
    nd.output(principled(nd, base, 1.0).outputs[0])
    return mat


def dust_material(strength=0.14):
    mat = bpy.data.materials.new("SandDust")
    nd = Nodes(mat)
    pinfo = nd.new("ShaderNodeParticleInfo", -600, -200)
    age = nd.math('DIVIDE', pinfo.outputs["Age"], pinfo.outputs["Lifetime"], -400, -200)
    alpha = nd.math('MULTIPLY', nd.math('SUBTRACT', 1.0, age, -250, -200, clamp=True), strength, -100, -200)
    b = principled(nd, color("dust"), 1.0, 300, 0)
    nd.set(b.inputs["Alpha"], alpha)
    nd.output(b.outputs[0])
    return mat


def pile_material():
    mat = bpy.data.materials.new("SandPile")
    nd = Nodes(mat)
    tc = nd.new("ShaderNodeTexCoord", -1200, 0)
    n = nd.new("ShaderNodeTexNoise", -1000, 0, Scale=5, Detail=6)
    nd.set(n.inputs["Vector"], tc.outputs["Object"])
    vor = nd.new("ShaderNodeTexVoronoi", -1000, 250, Scale=120)
    nd.set(vor.inputs["Vector"], tc.outputs["Object"])
    base = nd.ramp(n.outputs["Fac"], [(0.3, color("mid")), (0.65, color("pile"))], -600, 150)
    bump = nd.new("ShaderNodeBump", -400, -100, Strength=0.4, Distance=0.01)
    nd.set(bump.inputs["Height"], vor.outputs["Distance"])
    bsdf = principled(nd, base, 1.0, 200, 200)
    nd.set(bsdf.inputs["Normal"], bump.outputs["Normal"])
    flat = nd.new("ShaderNodeVectorMath", -1000, -300)
    flat.operation = 'MULTIPLY'
    nd.set(flat.inputs[0], tc.outputs["Object"])
    flat.inputs[1].default_value = (1, 1, 0)
    rlen = nd.new("ShaderNodeVectorMath", -800, -300)
    rlen.operation = 'LENGTH'
    nd.set(rlen.inputs[0], flat.outputs[0])
    r = nd.math('ADD', rlen.outputs["Value"],
                nd.math('MULTIPLY', nd.math('SUBTRACT', n.outputs["Fac"], 0.5, -600, -450), 0.7, -450, -450),
                -300, -350)
    edge = nd.new("ShaderNodeMapRange", -100, -350, From_Min=0.75, From_Max=1.35, To_Min=1.0, To_Max=0.0)
    edge.interpolation_type = 'SMOOTHSTEP'
    nd.set(edge.inputs["Value"], r)
    nd.set(bsdf.inputs["Alpha"], edge.outputs["Result"])
    nd.output(bsdf.outputs[0])
    return mat


# ----------------------------------------------------------------------------
# Partikel
# ----------------------------------------------------------------------------
def instance_sphere(name, mat):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    obj = link_obj(bpy.data.objects.new(name, me))
    obj.location = (0, 0, -50)  # außerhalb des Bildes; Partikel ignorieren die Position
    return obj


def add_particles(body, name, count, start, end, inst, *, life, life_rand=0.0, size, size_rand=0.6,
                  normal=0.3, rand=0.4, align=(0, 0, 0), drag=0.0, brownian=0.0, gravity=1.0,
                  turbulence=1.0, wind=1.0, vgroup="", seed=0):
    ps = bpy.data.particles.new(name)
    ps.type = 'EMITTER'
    ps.count = max(1, int(count))
    ps.frame_start = start
    ps.frame_end = max(start + 0.5, end)
    ps.lifetime = life
    ps.lifetime_random = life_rand
    ps.emit_from = 'FACE'
    ps.distribution = 'RAND'
    ps.use_emit_random = True
    ps.use_even_distribution = True
    ps.normal_factor = normal
    ps.factor_random = rand
    ps.object_align_factor = align
    ps.physics_type = 'NEWTON'
    ps.mass = 1.0
    ps.particle_size = size
    ps.size_random = size_rand
    ps.drag_factor = drag
    ps.brownian_factor = brownian
    ps.timestep = SIM_TIMESTEP
    ps.use_size_deflect = True
    ps.effector_weights.gravity = gravity
    ps.effector_weights.turbulence = turbulence
    ps.effector_weights.wind = wind
    ps.render_type = 'OBJECT'
    ps.instance_object = inst
    ps.display_method = 'DOT'
    ps.display_percentage = 15
    mod = body.modifiers.new(name, 'PARTICLE_SYSTEM')
    psys = mod.particle_system
    old = psys.settings
    psys.settings = ps
    if old and old.users == 0:
        bpy.data.particles.remove(old)
    psys.seed = seed
    psys.vertex_group_density = vgroup
    psys.point_cache.frame_start = 1
    psys.point_cache.frame_end = FRAME_END
    return psys


def build_particles(body, bands, scale):
    grain = instance_sphere("GrainInstance", grain_material())
    dust = instance_sphere("DustInstance", dust_material())
    for i, (vg, share, start, end) in enumerate(bands):
        add_particles(body, f"Grains_{i}", GRAIN_COUNT * scale * share, start, end, grain,
                      life=1000, size=0.008, size_rand=0.7, normal=0.55, rand=0.45,
                      align=(0, -0.15, 0.35), drag=0.3, gravity=1.0, turbulence=0.25, wind=0.05,
                      vgroup=vg, seed=11 + i)
        add_particles(body, f"Chunks_{i}", CHUNK_COUNT * scale * share, start, end, grain,
                      life=1000, size=0.022, size_rand=0.6, normal=0.45, rand=0.4,
                      align=(0, -0.1, 0.25), drag=0.05, gravity=1.0, turbulence=0.1, wind=0.0,
                      vgroup=vg, seed=51 + i)
        add_particles(body, f"Dust_{i}", DUST_COUNT * scale * share, start, end + 4, dust,
                      life=60, life_rand=0.6, size=0.03, size_rand=0.7, normal=0.8, rand=0.6,
                      align=(0, -0.1, 0.5), drag=2.0, brownian=0.3, gravity=0.3,
                      turbulence=0.6, wind=0.6, vgroup=vg, seed=101 + i)
    add_particles(body, "Trail", TRAIL_COUNT * scale, 1, COLLAPSE_START + 10, dust,
                  life=40, life_rand=0.4, size=0.012, normal=0.15, rand=0.3, drag=0.4,
                  brownian=0.3, gravity=0.6, turbulence=0.6, wind=0.3, seed=7)


def build_forces():
    bpy.ops.object.effector_add(type='TURBULENCE', location=(0, 0, 1.2))
    turb = bpy.context.view_layer.objects.active
    turb.name = "SandTurbulence"
    turb.field.size = 0.3
    for f, s in ((1, 0.6), (COLLAPSE_START, 1.0), (COLLAPSE_START + 15, 2.5),
                 (COLLAPSE_END + 20, 1.5), (FRAME_END, 1.0)):
        turb.field.strength = s
        turb.field.keyframe_insert("strength", frame=f)
    bpy.ops.object.effector_add(type='WIND', location=(0, 0, 0))
    wind = bpy.context.view_layer.objects.active
    wind.name = "SandUpdraft"
    for f, s in ((1, 0.3), (COLLAPSE_START, 0.4), (COLLAPSE_START + 10, 1.4),
                 (COLLAPSE_END, 0.9), (COLLAPSE_END + 30, 0.2)):
        wind.field.strength = s
        wind.field.keyframe_insert("strength", frame=f)


# ----------------------------------------------------------------------------
# Umgebung
# ----------------------------------------------------------------------------
def build_ground():
    me = bpy.data.meshes.new("Ground")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=6)
    bm.to_mesh(me)
    bm.free()
    ground = link_obj(bpy.data.objects.new("Ground", me))
    ground.is_shadow_catcher = True
    ground.modifiers.new("Collision", 'COLLISION')
    c = ground.collision
    c.damping_factor = 0.85
    c.damping_random = 0.1
    c.friction_factor = 0.9
    c.friction_random = 0.1
    c.thickness_outer = 0.005
    return ground


def build_pile():
    me = bpy.data.meshes.new("SandPile")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=90, y_segments=90, size=1.7)
    for v in bm.verts:
        x, y = v.co.x, v.co.y
        r2 = x * x + (y + 0.08) ** 2
        n = noise.noise(Vector((x * 2.5, y * 2.5, 0.3)))
        v.co.z = 0.002 + 0.2 * math.exp(-r2 / (2 * 0.42 ** 2)) * (1 + 0.35 * n) + 0.015 * math.exp(-r2)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.materials.append(pile_material())
    pile = link_obj(bpy.data.objects.new("SandPile", me))
    for f, s in ((COLLAPSE_START + 6, (0.001, 0.001, 0.001)), (COLLAPSE_START + 14, (0.3, 0.3, 0.05)),
                 (COLLAPSE_END + 35, (1, 1, 1))):
        pile.scale = s
        pile.keyframe_insert("scale", frame=f)
    return pile


def build_camera_and_light():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = ORTHO_SCALE
    cam = link_obj(bpy.data.objects.new("Camera", cam_data))
    tilt = math.radians(CAM_TILT)
    fwd = Vector((0, math.cos(tilt), -math.sin(tilt)))
    cam.location = Vector(CAM_TARGET) - fwd * 12
    cam.rotation_euler = (math.radians(90) - tilt, 0, 0)
    scene.camera = cam

    sun = bpy.data.lights.new("Sun", 'SUN')
    sun.energy = 2.4
    sun.angle = math.radians(14)
    sun.color = (1.0, 0.96, 0.9)
    sun_obj = link_obj(bpy.data.objects.new("Sun", sun))
    sun_obj.rotation_euler = Vector((0.25, 0.3, -0.92)).to_track_quat('-Z', 'Y').to_euler()

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.55, 0.6, 0.68, 1)
    bg.inputs[1].default_value = 0.7
    scene.world = world
    return cam


def setup_render(res, samples):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 1
    sc.cycles.transparent_max_bounces = 64
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.image_settings.color_depth = '8'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, FRAME_END
    sc.gravity = (0, 0, -9.81)


# ----------------------------------------------------------------------------
# Export / Texturen
# ----------------------------------------------------------------------------
def export_golem_fbx(body, dominant_bone, path, target_tris=12000):
    """Exportiert den Golem (Ruhepose) als einzelne Körperteile für Roblox."""
    me = body.data
    part_of_face = []
    for p in me.polygons:
        votes = {}
        for v in p.vertices:
            part = BONES[dominant_bone[v]][4]
            votes[part] = votes.get(part, 0) + 1
        part_of_face.append(max(votes, key=votes.get))
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    ratio = min(1.0, target_tris / tris)
    parts = []
    for part in sorted(set(part_of_face)):
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f, pn in zip(bm.faces, part_of_face) if pn != part], context='FACES')
        center = sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))
        bmesh.ops.translate(bm, verts=bm.verts, vec=-center)
        if bm.verts.layers.deform.active:
            bm.verts.layers.deform.remove(bm.verts.layers.deform.active)
        pme = bpy.data.meshes.new(part)
        bm.to_mesh(pme)
        bm.free()
        if "dissolve_z" in pme.attributes:
            pme.attributes.remove(pme.attributes["dissolve_z"])
        obj = link_obj(bpy.data.objects.new(part, pme))
        obj.location = center
        dec = obj.modifiers.new("Decimate", 'DECIMATE')
        dec.ratio = ratio
        tri = obj.modifiers.new("Triangulate", 'TRIANGULATE')
        tri.keep_custom_normals = True
        parts.append(obj)
    for o in bpy.context.scene.objects:
        o.select_set(o in parts)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'},
                             use_mesh_modifiers=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Z', axis_up='Y', mesh_smooth_type='FACE',
                             add_leaf_bones=False, bake_anim=False)
    for o in parts:
        me_ = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me_)
    log("FBX:", path)


def save_png(arr, path):
    """arr: (H, W, 4) float 0..1, Zeile 0 = oben."""
    h, w, _ = arr.shape
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1], dtype=np.float32).ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def load_png(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1]


def fbm(size, rng, octaves=(4, 8, 16, 32)):
    total = np.zeros((size, size))
    for k, cells in enumerate(octaves):
        g = rng.random((cells + 1, cells + 1))
        x = np.linspace(0, cells, size, endpoint=False)
        i = x.astype(int)
        t = x - i
        t = t * t * (3 - 2 * t)
        a, b = g[np.ix_(i, i)], g[np.ix_(i, i + 1)]
        c, d = g[np.ix_(i + 1, i)], g[np.ix_(i + 1, i + 1)]
        tx, ty = t[None, :], t[:, None]
        total += ((a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty) * 0.5 ** k
    return total / sum(0.5 ** k for k in range(len(octaves)))


def make_sprites(out):
    """Weiße Einzeltexturen - in Roblox per ParticleEmitter.Color sandfarben getönt."""
    rng = np.random.default_rng(3)
    s = 256
    y, x = np.mgrid[0:s, 0:s] / (s - 1) * 2 - 1
    r = np.sqrt(x * x + y * y)
    n = fbm(s, rng)
    a = np.clip((1 - r) ** 1.5 * (0.2 + 1.4 * n) - 0.05, 0, 1)
    shade = 0.8 + 0.2 * np.clip(n * 1.2 - 0.1 * y, 0, 1)
    dust = np.dstack([shade, shade, shade, a])
    save_png(dust, os.path.join(out, "SandDust.png"))

    s = 128
    y, x = np.mgrid[0:s, 0:s].astype(float)
    alpha = np.zeros((s, s))
    lum = np.ones((s, s))
    for _ in range(9):
        cx, cy = rng.uniform(30, 98, 2)
        rad = rng.uniform(5, 13)
        d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / rad
        m = np.clip((1 - d) * 4, 0, 1)
        light = np.clip(1 - 0.45 * (((x - cx) + (y - cy)) / rad + 0.6), 0.45, 1)
        lum = np.where(m > alpha, light, lum)
        alpha = np.maximum(alpha, m)
    grain = np.dstack([lum, lum, lum, alpha])
    save_png(grain, os.path.join(out, "SandGrain.png"))


def downscale(rgba, size):
    h = rgba.shape[0]
    f = h // size
    a = rgba[..., 3:4]
    pm = np.concatenate([rgba[..., :3] * a, a], -1)
    pm = pm.reshape(size, f, size, f, 4).mean((1, 3))
    rgb = pm[..., :3] / np.maximum(pm[..., 3:4], 1e-6)
    return np.concatenate([rgb, pm[..., 3:4]], -1)


def build_sheet(frame_paths, grid, path):
    cell = SHEET_SIZE // grid
    sheet = np.zeros((SHEET_SIZE, SHEET_SIZE, 4), dtype=np.float32)
    for i, p in enumerate(frame_paths):
        r, c = divmod(i, grid)
        sheet[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell] = downscale(load_png(p), cell)
    # Hauch von Schatten-Fänger-Rauschen entfernen (wäre in Roblox ein grauer Kasten)
    sheet[..., 3] = np.clip((sheet[..., 3] - 0.035) / 0.965, 0, 1)
    # unsichtbare Pixel sandfarben füllen -> keine dunklen Ränder durch Textur-Filterung
    vis = sheet[..., 3] > 0.2
    fill = sheet[vis][:, :3].mean(0) if vis.any() else np.array([0.7, 0.6, 0.5])
    sheet[sheet[..., 3] < 1 / 255, :3] = fill
    save_png(np.clip(sheet, 0, 1), path)
    log("Sheet:", path)


# ----------------------------------------------------------------------------
# Ablauf
# ----------------------------------------------------------------------------
def build_scene(scale=1.0):
    reset_scene()
    setup_render(RENDER_RES, SAMPLES)
    body = build_golem_mesh()
    arm, dominant = build_rig(body)
    animate_rig(arm)
    bands = bake_dissolve_height(body)
    body.data.materials.append(body_material())
    build_ground()
    build_pile()
    build_forces()
    build_particles(body, bands, scale)
    cam = build_camera_and_light()
    bpy.context.scene.frame_set(1)
    return body, dominant, cam


def simulate():
    scene = bpy.context.scene
    for f in range(1, FRAME_END + 1):
        scene.frame_set(f)
        if f % 20 == 0:
            log(f"Simulation Frame {f}/{FRAME_END}")


def render_pass(name, frames, out, body):
    scene = bpy.context.scene
    body.data.materials[0].node_tree.nodes["BodyVisible"].outputs[0].default_value = 0.0 if name == "burst" else 1.0
    folder = os.path.join(out, "frames", name)
    os.makedirs(folder, exist_ok=True)
    paths = {}
    for i, f in enumerate(frames):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(folder, f"{name}_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        paths[f] = scene.render.filepath
        log(f"Render {name}: {i + 1}/{len(frames)} (Frame {f})")
    body.data.materials[0].node_tree.nodes["BodyVisible"].outputs[0].default_value = 1.0
    return paths


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="sand_monster_vfx.py")
    ap.add_argument("--out", default="sand_vfx_output", help="Ausgabeordner")
    ap.add_argument("--quick", action="store_true", help="wenige Partikel, kleine Auflösung")
    ap.add_argument("--build-only", action="store_true", help="nur Szene bauen, nicht rendern")
    ap.add_argument("--save", default=None, help=".blend-Datei speichern")
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--res", type=int, default=None)
    args = ap.parse_args(argv)

    global RENDER_RES, SAMPLES
    scale = 0.15 if args.quick else 1.0
    RENDER_RES = args.res or (256 if args.quick else RENDER_RES)
    SAMPLES = args.samples or (8 if args.quick else SAMPLES)

    body, dominant, cam = build_scene(scale)
    if args.build_only or not bpy.app.background:
        if args.save:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
        log("Szene gebaut. Leertaste = Simulation abspielen, F12 = Frame rendern.")
        return

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    export_golem_fbx(body, dominant, os.path.join(out, "SandGolem.fbx"))
    make_sprites(out)
    simulate()

    needed = {}
    for _name, (pass_name, frames, _grid) in SHEETS.items():
        needed.setdefault(pass_name, set()).update(frames)
    rendered = {p: render_pass(p, sorted(fr), out, body) for p, fr in needed.items()}

    for name, (pass_name, frames, grid) in SHEETS.items():
        build_sheet([rendered[pass_name][f] for f in frames], grid, os.path.join(out, name + ".png"))
    collapse = SHEETS["SandMonster_Collapse_8x8"][1]
    build_sheet([rendered["full"][f] for f in reversed(collapse)], 8,
                os.path.join(out, "SandMonster_Rise_8x8.png"))

    scene = bpy.context.scene
    ground_v = world_to_camera_view(scene, cam, Vector((0, 0, 0))).y
    meta = {
        "frames_per_sheet_8x8": 64,
        "sheet_fps": SHEET_FPS,
        "duration_seconds": round(64 / SHEET_FPS, 3),
        "frame_world_size_m": ORTHO_SCALE,
        "ground_v_from_bottom": round(ground_v, 4),
        "golem_height_m": round(max(v.co.z for v in body.data.vertices), 3),
        "burst_starts_at_seconds_in_collapse": round((SHEETS["SandBurst_8x8"][1][0] - 1) / (2 * SHEET_FPS), 3),
        "collapse_front_seconds": [round((COLLAPSE_START - 1) / (2 * SHEET_FPS), 3),
                                   round((COLLAPSE_END - 1) / (2 * SHEET_FPS), 3)],
    }
    with open(os.path.join(out, "vfx_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    log("Meta:", meta)

    if args.save:
        scene.frame_set(1)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
    log("Fertig ->", out)


if __name__ == "__main__":
    main()
