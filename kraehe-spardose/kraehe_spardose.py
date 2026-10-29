# -*- coding: utf-8 -*-
"""
Krähen-Spardose  –  prozeduraler Modell-Generator für Blender (getestet mit 4.5 LTS)

Erzeugt eine detaillierte Krähe mit ausgebreiteten Flügeln auf rundem Sockel:
  * hohler Körper (Wandstärke 3 mm) mit Münzschlitz oben auf dem Rücken
  * Schraubverschluss unten am Schwanz: Innengewinde im Körper + Schraubdeckel
    mit Außengewinde, Griffsteg und Rändelrand (Rechtsgewinde: im Uhrzeigersinn zu)
  * einzeln modellierte Federn (Schwingen, Decken, Schwanz, Halskrause, Brust)
  * Schnabel geöffnet, rote Augen mit "bösen" Brauen, geschuppte Beine und Krallen

Einheiten: 1 Blender-Einheit = 1 mm (Szene ist auf Millimeter eingestellt).

Benutzung
  GUI:   Blender öffnen -> Arbeitsbereich "Scripting" -> Öffnen -> Run Script
  Shell: blender -b --python kraehe_spardose.py -- --blend out.blend --stl stl_ordner

Alle Teile landen in der Collection "Kraehe_Spardose". Ein erneuter Lauf ersetzt sie.
"""
import bpy
import bmesh
import math
import os
import random
import sys
import time

import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

# ============================================================================
# Parameter (mm)
# ============================================================================
WAND = 3.0                    # Wandstärke des hohlen Körpers
VOXEL = 0.85                  # Auflösung des Körpers (kleiner = feiner, langsamer)

GEWINDE_RADIUS = 16.0         # Außenradius Deckel-Gewinde (Ø 32 mm)
GEWINDE_TIEFE = 1.4
GEWINDE_STEIGUNG = 3.0
GEWINDE_SPIEL = 0.4           # radiales Spiel (FDM-tauglich)
GEWINDE_SPIEL_AXIAL = 0.06    # axiales Spiel als Anteil der Steigung
KRAGEN_LAENGE = 13.0          # Länge des Innengewindes im Körper
KRAGEN_RADIUS = 21.0
AUFLAGE_RADIUS = 25.0         # plane Auflagefläche für den Deckel
STOPFEN_LAENGE = 12.0         # Gewindelänge am Deckel
STOPFEN_INNEN = 11.5          # Deckel ist innen hohl (Becher)

SCHLITZ = (34.0, 5.5)         # Münzschlitz Länge x Breite
DACH_STEIGUNG = 0.8           # Innendecke: 0.8 ≈ 39° zur Waagrechten (druckt ohne Stützen)

SOCKEL_Z = 14.0              # Höhe der Sockel-Unterseite beim Aufbau (wird am Ende auf 0 gesetzt)

SEED = 7
RNG = random.Random(SEED)

COLL_NAME = "Kraehe_Spardose"


def log(*a):
    print("[Kraehe]", *a, flush=True)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ============================================================================
# Mesh-Werkzeuge
# ============================================================================
class Acc:
    """Sammelt Geometrie vieler Einzelteile und baut daraus ein Objekt."""

    def __init__(self):
        self.V, self.F, self.n = [], [], 0

    def add(self, V, F):
        V = np.asarray(V, dtype=np.float64).reshape(-1, 3)
        n = self.n
        self.V.append(V)
        self.F.extend([[i + n for i in f] for f in F])
        self.n += len(V)

    def add_mirrored(self, V, F):
        V = np.array(V, dtype=np.float64).reshape(-1, 3)
        V[:, 0] *= -1.0
        self.add(V, [list(reversed(f)) for f in F])

    def build(self, name, coll, mat=None, recalc=False):
        V = np.concatenate(self.V) if self.V else np.zeros((0, 3))
        return make_object(name, V, self.F, coll, mat, recalc=recalc)


def make_object(name, V, F, coll, mat=None, smooth=True, recalc=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(V).tolist(), [], F)
    me.validate(clean_customdata=False)
    if recalc:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if smooth:
        set_smooth(ob)
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def set_smooth(ob, angle=None):
    me = ob.data
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if angle is not None and hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=angle)
    me.update()


def apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


BOOL_SOLVER = None


def boolean(ob, other, op):
    """op: 'UNION' | 'DIFFERENCE' | 'INTERSECT'. Manifold-Solver wenn möglich, sonst Exact."""
    global BOOL_SOLVER
    solvers = [i.identifier for i in bpy.types.BooleanModifier.bl_rna.properties["solver"].enum_items]
    order = [s for s in ("MANIFOLD", "EXACT") if s in solvers]
    before = len(ob.data.polygons)
    for solver in order:
        mod = ob.modifiers.new("bool", "BOOLEAN")
        mod.operation = op
        mod.object = other
        mod.solver = solver
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        if len(me.polygons) > 0 or op == "INTERSECT":
            old = ob.data
            ob.data = me
            if old.users == 0:
                bpy.data.meshes.remove(old)
            BOOL_SOLVER = solver
            return ob
        bpy.data.meshes.remove(me)
        log("  Boolean %s mit %s fehlgeschlagen (%d Flächen) – nächster Solver" % (op, solver, before))
    raise RuntimeError("Boolean fehlgeschlagen: %s %s" % (ob.name, op))


