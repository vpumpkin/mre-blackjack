# FINAL icon: the Fusion Comet (Kugel fused with a Wuerfel) smashes into a terrified Kreuz.
# 3D characters only (Blender 5.2, bpy module, Cycles CPU); all 2D FX are done in post.py.
# Run:  BPY scene.py OUT.png SIZE SAMPLES
# Writes OUT.png (RGBA beauty, transparent film), OUT_id.png (flat ID colours) and OUT_meta.json
#   ID colours: sphere (1,0,0), cube (1,0,1), cross (0,1,0), tetra (0,0,1), sweat drops (0,1,1)
# Face decals come from faces.py (system python, PIL); they are generated if missing.
# Layout overrides: ICON_CFG='{"head": {"px": 300}, "tetra": {"show": 0}, ...}'
import bpy, bmesh, math, sys, os, subprocess, json
from mathutils import Vector, Euler, Matrix, Quaternion

OUT = os.path.abspath(sys.argv[1])
SIZE = int(sys.argv[2])
SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 64
HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, 'tex')
if not os.path.exists(os.path.join(TEX, 'cube_col.png')):
    subprocess.run(['python3', '-I', os.path.join(HERE, 'faces.py'), TEX], check=True)

CFG = json.loads(os.environ.get('ICON_CFG', '{}'))
LENS = 35.0
REF = 512.0  # layout is specified in 512 px screen coordinates

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6
sc.cycles.glossy_bounces = 4
sc.cycles.transparent_max_bounces = 8
sc.cycles.sample_clamp_indirect = 8.0
# Light tree off: with the light-linked rim_left kicker the light tree over-brightened the Kreuz
# (median (207,210,237) -> (234,233,255)); without it the linked and unlinked renders agree.
sc.cycles.use_light_tree = bool(CFG.get('light_tree', 0))
sc.render.resolution_x = sc.render.resolution_y = SIZE
sc.render.resolution_percentage = 100
sc.render.compositor_device = 'CPU'
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
sc.render.film_transparent = True
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'


# ------------------------------------------------------------------ helpers
def at(px, py, depth):
    """world position that lands on screen pixel (px, py) of a 512 frame at the given depth (camera at origin looking +Y)"""
    hw = depth * 18.0 / LENS
    return Vector(((px / REF - 0.5) * 2 * hw, depth, (0.5 - py / REF) * 2 * hw))


def px_per_unit(depth):
    return (REF / 2) / (depth * 18.0 / LENS)


def new_obj(name, mesh):
    o = bpy.data.objects.new(name, mesh)
    sc.collection.objects.link(o)
    return o


def smooth(o):
    for p in o.data.polygons:
        p.use_smooth = True


def bevel(o, width, segs=6, angle=None, harden=True):
    b = o.modifiers.new('Bevel', 'BEVEL')
    b.width = width
    b.segments = segs
    b.profile = 0.5
    if angle is not None:
        b.limit_method = 'ANGLE'
        b.angle_limit = math.radians(angle)
    else:
        b.limit_method = 'NONE'
    b.harden_normals = harden
    b.miter_outer = 'MITER_ARC'
    return b


def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    return me


def cross_mesh(a=0.55, b=1.3, d=0.9):
    xs = [-b, -a, a, b]
    zs = [-b, -a, a, b]
    cells = [(1, 1), (0, 1), (2, 1), (1, 0), (1, 2)]
    verts, idx = [], {}

    def vid(i, j, side):
        k = (i, j, side)
        if k not in idx:
            idx[k] = len(verts)
            verts.append((xs[i], -d / 2 if side == 0 else d / 2, zs[j]))
        return idx[k]
    faces, edges = [], {}
    for (i, j) in cells:
        corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
        faces.append([vid(*c, 0) for c in corners])
        faces.append([vid(*c, 1) for c in corners[::-1]])
        for e0, e1 in zip(corners, corners[1:] + corners[:1]):
            key = tuple(sorted((e0, e1)))
            edges[key] = edges.get(key, 0) + 1
    for (e0, e1), n in edges.items():
        if n == 1:
            faces.append([vid(*e0, 0), vid(*e1, 0), vid(*e1, 1), vid(*e0, 1)])
    return mesh_from('cross', verts, faces)