def remove_object(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me is not None and getattr(me, "users", 1) == 0:
        if isinstance(me, bpy.types.Mesh):
            bpy.data.meshes.remove(me)


def mesh_arrays(ob, world=True):
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if world:
        M = np.array(ob.matrix_world)
        co = co @ M[:3, :3].T + M[:3, 3]
    return co


def bvh_of(ob):
    me = ob.data
    co = mesh_arrays(ob)
    polys = [tuple(p.vertices) for p in me.polygons]
    return BVHTree.FromPolygons(co.tolist(), polys)


# ----------------------------------------------------------------------------
# Grundformen
# ----------------------------------------------------------------------------
def lathe(profile, K=48):
    """Rotationskörper um Z. profile: [(r, z), ...] von unten nach oben, r=0 => Pol."""
    V, F, rings = [], [], []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([len(V)])
            V.append((0.0, 0.0, z))
        else:
            idx = []
            for k in range(K):
                a = 2 * math.pi * k / K
                idx.append(len(V))
                V.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(idx)
    for a, b in zip(rings[:-1], rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(K):
            k1 = (k + 1) % K
            if len(a) == 1:
                F.append([a[0], b[k1], b[k]])
            elif len(b) == 1:
                F.append([a[k], a[k1], b[0]])
            else:
                F.append([a[k], a[k1], b[k1], b[k]])
    return np.array(V), F


def ellipsoid(center, radii, K=40, rings=20, rot=None):
    prof = []
    for i in range(rings + 1):
        phi = -math.pi / 2 + math.pi * i / rings
        prof.append((math.cos(phi) if 0 < i < rings else 0.0, math.sin(phi)))
    V, F = lathe(prof, K)
    V = V * np.array(radii)
    if rot is not None:
        V = V @ np.array(rot).T
    return V + np.array(center), F


def loft(path, radii, K=16, shape=None, caps=(True, True), tips=(0.0, 0.0), up=(0, 0, 1)):
    """Schlauch entlang eines Pfads. radii: Zahl oder (rx, ry) je Pfadpunkt.
    shape(a, t) -> (cx, cy) erlaubt eigene Querschnitte (gegen den Uhrzeigersinn)."""
    P = [Vector(p) for p in path]
    n = len(P)
    T = []
    for i in range(n):
        a, b = P[max(i - 1, 0)], P[min(i + 1, n - 1)]
        T.append((b - a).normalized())
    up = Vector(up)
    Y = up - T[0] * up.dot(T[0])
    if Y.length < 1e-6:
        Y = Vector((1, 0, 0)) - T[0] * T[0].x
    Y.normalize()
    V, F = [], []
    for i in range(n):
        if i > 0:
            Y = T[i - 1].rotation_difference(T[i]) @ Y
            Y = (Y - T[i] * Y.dot(T[i])).normalized()
        X = Y.cross(T[i])
        r = radii[i]
        rx, ry = (r, r) if not isinstance(r, (tuple, list)) else r
        t = i / (n - 1)
        for k in range(K):
            a = 2 * math.pi * k / K
            cx, cy = shape(a, t) if shape else (math.cos(a), math.sin(a))
            V.append(P[i] + X * (rx * cx) + Y * (ry * cy))
    for i in range(n - 1):
        for k in range(K):
            k1 = (k + 1) % K
            F.append([i * K + k, i * K + k1, (i + 1) * K + k1, (i + 1) * K + k])
    if caps[0]:
        c = len(V)
        V.append(P[0] - T[0] * tips[0])
        for k in range(K):
            F.append([c, (k + 1) % K, k])
    if caps[1]:
        c = len(V)
        V.append(P[-1] + T[-1] * tips[1])
        b = (n - 1) * K
        for k in range(K):
            F.append([c, b + k, b + (k + 1) % K])
    return np.array([v[:] for v in V]), F


def resample(path, radii, n):
    """Glättet einen Pfad (Catmull-Rom) und interpoliert die Radien."""
    P = np.array(path, float)
    R = np.array(radii, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out_p, out_r = [], []
    m = len(path) - 1
    for k in range(n + 1):
        x = k / n * m
        i = min(int(x), m - 1)
        t = x - i
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        out_p.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                            + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        out_r.append(R[i] * (1 - t) + R[i + 1] * t)
    return [tuple(p) for p in out_p], [tuple(r) if np.ndim(r) else float(r) for r in out_r]


def prism(poly, z0, z1, chamfer=0.0, inset_poly=None):
    """Extrudiertes konvexes Polygon (gegen den Uhrzeigersinn) mit optionaler Fase oben."""
    rings = [[(x, y, z0) for x, y in poly], [(x, y, z1 - chamfer) for x, y in poly]]
    if chamfer > 0:
        rings.append([(x, y, z1) for x, y in inset_poly])
    K = len(poly)
    V = [v for r in rings for v in r]
    F = []
    for i in range(len(rings) - 1):
        for k in range(K):
            k1 = (k + 1) % K
            F.append([i * K + k, i * K + k1, (i + 1) * K + k1, (i + 1) * K + k])
    F.append(list(reversed(range(K))))
    F.append([(len(rings) - 1) * K + k for k in range(K)])
    return np.array(V), F


def stadium(length, width, n=10):
    r = width / 2
    h = length / 2 - r
    pts = []
    for i in range(n + 1):
        a = -math.pi / 2 + math.pi * i / n
        pts.append((h + r * math.cos(a), r * math.sin(a)))
    for i in range(n + 1):
        a = math.pi / 2 + math.pi * i / n
        pts.append((-h + r * math.cos(a), r * math.sin(a)))
    return pts


def roof_solid(apex, half_len, slope=1.0):
    """Geschlossener Körper unter einem 45°-Dach, dessen First entlang X über apex verläuft."""
    xs = np.linspace(apex.x - 90, apex.x + 90, 121)
    ys = np.linspace(apex.y - 100, apex.y + 100, 133)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    dx = np.maximum(np.abs(X - apex.x) - half_len, 0.0)
    Z = apex.z - slope * np.sqrt(dx ** 2 + (Y - apex.y) ** 2)
    zb = apex.z - 300.0
    nI, nJ = X.shape
    top = np.stack([X, Y, Z], -1).reshape(-1, 3)
    bot = np.stack([X, Y, np.full_like(Z, zb)], -1).reshape(-1, 3)
    off = nI * nJ
    idx = lambda i, j: i * nJ + j
    F = []
    for i in range(nI - 1):
        for j in range(nJ - 1):
            F.append([idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)])
            F.append([off + idx(i, j), off + idx(i, j + 1), off + idx(i + 1, j + 1), off + idx(i + 1, j)])
    ring = [(i, 0) for i in range(nI)] + [(nI - 1, j) for j in range(1, nJ)] + \
           [(i, nJ - 1) for i in range(nI - 2, -1, -1)] + [(0, j) for j in range(nJ - 2, 0, -1)]
    for a, b in zip(ring, ring[1:] + ring[:1]):
        F.append([idx(*a), off + idx(*a), off + idx(*b), idx(*b)])
    return np.concatenate([top, bot]), F


def point_inside(bvh, p):
    """Strahl-Paritätstest: liegt p innerhalb des geschlossenen Netzes?"""
    d = Vector((0.0123, 0.0071, 1.0)).normalized()
    o = Vector(p)
    n = 0
    for _ in range(64):
        hit = bvh.ray_cast(o, d)
        if hit[0] is None:
            break
        n += 1
        o = hit[0] + d * 1e-4
    return n % 2 == 1


def cav_volume(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    v = bm.calc_volume(signed=True)
    bm.free()
    return v


def frame_to_world(V, origin, ex, ey, ez):
    M = np.array([ex[:], ey[:], ez[:]])
    return np.asarray(V) @ M + np.array(origin[:])


def basis_from_axis(d):
    d = Vector(d).normalized()
    helper = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
    e1 = helper.cross(d).normalized()
    e2 = d.cross(e1)
    return e1, e2, d


# ----------------------------------------------------------------------------
# Feder
# ----------------------------------------------------------------------------
# >>> TEIL feder
def feather(L, W, th=1.5, point=0.0, asym=1.0, bend=0.05, cup=0.10, notches=0,
            root_w=0.2, taper=0.55, rachis=0.45, nW=4, rng=RNG, jag=0.0, barbs=0.0, barb_gap=2.8):
    """Einzelne Feder lokal: x = Länge, y = Breite, z = oben. Geschlossener Körper.
    barbs > 0 graviert schräge Federäste (Rillentiefe in mm) in die Oberseite."""
    nL = max(10, int(L / 2.0))
    if barbs > 0:
        nL = max(nL, int(L / 0.65))
        nW = max(nW, 6)
    t = np.linspace(0.0, 1.0, nL + 1)
    s = np.linspace(-1.0, 1.0, 2 * nW + 1)
    base = root_w + (1 - root_w) * smoothstep(0.0, 0.32, t)
    x = np.clip((t - taper) / (1 - taper), 0, 1)
    tipf = (1 - point) * np.sqrt(np.clip(1 - x * x, 0, 1)) + point * (1 - x) ** 0.9
    base = base * np.maximum(tipf, 0.07)
    wpos = base.copy()
    wneg = base * asym
    for _ in range(notches):
        tn = rng.uniform(0.38, 0.9)
        dp = rng.uniform(0.25, 0.5)
        prof = dp * np.clip(1 - np.abs(t - tn) / 0.055, 0, 1)
        if rng.random() < 0.5:
            wpos = wpos * (1 - prof)
        else:
            wneg = wneg * (1 - prof)
    if jag > 0:
        wpos = wpos * (1 - jag * np.array([rng.random() for _ in t]) * (t > 0.3))
        wneg = wneg * (1 - jag * np.array([rng.random() for _ in t]) * (t > 0.3))
    T, S = np.meshgrid(t, s, indexing="ij")
    Wd = np.where(S < 0, wneg[:, None], wpos[:, None]) * (W / 2)
    X = T * L
    Y = S * Wd
    camber = -cup * (W / 2) * S ** 2 - bend * L * T ** 2
    h = th * 0.5 * (0.62 + 0.38 * (1 - np.abs(S))) * (1 - 0.3 * T)
    r = rachis * th * np.exp(-(S / 0.16) ** 2) * (1 - 0.7 * T)
    Zt = camber + h + r
    if barbs > 0:
        A = np.abs(S)
        phase = (X - 0.9 * np.abs(Y)) / barb_gap
        mask = smoothstep(0.14, 0.3, A) * (1 - smoothstep(0.82, 1.0, A)) * smoothstep(0.08, 0.2, T)
        Zt = Zt - barbs * mask * (0.5 + 0.5 * np.cos(2 * np.pi * phase)) ** 3
    Zb = camber - h * 0.8 - 0.25 * r
    top = np.stack([X, Y, Zt], -1).reshape(-1, 3)
    bot = np.stack([X, Y, Zb], -1).reshape(-1, 3)
    nI, nJ = nL + 1, 2 * nW + 1
    off = nI * nJ
    V = np.concatenate([top, bot])
    idx = lambda i, j: i * nJ + j
    F = []
    for i in range(nI - 1):
        for j in range(nJ - 1):
            F.append([idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)])
            F.append([off + idx(i, j), off + idx(i, j + 1), off + idx(i + 1, j + 1), off + idx(i + 1, j)])
    ring = [(i, 0) for i in range(nI)] + [(nI - 1, j) for j in range(1, nJ)] + \
           [(i, nJ - 1) for i in range(nI - 2, -1, -1)] + [(0, j) for j in range(nJ - 2, 0, -1)]
    for a, b in zip(ring, ring[1:] + ring[:1]):
        ia, ib = idx(*a), idx(*b)
        F.append([ia, off + ia, off + ib, ib])
    return V, F
# <<< TEIL feder


def place(V, P, D, U, roll=0.0):
    X = Vector(D).normalized()
    U = Vector(U)
    Z = (U - X * U.dot(X)).normalized()
    Y = Z.cross(X)
    if roll:
        c, s = math.cos(roll), math.sin(roll)
        Y, Z = Y * c + Z * s, Z * c - Y * s
    return frame_to_world(V, P, X, Y, Z)


def on_surface(bvh, inner, direction, embed=1.0):
    d = Vector(direction).normalized()
    hit = bvh.ray_cast(Vector(inner) + d * 400.0, -d)
    if hit[0] is None:
        return None, None
    n = hit[1].normalized()
    return hit[0] - n * embed, n


SPERRZONEN = []  # (Ursprung, Achse, Radius, z0, z1): hier dürfen keine Federn hin (Deckel)


def in_sperrzone(V):
    for O, d, R, z0, z1 in SPERRZONEN:
        rel = np.asarray(V) - np.array(O[:])
        z = rel @ np.array(d[:])
        rho = np.linalg.norm(rel - np.outer(z, np.array(d[:])), axis=1)
        if np.any((rho < R) & (z > z0) & (z < z1)):
            return True
    return False


def surface_feather(acc, bvh, inner, direction, flow, L, W, lift=0.25, embed=1.0, **kw):
    p, n = on_surface(bvh, inner, direction, embed)
    if p is None:
        return False
    flow = Vector(flow)
    tang = flow - n * flow.dot(n)
    if tang.length < 1e-6:
        return False
    tang.normalize()
    D = tang * math.cos(lift) + n * math.sin(lift)
    V, F = feather(L, W, **kw)
    V = place(V, p, D, n, roll=RNG.uniform(-0.12, 0.12))
    if in_sperrzone(V):
        return False
    acc.add(V, F)
    return True


# ============================================================================
# Materialien
# ============================================================================
def material(name, color, rough=0.55, spec=0.35, emission=None, strength=0.0, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):   # ab Blender 5 nutzen Materialien immer Nodes
        m.use_nodes = True
    m.diffuse_color = (*color, 1.0)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    for key in ("Specular IOR Level", "Specular"):
        if key in b.inputs:
            b.inputs[key].default_value = spec
            break
    if coat and "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    if emission is not None:
        for key in ("Emission Color", "Emission"):
            if key in b.inputs:
                b.inputs[key].default_value = (*emission, 1.0)
                break
        b.inputs["Emission Strength"].default_value = strength
    return m


# ============================================================================
# Körper
# ============================================================================
MB_K = 0.574  # Oberfläche eines einzelnen Metaballs liegt bei 0.574 * Radius


# >>> TEIL koerperform
def koerper_metaballs(ell, q):
    """Rumpf, Brust, Bauch, Bürzel, Oberschenkel, Schultern. ell(mitte, halbachsen, rotation)."""
    ell((0, 6, 80), (31, 46, 29), q(x=-4))           # Rumpf
    ell((0, -26, 76), (28, 27, 30))                  # Brust
    ell((0, 4, 66), (25, 32, 17))                    # Bauch
    ell((0, 44, 84), (16, 20, 12), q(x=6))           # Bürzel
    ell((0, 60, 83), (10, 14, 6.5), q(x=10))         # Schwanzansatz
    for sx in (-1, 1):
        ell((sx * 14, -6, 58), (10.5, 12, 14))       # Oberschenkel ("Hosen")
        ell((sx * 24, -16, 92), (11, 15, 9), q(y=sx * 20))  # Schulter
# <<< TEIL koerperform


# >>> TEIL kopfform
def kopf_metaballs(ell, q):
    """Hals, Kopf, Wangen, Stirn."""
    ell((0, -50, 85), (22, 20, 24))                  # Hals (Krause)
    ell((0, -70, 91), (18.5, 22, 18), q(x=8))        # Kopf
    ell((0, -82, 85), (13, 14, 11))                  # Wangen / Kinn
    ell((0, -85, 94), (10, 12, 8.5), q(x=12))        # Stirn zum Schnabel
# <<< TEIL kopfform


def metaball_body(coll):
    mb = bpy.data.metaballs.new("KoerperMB")
    mb.resolution = 1.4
    mb.render_resolution = 1.4
    mb.threshold = 0.6

    def ell(c, semi, rot=None, stiff=2.0):
        e = mb.elements.new(type="ELLIPSOID")
        e.co = c
        r = max(semi)
        e.radius = r / MB_K
        e.size_x, e.size_y, e.size_z = semi[0] / r, semi[1] / r, semi[2] / r
        e.stiffness = stiff
        if rot is not None:
            e.rotation = rot

    from mathutils import Euler
    q = lambda x=0, y=0, z=0: Euler((math.radians(x), math.radians(y), math.radians(z))).to_quaternion()

    koerper_metaballs(ell, q)
    kopf_metaballs(ell, q)
    ob = bpy.data.objects.new("KoerperMB", mb)
    coll.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.metaballs.remove(mb)
    body = bpy.data.objects.new("Koerper", me)
    coll.objects.link(body)
    rm = body.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = VOXEL
    rm.adaptivity = 0.0
    sm = body.modifiers.new("smooth", "SMOOTH")
    sm.factor = 0.6
    sm.iterations = 6
    apply_modifiers(body)
    return body


def landing_frame(bvh, c0, d0):
    """Bestimmt Achse und plane Auflagefläche für den Schraubverschluss."""
    d = Vector(d0).normalized()
    for _ in range(3):
        hit = bvh.ray_cast(Vector(c0), d)
        d = (d + hit[1].normalized()).normalized()
    e1, e2, d = basis_from_axis(d)
    ts = []
    for k in range(24):
        a = 2 * math.pi * k / 24
        o = Vector(c0) + (e1 * math.cos(a) + e2 * math.sin(a)) * AUFLAGE_RADIUS
        hit = bvh.ray_cast(o, d)
        ts.append((hit[0] - o).dot(d))
    tp = min(ts) - 0.8
    return Vector(c0) + d * tp, e1, e2, d


# ----------------------------------------------------------------------------
# Gewinde
# ----------------------------------------------------------------------------
def thread_profile(u, crest, flank):
    d = np.abs(np.mod(u, 1.0) - 0.5)
    return np.clip(1 - (d - crest / 2) / flank, 0, 1)


R_MIN = GEWINDE_RADIUS - GEWINDE_TIEFE


def r_aussen(theta, z):
    u = z / GEWINDE_STEIGUNG - theta / (2 * math.pi)
    lead = smoothstep(-STOPFEN_LAENGE, -STOPFEN_LAENGE + 1.6 * GEWINDE_STEIGUNG, z)
    r = R_MIN + GEWINDE_TIEFE * thread_profile(u, 0.2, 0.27) * lead
    tip = np.clip(0.6 - (z + STOPFEN_LAENGE), 0, 0.6)   # Fase an der Spitze
    return r - tip


def r_innen(theta, z):
    u = z / GEWINDE_STEIGUNG - theta / (2 * math.pi)
    r = R_MIN + GEWINDE_SPIEL + GEWINDE_TIEFE * thread_profile(u, 0.2 + 2 * GEWINDE_SPIEL_AXIAL, 0.27)
    rmax = R_MIN + GEWINDE_SPIEL + GEWINDE_TIEFE + 0.6
    r = np.maximum(r, rmax + z)                          # Einlauffase außen
    r = np.maximum(r, rmax - (z + KRAGEN_LAENGE))        # Fase innen
    return r


def tube_mod(z0, z1, dz, K, r_out, r_in=None):
    """Rohr/Zylinder mit winkel- und höhenabhängigem Radius (für Gewinde und Rändel)."""
    nz = max(2, int(math.ceil((z1 - z0) / dz)) + 1)
    zs = np.linspace(z0, z1, nz)
    th = np.linspace(0, 2 * math.pi, K, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    V = []
    for z in zs:
        r = r_out(th, z) * np.ones(K)
        V.append(np.stack([r * c, r * s, np.full(K, z)], -1))
    no = len(V) * K
    if r_in is not None:
        for z in zs:
            r = r_in(th, z) * np.ones(K)
            V.append(np.stack([r * c, r * s, np.full(K, z)], -1))
    V = np.concatenate(V)
    F = []
    for i in range(nz - 1):
        for k in range(K):
            k1 = (k + 1) % K
            F.append([i * K + k, i * K + k1, (i + 1) * K + k1, (i + 1) * K + k])
            if r_in is not None:
                a = no + i * K
                b = no + (i + 1) * K
                F.append([a + k, b + k, b + k1, a + k1])
    top = (nz - 1) * K
    if r_in is not None:
        for k in range(K):
            k1 = (k + 1) % K
            F.append([top + k, top + k1, no + top + k1, no + top + k])
            F.append([k, no + k, no + k1, k1])
    else:
        c0, c1 = len(V), len(V) + 1
        V = np.concatenate([V, [[0, 0, z0], [0, 0, z1]]])
        for k in range(K):
            k1 = (k + 1) % K
            F.append([c0, k1, k])
            F.append([c1, top + k, top + k1])
    return V, F


# ============================================================================
# Flügel
# ============================================================================
# >>> TEIL fluegel
WS = 0.78  # Flügel-Skalierung

BONE = [(-6.0, 2.0), (42.0, 16.0), (88.0, -2.0), (122.0, 8.0)]  # Schulter, Ellbogen, Handgelenk, Handspitze


def bone_at(u):
    us = [p[0] for p in BONE]
    vs = [p[1] for p in BONE]
    return float(np.interp(u, us, vs))


def flight_angle(u):
    """Richtung der Federn (Grad, 0 = nach außen, 90 = nach hinten)."""
    if u <= 88:
        return 100.0 - 10.0 * (u / 88.0)
    return lerp(88.0, 14.0, (u - 88.0) / 34.0)


def wing_geometry():
    """Linker Flügel in lokalen Koordinaten (u außen, v hinten, n oben). Liefert Liste
    (V, F, hand) – hand=True für Teile, die mit der Hand mitgedreht werden."""
    parts = []

    def fe(u, vofs, n, ang, L, W, hand=False, **kw):
        a = math.radians(ang)
        D = Vector((math.cos(a), math.sin(a), -0.035))
        P = Vector((u * WS, (bone_at(u) + vofs) * WS, n))
        V, F = feather(L * WS, W * WS, **kw)
        parts.append((place(V, P, D, (0, 0, 1), roll=RNG.uniform(-0.05, 0.05)), F, hand))

    # Handschwingen (10)
    plens = [80, 84, 88, 93, 98, 103, 106, 107, 104, 95]
    for i in range(10):
        f = i / 9
        u = lerp(89.0, 121.0, f)
        ang = lerp(80.0, 12.0, f) + RNG.uniform(-2, 2)
        outer = i >= 5
        fe(u, 2.5, 0.25 + 0.42 * i, ang, plens[i], lerp(17, 13.5, f), hand=True,
           th=1.6, point=0.25 if outer else 0.05, asym=0.55 if outer else 0.8,
           taper=0.42 if outer else 0.6, notches=1 + (i % 2), bend=0.05, cup=0.12, jag=0.08, barbs=0.35)
    # Armschwingen (12) + Schirmfedern (3)
    for i in range(12):
        f = i / 11
        u = lerp(6.0, 86.0, f)
        ang = 97.0 - 8.0 * f + RNG.uniform(-2, 2)
        fe(u, 2.5, 4.4 - 0.36 * i, ang, lerp(64, 72, f), 19, th=1.6, point=0.0,
           taper=0.62, notches=1, bend=0.04, cup=0.12, jag=0.06, barbs=0.35)
    for i in range(3):
        fe(-4.0 + 4.5 * i, 4.0, 5.0 + 0.3 * i, 108 - 4 * i, 56, 19, th=1.6, taper=0.6, notches=1, bend=0.05,
           barbs=0.35)
    # Große Decken
    for i in range(24):
        u = lerp(-2.0, 120.0, i / 23)
        ang = flight_angle(u) + RNG.uniform(-3, 3)
        fe(u, 1.0, 6.2, ang, lerp(38, 31, i / 23), 14, hand=u > 88, th=1.4, point=0.15,
           taper=0.5, notches=RNG.choice((0, 1)), bend=0.07, cup=0.14, jag=0.06, barbs=0.3, barb_gap=2.4)
    # Mittlere Decken
    for i in range(24):
        u = lerp(-4.0, 116.0, i / 23) + 2.5
        ang = flight_angle(u) - 6 + RNG.uniform(-4, 4)
        fe(u, -1.5, 7.8, ang, lerp(25, 20, i / 23), 12, hand=u > 88, th=1.3, point=0.3,
           taper=0.45, bend=0.08, cup=0.15, jag=0.1)
    # Kleine Decken (zwei Reihen, schuppenartig)
    for row, (vofs, n, L) in enumerate(((-3.5, 9.2, 16.0), (-7.5, 10.4, 13.0))):
        for i in range(26):
            u = lerp(-10.0, 112.0 - row * 6, i / 25) + row * 2.3
            ang = flight_angle(u) - 12 + RNG.uniform(-6, 6)
            fe(u, vofs, n, ang, L, 10, hand=u > 88, th=1.2, point=0.35, taper=0.45,
               bend=0.10, cup=0.16, jag=0.12)
    # Daumenfittich
    for i in range(3):
        fe(86.0 + 2 * i, -6.0, 9.5 + 0.4 * i, -18 + 10 * i, 30 - 3 * i, 9, hand=True,
           th=1.3, point=0.4, taper=0.4, bend=0.04)
    # Armknochen / Vorderkante
    path, radii = [], []
    for u in np.linspace(-10.0, 122.0, 26):
        path.append((u * WS, (bone_at(max(u, -6.0)) - 1.0) * WS, 3.8 - 0.8 * (u / 122.0)))
        rr = float(np.interp(u, [-10, 0, 42, 88, 122], [9.5, 8.5, 6.5, 5.0, 3.0])) * WS
        radii.append((rr * 1.15, rr * 0.68))
    V, F = loft(path, radii, K=18, tips=(2.0, 2.0))
    parts.append((V, F, "arm"))
    return parts


def wing_transform(dihedral=14, sweep=18, twist=22, hand_lift=10):
    def rx(a):
        return Matrix.Rotation(math.radians(a), 3, "X")

    def ry(a):
        return Matrix.Rotation(math.radians(a), 3, "Y")

    def rz(a):
        return Matrix.Rotation(math.radians(a), 3, "Z")

    M = rz(sweep) @ ry(-dihedral) @ rx(twist)
    wrist = Vector((88.0 * WS, bone_at(88.0) * WS, 6.0))
    H = ry(-hand_lift) @ rz(6)
    return np.array(M), np.array(H), np.array(wrist)


def build_wing(shoulder, mirror, coll, mat):
    M, H, wrist = wing_transform()
    acc = Acc()
    skipped = 0
    for V, F, hand in wing_geometry():
        V = np.asarray(V)
        if hand == "arm":
            # Handteil des Knochens sanft mitdrehen
            w = smoothstep(80 * WS, 95 * WS, V[:, 0])[:, None]
            Vh = (V - wrist) @ H.T + wrist
            V = V * (1 - w) + Vh * w
        elif hand:
            V = (V - wrist) @ H.T + wrist
        V = V @ M.T + np.array(shoulder[:])
        if hand != "arm" and in_sperrzone(V * np.array([-1.0 if mirror else 1.0, 1, 1])):
            skipped += 1
            continue
        if mirror:
            acc.add_mirrored(V, F)
        else:
            acc.add(V, F)
    if skipped:
        log("  %d Federn wegen Münzschlitz/Deckel ausgelassen" % skipped)
    name = "Fluegel_rechts" if mirror else "Fluegel_links"
    return acc.build(name, coll, mat)


def schulter_punkt(outer_bvh):
    """Ansatzpunkt des linken Flügels auf der Körperoberfläche (rechts wird gespiegelt)."""
    sdir = Vector((1, -0.1, 0.32)).normalized()
    hit = outer_bvh.ray_cast(Vector((0, -16, 88)) + sdir * 300, -sdir)
    return hit[0] - hit[1] * 3.0
# <<< TEIL fluegel


# ============================================================================
# Bauteile (jeweils zwischen ">>> TEIL" und "<<< TEIL")
# ============================================================================
# >>> TEIL schlitz
def schlitz_geometrie():
    """Schnittkörper für den Münzschlitz im Schlitz-Koordinatensystem
    (x = quer zum Körper, z = Oberflächennormale, Ursprung auf der Oberfläche).
    Liste aus (Operation, (V, F)). Die Durchgangsöffnung muss SCHLITZ groß bleiben."""
    return [
        ("DIFFERENCE", prism(stadium(*SCHLITZ), -14.0, 6.0)),
        # Rahmen um den Schlitz (leicht vertieft)
        ("DIFFERENCE", prism(stadium(SCHLITZ[0] + 7, SCHLITZ[1] + 7), -0.9, 6.0)),
    ]
# <<< TEIL schlitz


# >>> TEIL kopf
def build_kopf(outer_bvh, det, c_det, m_beak, m_eye, m_pupil):
    """Schnabel, Augen, Brauen, Nasenborsten, Kopffedern, Halskrause.
    Federn kommen in den Sammler det; Rückgabe: (Schnabel, Augen, Pupillen)."""
    beak = Acc()

    # Oberschnabel
    def upper_shape(a, t):
        c, s = math.cos(a), math.sin(a)
        if s >= 0:
            return c * (1 - 0.25 * s ** 4), s ** 0.85
        return c, s * 0.35

    # (y, Oberkante, Unterkante, halbe Breite) – kräftiger, gebogener Rabenschnabel
    up = [(-84, 101.0, 86.0, 10.0), (-95, 97.0, 86.0, 8.6), (-105, 93.5, 85.0, 6.9), (-114, 89.0, 83.0, 5.3),
          (-121, 84.0, 79.5, 3.9), (-126, 78.5, 75.0, 2.5), (-128.5, 73.5, 71.0, 1.3)]
    up_path = [(0, y, lo + (hi - lo) / 1.35 * 0.35) for y, hi, lo, w in up]
    up_r = [(w, (hi - lo) / 1.35) for y, hi, lo, w in up]
    up_path, up_r = resample(up_path, up_r, 40)
    V, F = loft(up_path, up_r, K=32, shape=upper_shape, tips=(0, 1.6), up=(0, 0, 1))
    beak.add(V, F)

    def lower_shape(a, t):
        c, s = math.cos(a), math.sin(a)
        if s >= 0:
            return c, s * 0.3
        return c * (1 - 0.2 * s ** 4), -((-s) ** 0.9)

    lo = [(-84, 84.5, 76.0, 9.0), (-95, 84.0, 78.0, 7.6), (-105, 80.0, 75.0, 6.0), (-113, 76.0, 72.0, 4.4),
          (-119, 72.0, 69.2, 2.6), (-121.5, 70.2, 68.6, 1.2)]
    lo_path = [(0, y, hi - (hi - lo_) / 1.3 * 0.3) for y, hi, lo_, w in lo]
    lo_r = [(w, (hi - lo_) / 1.3) for y, hi, lo_, w in lo]
    lo_path, lo_r = resample(lo_path, lo_r, 30)
    V, F = loft(lo_path, lo_r, K=28, shape=lower_shape, tips=(0, 0.8), up=(0, 0, 1))
    beak.add(V, F)
    beak_ob = beak.build("Schnabel", c_det, m_beak)
    set_smooth(beak_ob, angle=math.radians(60))

    # Augen
    eye_acc, pupil_acc = Acc(), Acc()
    for sx in (1, -1):
        dirv = Vector((sx * 1.0, -0.62, 0.32)).normalized()
        p, n = on_surface(outer_bvh, (0, -80, 92), dirv, embed=0.0)
        r_eye = 5.2
        ec = p - n * 3.4                     # Auge steht ~1.8 mm vor
        V, F = ellipsoid(ec[:], (r_eye, r_eye, r_eye), K=32, rings=16)
        eye_acc.add(V, F)
        Vp, Fp = ellipsoid((0, 0, 0), (2.0, 2.0, 0.8), K=20, rings=10)
        e_1, e_2, e_3 = basis_from_axis(n)
        pupil_acc.add(frame_to_world(Vp, ec + n * (r_eye - 0.5), e_1, e_2, e_3), Fp)
        fwd = Vector((0, -1, 0))
        fwd = (fwd - n * fwd.dot(n)).normalized()
        upv = n.cross(fwd).normalized() * sx * -1
        if upv.z < 0:
            upv = -upv

        def snap(pt, lift):
            loc, nrm = outer_bvh.find_nearest(pt)[:2]
            return (loc + nrm.normalized() * lift)[:]

        # böse Braue: Wulst über dem Auge, schräg nach vorne-unten zum Schnabel
        brow = [snap(ec + upv * 6.2 - fwd * 8.0, 0.5), snap(ec + upv * 5.0 - fwd * 3.0, 1.6),
                snap(ec + upv * 4.0 + fwd * 1.5, 2.3), snap(ec + upv * 2.4 + fwd * 5.5, 1.8),
                snap(ec + upv * 0.6 + fwd * 9.0, 0.6)]
        brow, br = resample(brow, [(1.4, 1.8), (2.0, 2.4), (2.2, 2.4), (1.8, 1.9), (0.9, 1.0)], 16)
        V, F = loft(brow, br, K=14, tips=(1.0, 1.2), up=n[:])
        det.add(V, F)
        # Unterlid
        lid = [snap(ec - upv * 5.0 - fwd * 4.5, 0.6), snap(ec - upv * 5.6, 1.0), snap(ec - upv * 4.6 + fwd * 4.5, 0.6)]
        lid, lr = resample(lid, [0.8, 1.1, 0.8], 10)
        V, F = loft(lid, lr, K=10, tips=(0.8, 0.8), up=n[:])
        det.add(V, F)
    eye_ob = eye_acc.build("Augen", c_det, m_eye)
    pupil_ob = pupil_acc.build("Pupillen", c_det, m_pupil)

    # Nasenborsten über dem Schnabelansatz
    for i in range(11):
        f = i / 10
        a = lerp(-1.0, 1.0, f)
        dirv = Vector((math.sin(a) * 0.9, -1.0, 0.8 + 0.2 * math.cos(a))).normalized()
        surface_feather(det, outer_bvh, (0, -80, 90), dirv, (0, -1, -0.35), 10 - 3 * abs(a), 4.0,
                        lift=0.0, embed=0.6, th=0.9, point=0.8, taper=0.3, bend=0.10, cup=0.15, rachis=0.4)

    # Kopf: kleine schuppige Federn
    for ring, ang_el in enumerate(np.linspace(-15, 65, 6)):
        nring = 16 - ring
        for k in range(nring):
            yaw = lerp(-115, 115, (k + 0.5 * (ring % 2)) / nring)
            if abs(yaw) < 40 and ang_el < 30:
                continue
            el, yw = math.radians(ang_el), math.radians(yaw)
            dirv = Vector((math.sin(yw) * math.cos(el), -math.cos(yw) * math.cos(el) * 0.3 + 0.25, math.sin(el)))
            if dirv.length < 1e-3:
                continue
            surface_feather(det, outer_bvh, (0, -70, 90), dirv, (0, 1, -0.25), RNG.uniform(7.5, 9.5), 6.5,
                            lift=0.07, embed=0.7, th=1.0, point=0.35, taper=0.45, bend=0.12, cup=0.2,
                            rachis=0.25)
    # Halskrause (Hackles) – spitze, abstehende Federn
    rows = np.linspace(-70, -38, 8)
    for ri, y in enumerate(rows):
        nrow = 22
        for k in range(nrow):
            phi = 2 * math.pi * (k + 0.5 * (ri % 2)) / nrow + RNG.uniform(-0.08, 0.08)
            dirv = Vector((math.sin(phi), 0.0, math.cos(phi)))
            down = -math.cos(phi)  # 1 = Kehle
            throat = max(0.0, down)
            L = lerp(11, 21, throat) * lerp(1.0, 0.85, ri / 7) + RNG.uniform(-1.5, 1.5)
            if y < -62 and math.cos(phi) > 0.2:
                continue  # Oberkopf frei lassen
            flow = Vector((0, 1.0, -0.35 - 0.9 * throat))
            surface_feather(det, outer_bvh, (0, y, 84), dirv, flow, L, lerp(5.5, 7, throat),
                            lift=math.radians(lerp(16, 30, throat) + RNG.uniform(-5, 5)), embed=1.0,
                            th=1.3, point=0.85, taper=0.25, bend=-0.02, cup=0.05, rachis=0.5,
                            notches=RNG.choice((0, 0, 1)), jag=0.1)
    return beak_ob, eye_ob, pupil_ob
# <<< TEIL kopf


# >>> TEIL koerperfedern
def build_koerperfedern(outer_bvh, det):
    """Brust-, Oberschenkel- und Schulterfedern (in den Sammler det)."""
    # Brust
    for ri, el in enumerate(np.linspace(8, -55, 7)):
        n = 11 - abs(ri - 3)
        for k in range(n):
            yaw = lerp(-62, 62, (k + 0.5 * (ri % 2)) / max(n - 1, 1)) + RNG.uniform(-4, 4)
            e, yw = math.radians(el), math.radians(yaw)
            dirv = Vector((math.sin(yw) * math.cos(e), -math.cos(yw) * math.cos(e), math.sin(e)))
            surface_feather(det, outer_bvh, (0, -24, 76), dirv, (0, 0.55, -1.0), RNG.uniform(13, 16), 10,
                            lift=math.radians(9), embed=0.9, th=1.2, point=0.3, taper=0.45, bend=0.10,
                            cup=0.2, rachis=0.3, jag=0.1)
    # Oberschenkel
    for sx in (1, -1):
        for ri, z in enumerate((60, 52, 46)):
            for k in range(9):
                phi = 2 * math.pi * (k + 0.5 * ri) / 9
                dirv = Vector((math.cos(phi), math.sin(phi), -0.15)).normalized()
                surface_feather(det, outer_bvh, (sx * 14, -6, z), dirv, (0, 0.2, -1), RNG.uniform(10, 13), 7,
                                lift=math.radians(14), embed=0.9, th=1.2, point=0.6, taper=0.35,
                                bend=0.04, cup=0.1, jag=0.1)
    # Schulterbereich (Übergang Flügel)
    for sx in (1, -1):
        for ri in range(3):
            for k in range(7):
                yaw = lerp(-30, 40, k / 6) + ri * 4
                el = 40 - ri * 12
                yw, e = math.radians(yaw), math.radians(el)
                dirv = Vector((sx * math.cos(e) * math.cos(yw), math.sin(yw) * math.cos(e) - 0.3, math.sin(e)))
                surface_feather(det, outer_bvh, (sx * 10, -22, 90), dirv, (sx * 0.3, 1, -0.2),
                                RNG.uniform(12, 15), 9, lift=math.radians(8), embed=0.9, th=1.2, point=0.4,
                                taper=0.45, bend=0.1, cup=0.2, jag=0.1)
# <<< TEIL koerperfedern


# >>> TEIL schwanz
def build_schwanz(outer_bvh, c_det, m_body):
    """Schwanzfächer mit Oberschwanzdecken am Bürzel."""
    tail = Acc()
    th_hit = outer_bvh.ray_cast(Vector((0, 300, 84)), Vector((0, -1, 0)))
    troot = th_hit[0] + Vector((0, -10, 0.5))
    nt = 12
    for i in range(nt):
        f = i / (nt - 1) - 0.5
        ang = f * 58
        a = math.radians(ang)
        pitch = math.radians(-22 - 4 * abs(f))
        D = Vector((math.sin(a) * math.cos(pitch), math.cos(a) * math.cos(pitch), math.sin(pitch)))
        L = 58 - 14 * (2 * abs(f)) ** 1.5
        P = troot + Vector((f * 22, 0, -abs(f) * 2.0 + (0.5 - abs(f)) * 2.2))
        V, F = feather(L, 18, th=1.7, taper=0.62, bend=0.03, cup=0.12, notches=1, jag=0.06, barbs=0.35)
        tail.add(place(V, P, D, (0, -math.sin(pitch) * 0.3, 1), roll=f * 0.3), F)
    for i in range(7):
        f = i / 6 - 0.5
        a = math.radians(f * 50)
        pitch = math.radians(-16)
        D = Vector((math.sin(a) * math.cos(pitch), math.cos(a) * math.cos(pitch), math.sin(pitch)))
        P = troot + Vector((f * 16, -8, 4.5 - abs(f) * 2))
        V, F = feather(30, 13, th=1.4, taper=0.5, point=0.2, bend=0.06, cup=0.15, jag=0.08)
        tail.add(place(V, P, D, (0, 0, 1), roll=f * 0.2), F)
    tail_ob = tail.build("Schwanz", c_det, m_body)
    return tail_ob
# <<< TEIL schwanz


# >>> TEIL beine
def build_beine(c_det, m_leg):
    """Läufe, Zehen und Krallen (Sockel-Oberseite liegt beim Aufbau bei SOCKEL_Z + 7.2)."""
    legs = Acc()
    for sx in (1, -1):
        top = Vector((sx * 14.5, -4.0, 50.0))
        foot = Vector((sx * 16.5, -12.0, SOCKEL_Z + 11.0))
        path = [top.lerp(foot, t)[:] for t in np.linspace(0, 1, 30)]
        radii = []
        for t in np.linspace(0, 1, 30):
            r = lerp(4.6, 3.8, t) * (1 + 0.07 * math.cos(2 * math.pi * t * 11) ** 2)
            radii.append((r, r * 1.08))
        V, F = loft(path, radii, K=18, tips=(1.0, 1.0))
        legs.add(V, F)
        # Zehen
        toes = [(-26, 30.0, 2.7), (0, 34.0, 2.9), (26, 27.0, 2.6), (180, 20.0, 2.7)]
        for ang, L, r0 in toes:
            if ang == 180:
                dvec = Vector((sx * 0.15, 1.0, 0.0)).normalized()
            else:
                a = math.radians(ang)  # positiv = nach außen
                dvec = Vector((sx * math.sin(a), -math.cos(a), 0.0))
            pts, rr = [], []
            nseg = 3 if ang != 180 else 2
            for t in np.linspace(0, 1, 26):
                p = foot + dvec * (L * t) + Vector((0, 0, lerp(0.0, -1.6, smoothstep(0, 0.35, t))))
                p.z = max(p.z, SOCKEL_Z + 9.0)
                pts.append(p[:])
                bump = math.cos(math.pi * t * nseg) ** 2
                rr.append((r0 * lerp(1.0, 0.72, t) * (1 + 0.12 * bump), r0 * lerp(1.0, 0.72, t) * (0.9 + 0.1 * bump)))
            V, F = loft(pts, rr, K=14, tips=(0.5, 1.0))
            legs.add(V, F)
            # Kralle
            e = Vector(pts[-1]) + dvec * 1.2
            cl = [e + dvec * (8.5 * t) + Vector((0, 0, 1.0 * math.sin(math.pi * t * 0.6) - 3.6 * t ** 2.2))
                  for t in np.linspace(0, 1, 12)]
            cr = [(lerp(2.0, 0.3, t), lerp(2.2, 0.35, t)) for t in np.linspace(0, 1, 12)]
            V, F = loft([c[:] for c in cl], cr, K=10, tips=(0.4, 0.3))
            legs.add(V, F)
    legs_ob = legs.build("Beine", c_det, m_leg)
    return legs_ob


def build_sockel(c_det, m_body):
    """Runder Sockel."""
    V, F = lathe([(0, 0), (56.5, 0), (58.0, 1.2), (58.5, 3.0), (58.5, 5.0), (57.5, 6.6), (56.0, 7.2), (0, 7.2)], K=160)
    V = V + np.array([0, -6.0, SOCKEL_Z])
    base = make_object("Sockel", V, F, c_det, m_body)
    set_smooth(base, angle=math.radians(30))
    return base
# <<< TEIL beine


# ============================================================================
# Hauptaufbau
# ============================================================================
def build():
    t0 = time.time()
    scene = bpy.context.scene
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"

    for name in ("Cube", "Light", "Camera"):        # Werks-Startszene aufräumen
        ob = bpy.data.objects.get(name)
        if ob is not None and not ob.users_collection[0].name.startswith(COLL_NAME):
            bpy.data.objects.remove(ob, do_unlink=True)

    old = bpy.data.collections.get(COLL_NAME)
    if old:
        for ob in list(old.all_objects):
            remove_object(ob)
        for c in list(old.children_recursive):
            bpy.data.collections.remove(c)
        bpy.data.collections.remove(old)
    root = bpy.data.collections.new(COLL_NAME)
    scene.collection.children.link(root)

    def sub(name):
        c = bpy.data.collections.new(name)
        root.children.link(c)
        return c

    c_body, c_wing, c_det, c_cap, c_help = sub("Koerper"), sub("Fluegel"), sub("Details"), sub("Schraubdeckel"), sub("Hilfsobjekte")
    c_help.hide_render = True

    m_body = material("Kraehe_Schwarz", (0.020, 0.020, 0.022), rough=0.6, spec=0.2)
    m_beak = material("Kraehe_Schnabel", (0.014, 0.014, 0.015), rough=0.32, spec=0.45, coat=0.2)
    m_eye = material("Kraehe_Auge", (0.85, 0.02, 0.01), rough=0.2, spec=0.6, emission=(1.0, 0.03, 0.01), strength=2.5)
    m_pupil = material("Kraehe_Pupille", (0.08, 0.0, 0.0), rough=0.15, spec=0.6)

    # ---------------------------------------------------------------- Körper
    log("Körper (Metaballs -> Voxel-Mesh)")
    body = metaball_body(c_body)
    body.data.materials.append(m_body)
    bvh = bvh_of(body)

    # ------------------------------------------------- Auflage Schraubdeckel
    log("Auflagefläche + Hohlraum")
    O, e1, e2, d = landing_frame(bvh, (0, 18, 74), (0, 0.62, -0.78))
    SPERRZONEN.clear()
    SPERRZONEN.append((O, d, AUFLAGE_RADIUS + 3.0, -3.0, 60.0))
    V, F = tube_mod(0.0, 40.0, 20.0, 128, lambda th, z: AUFLAGE_RADIUS)
    cut = make_object("cut_auflage", frame_to_world(V, O, e1, e2, d), F, c_help, smooth=False)
    boolean(body, cut, "DIFFERENCE")
    remove_object(cut)
    outer_bvh = bvh_of(body)

    # ------------------------------------------------------------- Hohlraum
    cav = bpy.data.objects.new("Hohlraum", body.data.copy())
    c_help.objects.link(cav)
    dm = cav.modifiers.new("inset", "DISPLACE")
    dm.mid_level = 0.0
    dm.strength = -WAND
    rm = cav.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = 1.2
    apply_modifiers(cav)
    V, F = ellipsoid((0, 8, 80), (40, 50, 29), K=64, rings=32)
    lim = make_object("lim", V, F, c_help, smooth=False)
    boolean(cav, lim, "INTERSECT")
    remove_object(lim)
    # 45°-Dach über dem Hohlraum: druckt ohne Stützen im Inneren, First unter dem Schlitz
    top = outer_bvh.ray_cast(Vector((0, 6, 300)), Vector((0, 0, -1)))[0]
    V, F = roof_solid(Vector((0, top.y, top.z - WAND - 0.3)), SCHLITZ[0] / 2 + 2.0, slope=DACH_STEIGUNG)
    lim = make_object("dach", V, F, c_help, smooth=False)
    boolean(cav, lim, "INTERSECT")
    remove_object(lim)
    cav_bvh = bvh_of(cav)
    log("  Innenvolumen: %.0f ml" % (cav_volume(cav) / 1000.0))

    boolean(body, cav, "DIFFERENCE")

    # Loch + Innengewinde-Kragen
    log("Innengewinde")
    rhole = R_MIN + GEWINDE_SPIEL + GEWINDE_TIEFE + 0.9
    V, F = tube_mod(-WAND - 4.0, 5.0, 10.0, 160, lambda th, z: rhole)
    cut = make_object("cut_loch", frame_to_world(V, O, e1, e2, d), F, c_help, smooth=False)
    boolean(body, cut, "DIFFERENCE")
    remove_object(cut)
    V, F = tube_mod(-KRAGEN_LAENGE, 0.0, GEWINDE_STEIGUNG / 18, 180,
                    lambda th, z: KRAGEN_RADIUS - np.clip(1.5 - (z + KRAGEN_LAENGE), 0, 1.5), r_innen)
    collar = make_object("Kragen", frame_to_world(V, O, e1, e2, d), F, c_help, smooth=False)
    boolean(body, collar, "UNION")
    remove_object(collar)

    # Münzschlitz
    log("Münzschlitz")
    hit = outer_bvh.ray_cast(Vector((0, 6, 300)), Vector((0, 0, -1)))
    sn = hit[1].normalized()
    s1 = Vector((1, 0, 0))
    s2 = sn.cross(s1).normalized()
    s1 = s2.cross(sn).normalized()
    for op, (V, F) in schlitz_geometrie():
        cut = make_object("schlitz_teil", frame_to_world(V, hit[0], s1, s2, sn), F, c_help, smooth=False)
        boolean(body, cut, op)
        remove_object(cut)
    set_smooth(body, angle=math.radians(40))
    SPERRZONEN.append((hit[0], sn, SCHLITZ[0] / 2 + 6.0, -3.0, 300.0))

    # ---------------------------------------------------------- Schraubdeckel
    log("Schraubdeckel")
    cap_parts = []
    # Gewindestopfen (Becher, innen hohl – wird von der Scheibe geschlossen)
    cap_parts.append(tube_mod(-STOPFEN_LAENGE, 0.8, GEWINDE_STEIGUNG / 18, 180, r_aussen, lambda th, z: STOPFEN_INNEN))
    rf = AUFLAGE_RADIUS - 0.7

    def r_flansch(th, z):
        knurl = 0.55 * (0.5 + 0.5 * np.cos(40 * th)) ** 2
        ch = np.clip(0.7 - (3.4 - z), 0, 0.7) + np.clip(0.4 - (z - 0.2), 0, 0.4)
        return rf - knurl - ch

    cap_parts.append(tube_mod(0.2, 3.4, 0.2, 240, r_flansch))
    cap_parts.append(prism(stadium(2 * rf - 12, 8.0, 12), 3.0, 10.0, chamfer=1.2,
                           inset_poly=stadium(2 * rf - 14.4, 5.6, 12)))
    # Pfeil "auf" (gegen Uhrzeigersinn) als flache Erhebung
    for sgn in (1, -1):
        arc = []
        for a in np.linspace(math.radians(25), math.radians(70), 10):
            arc.append((sgn * 17.5 * math.cos(a), sgn * 17.5 * math.sin(a), 3.2))
        cap_parts.append(loft(arc, [1.0] * len(arc), K=10))
        a = math.radians(78)
        tip = (sgn * 17.5 * math.cos(a), sgn * 17.5 * math.sin(a), 3.2)
        base_a = math.radians(66)
        bc = Vector((sgn * 17.5 * math.cos(base_a), sgn * 17.5 * math.sin(base_a), 3.2))
        cap_parts.append(loft([bc[:], tip], [2.4, 0.2], K=10, tips=(0, 0)))
    cap = make_object("Schraubdeckel", *cap_parts[0], c_cap, m_body, smooth=False)
    for V, F in cap_parts[1:]:
        part = make_object("deckel_teil", V, F, c_help, smooth=False)
        boolean(cap, part, "UNION")
        remove_object(part)
    cap_frame = Matrix(((e1.x, e2.x, d.x, O.x), (e1.y, e2.y, d.y, O.y), (e1.z, e2.z, d.z, O.z), (0, 0, 0, 1)))
    cap.data.transform(cap_frame)
    # Druckausrichtung (Becherrand auf dem Druckbett) für den STL-Export merken
    druck = Matrix.Translation((0, 0, STOPFEN_LAENGE)) @ cap_frame.inverted() @ Matrix.Translation((0, 0, -SOCKEL_Z)).inverted()
    cap["druck_matrix"] = [v for row in druck for v in row]
    set_smooth(cap, angle=math.radians(35))

    # ----------------------------------------------------------------- Flügel
    log("Flügel")
    shoulderL = schulter_punkt(outer_bvh)
    wl = build_wing(shoulderL, False, c_wing, m_body)
    wr = build_wing(shoulderL, True, c_wing, m_body)
    for w in (wl, wr):            # Flügel enden exakt auf der Körperoberfläche (Klebefläche)
        boolean(w, body, "DIFFERENCE")

    # ---------------------------------------------------------------- Details
    det = Acc()
    log("Kopf, Schnabel, Augen, Halskrause")
    beak_ob, eye_ob, pupil_ob = build_kopf(outer_bvh, det, c_det, m_beak, m_eye, m_pupil)
    log("Brust-, Schenkel- und Schulterfedern")
    build_koerperfedern(outer_bvh, det)
    log("Schwanz")
    tail_ob = build_schwanz(outer_bvh, c_det, m_body)
    log("Beine, Füße, Sockel")
    legs_ob = build_beine(c_det, m_beak)
    base = build_sockel(c_det, m_body)

    det_ob = det.build("Federn_Details", c_det, m_body)

    # ------------------------------------------------------- Prüfungen
    log("Prüfe, dass nichts in den Hohlraum ragt")
    cav_co = mesh_arrays(cav)
    lo, hi = cav_co.min(0), cav_co.max(0)
    for ob in (wl, wr, det_ob, tail_ob, legs_ob, beak_ob, eye_ob, pupil_ob):
        co = mesh_arrays(ob)
        co = co[np.all((co > lo) & (co < hi), axis=1)]
        inside = sum(1 for v in co if point_inside(cav_bvh, v))
        if inside:
            log("  %s ragt in den Hohlraum (%d Punkte) -> wird beschnitten" % (ob.name, inside))
            boolean(ob, cav, "DIFFERENCE")
    remove_object(cav)
    for ob in root.all_objects:
        if ob.type == "MESH":
            ob.data.transform(Matrix.Translation((0, 0, -SOCKEL_Z)))

    for ob in list(c_help.objects):
        remove_object(ob)
    bpy.data.collections.remove(c_help)
    log("fertig in %.1f s, Boolean-Solver: %s" % (time.time() - t0, BOOL_SOLVER))
    return root


# ============================================================================
# Szene (Kamera, Licht) und Export
# ============================================================================
def setup_scene():
    scene = bpy.context.scene
    for name in ("Kamera_Kraehe", "Sonne_Key", "Sonne_Fill", "Boden"):
        ob = bpy.data.objects.get(name)
        if ob:
            remove_object(ob)
    coll = bpy.data.collections.get("Kraehe_Szene")
    if coll is None:
        coll = bpy.data.collections.new("Kraehe_Szene")
        scene.collection.children.link(coll)
    cam = bpy.data.cameras.new("Kamera_Kraehe")
    cam.lens = 55
    cam.clip_start = 1
    cam.clip_end = 10000
    co = bpy.data.objects.new("Kamera_Kraehe", cam)
    coll.objects.link(co)
    co.location = (-330, -470, 360)
    target = Vector((0, -10, 80))
    co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = co

    def sun(name, rot, energy, angle):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        ld.angle = math.radians(angle)
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = [math.radians(a) for a in rot]
        coll.objects.link(lo)

    sun("Sonne_Key", (40, 10, -35), 3.8, 14)
    sun("Sonne_Fill", (60, -10, 150), 0.2, 30)
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (1.0, 1.0, 1.0, 1)
    bg.inputs[1].default_value = 0.5
    me = bpy.data.meshes.new("Boden")
    s = 3000
    me.from_pydata([(-s, -s, -0.05), (s, -s, -0.05), (s, s, -0.05), (-s, s, -0.05)], [], [(0, 1, 2, 3)])
    floor = bpy.data.objects.new("Boden", me)
    coll.objects.link(floor)
    mf = material("Boden_weiss", (0.58, 0.58, 0.58), rough=0.9, spec=0.1)
    floor.data.materials.append(mf)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.view_settings.view_transform = "Standard"   # kontrastreich wie die Vorlage


def write_stl(path, objects):
    dg = bpy.context.evaluated_depsgraph_get()
    tris = []
    for ob in objects:
        M = np.array(ob.matrix_world)
        if "druck_matrix" in ob:
            M = np.array(ob["druck_matrix"]).reshape(4, 4) @ M
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        co = co @ M[:3, :3].T + M[:3, 3]
        idx = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", idx)
        tris.append(co[idx.reshape(-1, 3)])
        ev.to_mesh_clear()
    T = np.concatenate(tris).astype(np.float32)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(T), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = T
    with open(path, "wb") as f:
        f.write(b"Kraehe-Spardose".ljust(80, b" "))
        f.write(np.uint32(len(T)).tobytes())
        f.write(rec.tobytes())
    log("STL", path, len(T), "Dreiecke")


def export_stls(folder):
    os.makedirs(folder, exist_ok=True)
    o = bpy.data.objects
    groups = {
        "01_Koerper_mit_Sockel.stl": ["Koerper", "Federn_Details", "Schwanz", "Schnabel", "Beine", "Sockel", "Pupillen"],
        "02_Fluegel_links.stl": ["Fluegel_links"],
        "03_Fluegel_rechts.stl": ["Fluegel_rechts"],
        "04_Schraubdeckel.stl": ["Schraubdeckel"],
        "05_Augen_rot.stl": ["Augen"],
    }
    for fn, names in groups.items():
        write_stl(os.path.join(folder, fn), [o[n] for n in names if n in o])


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    build()
    setup_scene()
    if not bpy.app.background:
        # Ansicht in der Oberfläche auf das Modell (Millimeter-Maßstab) einstellen
        for area in bpy.context.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.clip_start, space.clip_end = 0.5, 20000.0
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is not None:
                with bpy.context.temp_override(area=area, region=region):
                    bpy.ops.view3d.view_all(center=False)
    if "--stl" in argv:
        export_stls(argv[argv.index("--stl") + 1])
    if "--blend" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(argv[argv.index("--blend") + 1]), compress=True)


if __name__ == "__main__":
    main()