def tetra_mesh(L=2.1):
    Rf = L / math.sqrt(3)
    h = L * math.sqrt(2.0 / 3.0)
    v = [(0, 0, Rf), (-L / 2, 0, -Rf / 2), (L / 2, 0, -Rf / 2), (0, h, 0)]
    v = [(x, y - h / 4, z) for (x, y, z) in v]
    return mesh_from('tetra', v, [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]])


def cube_mesh(s=1.0):
    v = [(x, y, z) for x in (-s, s) for y in (-s, s) for z in (-s, s)]
    f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return mesh_from('cube', v, f)


def sphere_obj(name, r=1.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=r)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = new_obj(name, me); smooth(o)
    return o


def link(nt, a, b):
    nt.links.new(a, b)


def mix_rgba(N):
    m = N.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.blend_type = 'MIX'
    ins = [s for s in m.inputs if s.type == 'RGBA']
    outs = [s for s in m.outputs if s.type == 'RGBA']
    return m, m.inputs['Factor'], ins[0], ins[1], outs[0]


def vinyl(name, rgb, rough=0.32, coat=1.0, face=None, S=1.0, rim=None, rim_power=3.0,
          rim_strength=0.0, bump=0.35, grad=None, grin_glow=0.0):
    """glossy vinyl toy material. face: decal name projected along local -Y. grad: (axis, lo, hi, rgb_lo, rgb_hi)
    vertical colour gradient in object space (gives the toys a lit-from-above candy look).
    grin_glow > 0: the decal's whites below object z = 0 (the grin) glow white at this emission strength"""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes
    p = N['Principled BSDF']
    p.inputs['Base Color'].default_value = (*rgb, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Coat Weight'].default_value = coat
    p.inputs['Coat Roughness'].default_value = 0.035
    p.inputs['Specular IOR Level'].default_value = 0.5
    tc = N.new('ShaderNodeTexCoord')
    sep = N.new('ShaderNodeSeparateXYZ'); link(nt, tc.outputs['Object'], sep.inputs[0])
    body = None
    if grad:
        axis, lo, hi, c0, c1 = grad
        mr = N.new('ShaderNodeMapRange'); mr.inputs['From Min'].default_value = lo; mr.inputs['From Max'].default_value = hi
        link(nt, sep.outputs[axis], mr.inputs['Value'])
        gm, gf, gA, gB, gO = mix_rgba(N)
        gA.default_value = (*c0, 1); gB.default_value = (*c1, 1)
        link(nt, mr.outputs['Result'], gf)
        body = gO
        link(nt, gO, p.inputs['Base Color'])
    if face:
        mu = N.new('ShaderNodeMath'); mu.operation = 'MULTIPLY_ADD'
        mu.inputs[1].default_value = 0.5 / S; mu.inputs[2].default_value = 0.5
        link(nt, sep.outputs['X'], mu.inputs[0])
        mv = N.new('ShaderNodeMath'); mv.operation = 'MULTIPLY_ADD'
        mv.inputs[1].default_value = 0.5 / S; mv.inputs[2].default_value = 0.5
        link(nt, sep.outputs['Z'], mv.inputs[0])
        comb = N.new('ShaderNodeCombineXYZ')
        link(nt, mu.outputs[0], comb.inputs['X']); link(nt, mv.outputs[0], comb.inputs['Y'])
        img = N.new('ShaderNodeTexImage')
        img.image = bpy.data.images.load(os.path.join(TEX, face + '_col.png'))
        img.extension = 'CLIP'; img.interpolation = 'Cubic'
        link(nt, comb.outputs[0], img.inputs['Vector'])
        front = N.new('ShaderNodeMath'); front.operation = 'LESS_THAN'; front.inputs[1].default_value = 0.0
        link(nt, sep.outputs['Y'], front.inputs[0])
        fa = N.new('ShaderNodeMath'); fa.operation = 'MULTIPLY'
        link(nt, img.outputs['Alpha'], fa.inputs[0]); link(nt, front.outputs[0], fa.inputs[1])
        mx, fac, A, B, O = mix_rgba(N)
        if body is not None:
            link(nt, body, A)
        else:
            A.default_value = (*rgb, 1)
        link(nt, fa.outputs[0], fac); link(nt, img.outputs['Color'], B)
        link(nt, O, p.inputs['Base Color'])
        hi = N.new('ShaderNodeTexImage')
        hi.image = bpy.data.images.load(os.path.join(TEX, face + '_h.png'))
        hi.image.colorspace_settings.name = 'Non-Color'
        hi.extension = 'EXTEND'; hi.interpolation = 'Cubic'
        link(nt, comb.outputs[0], hi.inputs['Vector'])
        hm = N.new('ShaderNodeMath'); hm.operation = 'MULTIPLY'
        link(nt, hi.outputs['Color'], hm.inputs[0]); link(nt, front.outputs[0], hm.inputs[1])
        bp = N.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = 0.03
        link(nt, hm.outputs[0], bp.inputs['Height'])
        link(nt, bp.outputs['Normal'], p.inputs['Normal'])
        link(nt, bp.outputs['Normal'], p.inputs['Coat Normal'])
    rim_term = None
    if rim is not None and rim_strength > 0:
        lw = N.new('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = 0.5
        pw = N.new('ShaderNodeMath'); pw.operation = 'POWER'; pw.inputs[1].default_value = rim_power
        link(nt, lw.outputs['Facing'], pw.inputs[0])
        st = N.new('ShaderNodeMath'); st.operation = 'MULTIPLY'; st.inputs[1].default_value = rim_strength
        link(nt, pw.outputs[0], st.inputs[0])
        p.inputs['Emission Color'].default_value = (*rim, 1)
        link(nt, st.outputs[0], p.inputs['Emission Strength'])
        rim_term = st.outputs[0]
    if face and grin_glow > 0:
        # The grin sits on the lower half, facing away from the overhead key, so its teeth rendered grey.
        # Self-lit decal whites, only in the grin:
        #   whiteMask = MapRange(BW(decal), 0.6 -> 0, 0.9 -> 1) * decal alpha * front * (object z < 0)
        #   Emission Color = mix(rim, white, whiteMask); Strength = rim_term * (1 - whiteMask) + grin_glow * whiteMask
        bw = N.new('ShaderNodeRGBToBW'); link(nt, img.outputs['Color'], bw.inputs[0])
        wm = N.new('ShaderNodeMapRange'); wm.clamp = True
        wm.inputs['From Min'].default_value = 0.6; wm.inputs['From Max'].default_value = 0.9
        link(nt, bw.outputs[0], wm.inputs['Value'])
        low = N.new('ShaderNodeMath'); low.operation = 'LESS_THAN'; low.inputs[1].default_value = 0.0
        link(nt, sep.outputs['Z'], low.inputs[0])
        w1 = N.new('ShaderNodeMath'); w1.operation = 'MULTIPLY'
        link(nt, wm.outputs['Result'], w1.inputs[0]); link(nt, fa.outputs[0], w1.inputs[1])
        wmask = N.new('ShaderNodeMath'); wmask.operation = 'MULTIPLY'
        link(nt, w1.outputs[0], wmask.inputs[0]); link(nt, low.outputs[0], wmask.inputs[1])
        _, ef, eA, eB, eO = mix_rgba(N)
        eA.default_value = (*(rim if rim is not None else (0.0, 0.0, 0.0)), 1); eB.default_value = (1.0, 1.0, 1.0, 1)
        link(nt, wmask.outputs[0], ef); link(nt, eO, p.inputs['Emission Color'])
        g1 = N.new('ShaderNodeMath'); g1.operation = 'MULTIPLY'; g1.inputs[1].default_value = grin_glow
        link(nt, wmask.outputs[0], g1.inputs[0])
        if rim_term is not None:
            inv = N.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
            link(nt, wmask.outputs[0], inv.inputs[1])
            r1 = N.new('ShaderNodeMath'); r1.operation = 'MULTIPLY'
            link(nt, rim_term, r1.inputs[0]); link(nt, inv.outputs[0], r1.inputs[1])
            sm = N.new('ShaderNodeMath'); sm.operation = 'ADD'
            link(nt, r1.outputs[0], sm.inputs[0]); link(nt, g1.outputs[0], sm.inputs[1])
            link(nt, sm.outputs[0], p.inputs['Emission Strength'])
        else:
            link(nt, g1.outputs[0], p.inputs['Emission Strength'])
    return m


def emit_mat(name, rgb, strength=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes
    for n in list(N):
        N.remove(n)
    e = N.new('ShaderNodeEmission'); e.inputs['Color'].default_value = (*rgb, 1)
    e.inputs['Strength'].default_value = strength
    o = N.new('ShaderNodeOutputMaterial')
    link(nt, e.outputs[0], o.inputs['Surface'])
    return m


def cam_quat(loc, yaw=0.0, pitch=0.0, roll=0.0):
    """rotation that turns local -Y toward the camera (origin) from loc, plus extra yaw/pitch/roll in degrees"""
    d = (Vector((0, 0, 0)) - Vector(loc)).normalized()
    q = (-d).to_track_quat('Y', 'Z')        # local +Y away from the camera, +Z up
    extra = Euler((math.radians(pitch), math.radians(roll), math.radians(yaw)), 'XYZ').to_matrix()
    return (q.to_matrix() @ extra).to_quaternion()


def face_camera(o, yaw=0.0, pitch=0.0, roll=0.0):
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = cam_quat(o.location, yaw, pitch, roll)


def no_glossy(o):
    """keep o out of glossy reflections (stops the white Kreuz painting a milky band over the Kugel's grin)"""
    o.visible_glossy = False


# ------------------------------------------------------------------ world (only lights reflections; film is transparent)
w = bpy.data.worlds.new('World'); sc.world = w
w.use_nodes = True
wn = w.node_tree.nodes
bgn = wn['Background']
tcw = wn.new('ShaderNodeTexCoord')
sepw = wn.new('ShaderNodeSeparateXYZ'); w.node_tree.links.new(tcw.outputs['Generated'], sepw.inputs[0])
ramp = wn.new('ShaderNodeValToRGB')
w.node_tree.links.new(sepw.outputs['Z'], ramp.inputs[0])
ramp.color_ramp.elements[0].position = 0.0
ramp.color_ramp.elements[0].color = (0.01, 0.006, 0.03, 1)
ramp.color_ramp.elements[1].position = 1.0
ramp.color_ramp.elements[1].color = (0.16, 0.08, 0.36, 1)
w.node_tree.links.new(ramp.outputs['Color'], bgn.inputs['Color'])
bgn.inputs['Strength'].default_value = CFG.get('world', 0.8)

# ------------------------------------------------------------------ layout (512 px screen coordinates)
# size = wanted on-screen size in px (head: radius of the sphere; cross: arm span; tetra: edge length)
HEAD = dict(px=288, py=226, depth=5.0, size=114, yaw=-10, pitch=7, roll=-6)
CUBE = dict(half=0.66, pos=(0.58, 0.80, 0.46), rot=(25, 0, 50), bevel=0.15, face=1)
CROSS = dict(px=157, py=353, depth=5.6, size=181, yaw=6, pitch=-4, roll=-15,
             squash_angle=30, squash=(0.88, 1.08), arm=0.55)
# tetra roll -32: clearly tumbling away from the impact (at -16 it read like an upright warning-sign glyph)
TETRA = dict(show=1, px=394, py=402, depth=5.2, size=112, yaw=12, pitch=6, roll=-32, squash=(0.95, 1.0, 1.05))
for k, d in (('head', HEAD), ('cube', CUBE), ('cross', CROSS), ('tetra', TETRA)):
    d.update(CFG.get(k, {}))

# ------------------------------------------------------------------ materials
M_SPHERE = vinyl('comet_sphere', (0.012, 0.13, 1.0), rough=0.28, face='comet', S=1.0,
                 rim=(0.05, 0.75, 1.0), rim_power=4.0, rim_strength=CFG.get('rim_s', 2.4), bump=0.3,
                 grin_glow=CFG.get('grin_glow', 0.6))
ORANGE_LO, ORANGE_HI = tuple(CFG.get('cube_lo', (0.70, 0.045, 0.002))), tuple(CFG.get('cube_hi', (0.92, 0.20, 0.008)))
M_CUBE = vinyl('comet_cube', ORANGE_HI, rough=0.27, face='cube' if CUBE['face'] else None, S=CUBE['half'],
               rim=(1.0, 0.55, 0.15), rim_power=4.0, rim_strength=CFG.get('rim_c', 0.9), bump=0.3,
               grad=('Z', -CUBE['half'], CUBE['half'], ORANGE_LO, ORANGE_HI))
M_CROSS = vinyl('cross', tuple(CFG.get('cross_rgb', (0.34, 0.38, 0.48))), rough=0.3, face='cross', S=1.3, bump=0.3)
M_TETRA = vinyl('tetra', (1.0, 0.62, 0.02), rough=0.3, face='tetra', S=1.0, bump=0.3,
                grad=('Z', -0.7, 1.2, (1.0, 0.36, 0.01), (1.0, 0.80, 0.06)))


def place(o, L, natural):
    o.location = at(L['px'], L['py'], L['depth'])
    s = L['size'] / (natural * px_per_unit(L['depth']))
    sq = L.get('squash', (1, 1, 1))
    o.scale = (s * sq[0], s * sq[1], s * sq[2])
    face_camera(o, L['yaw'], L['pitch'], L['roll'])


# ---- the Fusion Comet: Kugel (face) in front, a Wuerfel welded onto its back
head = sphere_obj('comet_sphere', 1.0)
head.data.materials.append(M_SPHERE)
place(head, HEAD, 1.0)
cube = new_obj('comet_cube', cube_mesh(CUBE['half'])); bevel(cube, CUBE['bevel'], 6)
smooth(cube)
cube.data.materials.append(M_CUBE)
cube.parent = head
cube.location = tuple(CUBE['pos'])
cube.rotation_euler = tuple(math.radians(a) for a in CUBE['rot'])

# ---- Kreuz: squashed along the impact direction by a parent empty (keeps the face decal on the body)
cross = new_obj('cross', cross_mesh(CROSS['arm'], 1.3, 0.9))
bevel(cross, 0.17, 6, angle=30)
smooth(cross)
cross.data.materials.append(M_CROSS)
c_loc = at(CROSS['px'], CROSS['py'], CROSS['depth'])
c_s = CROSS['size'] / (2.6 * px_per_unit(CROSS['depth']))
sq_e = bpy.data.objects.new('cross_squash', None); sc.collection.objects.link(sq_e)
sq_e.location = c_loc
sq_e.rotation_mode = 'XYZ'
sq_e.rotation_euler = (0.0, math.radians(-CROSS['squash_angle']), 0.0)   # local X = screen direction at squash_angle (deg, ccw from +x)
sq_e.scale = (CROSS['squash'][0], 1.0, CROSS['squash'][1])
bpy.context.view_layer.update()
cross.parent = sq_e
cross.matrix_parent_inverse = Matrix.Identity(4)
R_e = sq_e.rotation_euler.to_matrix()
R_c = cam_quat(c_loc, CROSS['yaw'], CROSS['pitch'], CROSS['roll']).to_matrix()
local = (R_e.transposed() @ R_c).to_4x4() @ Matrix.Diagonal((c_s, c_s, c_s, 1.0))
cross.matrix_basis = local
no_glossy(cross)

# ---- Tetraeder: second victim, knocked flying
tetra = new_obj('tetra', tetra_mesh(2.1))
bevel(tetra, 0.2, 6)
smooth(tetra)
tetra.data.materials.append(M_TETRA)
place(tetra, TETRA, 2.1)
no_glossy(tetra)
if not TETRA['show']:
    tetra.hide_render = True

# ---- sweat drops (glossy 3D teardrops), just one or two big ones
M_DROP = vinyl('drop', (0.10, 0.55, 1.0), rough=0.06, coat=1.0, rim=(0.5, 0.9, 1.0), rim_power=3.0, rim_strength=0.8)


def drop(name, px, py, depth, size, tilt):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    for v in bm.verts:
        x, y, z = v.co
        if z > 0:
            k = (1 - z) ** 0.55
            v.co = (x * k, y * k, z * 1.55)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = new_obj(name, me); smooth(o)
    o.data.materials.append(M_DROP)
    o.location = at(px, py, depth)
    s_ = size / (2.0 * px_per_unit(depth))
    o.scale = (s_, s_ * 0.8, s_)
    face_camera(o, 0, 0, tilt)
    no_glossy(o)
    return o


DROPS = CFG.get('drops', [[68, 250, 5.0, 30, 140]] + ([[446, 334, 5.2, 22, -150]] if TETRA['show'] else []))
drops = [drop('drop%d' % i, *d) for i, d in enumerate(DROPS)]

if CFG.get('only_head'):
    for o in [cross, tetra] + drops:
        o.hide_render = True


# ------------------------------------------------------------------ lights
def area(name, loc, target, energy, size, color=(1, 1, 1), shape='SQUARE'):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = energy; ld.size = size; ld.color = color
    ld.shape = shape
    o = bpy.data.objects.new(name, ld); sc.collection.objects.link(o)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return o


def point(name, loc, energy, radius, color):
    ld = bpy.data.lights.new(name, 'POINT'); ld.energy = energy; ld.shadow_soft_size = radius; ld.color = color
    o = bpy.data.objects.new(name, ld); sc.collection.objects.link(o)
    o.location = loc
    return o


LI = dict(key=850, fill=120, back=1000, glow=420, rimc=320, impact=160, cubekey=260, plumerim=700)
LI.update(CFG.get('lights', {}))
bpy.context.view_layer.update()
hp = head.matrix_world.translation.copy()
cc = cross.matrix_world.translation.copy()
tc_ = tetra.matrix_world.translation.copy()
# key: small, high and to the front-left -> crisp vinyl highlight above the brows
key = area('key', tuple(hp + Vector((-1.7, -2.3, 4.4))), tuple(hp), LI['key'], 1.3, (1.0, 0.97, 0.93))
# light linking: the hard key would bleach the orange cube's top face, so the cube gets its own warm key
key_recv = bpy.data.collections.new('key_receivers')
for o in sc.objects:
    if o.type == 'MESH' and o.name != 'comet_cube':
        key_recv.objects.link(o)
key.light_linking.receiver_collection = key_recv
# soft cool fill from below the camera so faces never go muddy
fill_l = area('fill', (1.2, -1.0, -3.0), (0.0, 4.5, -0.6), LI['fill'], 4.0, (0.62, 0.72, 1.0))
fill_l.visible_glossy = False         # its big soft reflection laid a milky band over the grin
# the plume behind the comet back-lights everything: cyan-white from above-behind-right
back_l = area('comet_back', (hp.x + 1.4, hp.y + 1.6, hp.z + 1.4), tuple(hp + Vector((-1.2, 0.0, -1.4))), LI['back'], 2.5, (0.55, 0.9, 1.0))
back_l.light_linking.receiver_collection = key_recv   # not on the cube: it mirrored as a pale patch on its top face
# the plume behind the cube rims it in cyan (orange body + cyan rim = complementary pop)
cpw = cube.matrix_world.translation.copy()
area('plume_rim', tuple(cpw + Vector((1.8, 1.4, 0.4))), tuple(cpw), LI['plumerim'], 1.6, (0.35, 0.85, 1.0))
# comet light spilling down onto the victims' upper-right edges (cyan rim)
area('glow_cross', tuple(cc + Vector((1.1, 0.9, 1.0))), tuple(cc), LI['glow'], 1.2, (0.45, 0.88, 1.0))
area('glow_tetra', tuple(tc_ + Vector((-0.9, 0.9, 1.0))), tuple(tc_), LI['glow'] * 0.8, 1.2, (0.75, 0.55, 1.0))
# magenta kicker from the left so the white Kreuz never melts into the floor glow
rim_l = area('rim_left', (-4.6, 6.0, -0.2), (-1.4, 4.2, -1.3), LI['rimc'], 2.0, (1.0, 0.35, 0.85))
# light linking: only the victims receive it (it mirrored as a pink-white bar right against the Kugel's left eye)
victims_recv = bpy.data.collections.new('rim_left_receivers')
for o in [cross, tetra] + drops:
    victims_recv.objects.link(o)
rim_l.light_linking.receiver_collection = victims_recv
# the impact itself: a hot, warm point light right at the contact
IMP = CFG.get('impact_px', None)
if IMP is None:
    # contact = point on the comet's rim facing the Kreuz
    hv = Vector((CROSS['px'] - HEAD['px'], CROSS['py'] - HEAD['py'])).normalized()
    IMP = (HEAD['px'] + hv.x * HEAD['size'] * 1.0, HEAD['py'] + hv.y * HEAD['size'] * 1.0)
imp_w = at(IMP[0], IMP[1], (HEAD['depth'] + CROSS['depth']) / 2 - 0.35)
imp_l = point('impact', tuple(imp_w), LI['impact'], 0.12, (1.0, 0.86, 0.6))
imp_l.visible_glossy = False          # warm diffuse spill only: no specular dot landing on a pupil
if LI['cubekey'] > 0:
    cp_ = cube.matrix_world.translation.copy()
    cube_key = area('cube_key', tuple(cp_ + Vector((1.6, -2.4, 2.2))), tuple(cp_), LI['cubekey'], 1.5, (1.0, 0.93, 0.85))
    # light linking: everything except the sphere (its square reflection cut the Kugel's right brow);
    # the tetra keeps it too, it gets part of its colour from this light
    nosphere_recv = bpy.data.collections.new('cube_key_receivers')
    for o in [cube, cross, tetra] + drops:
        nosphere_recv.objects.link(o)
    cube_key.light_linking.receiver_collection = nosphere_recv

# ------------------------------------------------------------------ camera
cd = bpy.data.cameras.new('cam'); cd.lens = LENS; cd.sensor_width = 36; cd.sensor_fit = 'HORIZONTAL'
cam = bpy.data.objects.new('cam', cd); sc.collection.objects.link(cam)
cam.location = (0, 0, 0)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.camera = cam

# screen-space metadata for the 2D compositing (512-reference pixels)
from bpy_extras.object_utils import world_to_camera_view
bpy.context.view_layer.update()


def scr(p):
    v = world_to_camera_view(sc, cam, Vector(p))
    return [v.x * REF, (1 - v.y) * REF]


meta = {'head': {'center': scr(head.matrix_world.translation), 'radius': HEAD['size']},
        'cube': {'center': scr(cube.matrix_world.translation)},
        'cross': {'center': scr(cross.matrix_world.translation), 'size': CROSS['size']},
        'tetra': {'center': scr(tetra.matrix_world.translation), 'size': TETRA['size'], 'show': TETRA['show']},
        'impact': [IMP[0], IMP[1]]}
_base, _ext = os.path.splitext(OUT)
with open(_base + '_meta.json', 'w') as fh:
    json.dump(meta, fh, indent=1)

# ------------------------------------------------------------------ beauty render
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)

# ------------------------------------------------------------------ ID render (flat emission colours) for 2D masks
ids = {'comet_sphere': (1, 0, 0), 'comet_cube': (1, 0, 1), 'cross': (0, 1, 0), 'tetra': (0, 0, 1)}
cache = {}
for o in sc.objects:
    if o.type == 'MESH':
        rgb = ids.get(o.name, (0, 1, 1) if o.name.startswith('drop') else (0, 0, 0))
        if rgb not in cache:
            cache[rgb] = emit_mat('id_%d%d%d' % rgb, rgb)
        o.data.materials.clear(); o.data.materials.append(cache[rgb])
        o.visible_glossy = True
sc.cycles.samples = 16
sc.cycles.use_denoising = False
w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.0
for o in sc.objects:
    if o.type == 'LIGHT':
        o.hide_render = True
sc.render.filepath = _base + '_id' + _ext
bpy.ops.render.render(write_still=True)
print('wrote', OUT, _base + '_id' + _ext)
