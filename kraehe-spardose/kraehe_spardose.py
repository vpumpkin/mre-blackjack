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

SOCKEL_Z = 2.0               # Höhe der Sockel-Unterseite beim Aufbau (wird am Ende auf 0 gesetzt)

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
            root_w=0.2, taper=0.55, rachis=0.45, nW=4, rng=RNG, jag=0.0, barbs=0.0, barb_gap=2.8,
            soft=False, rachis_w=0.16, notch_t=None, notch_dp=None, notch_side=None, emarg=0.0, emarg_t=0.55):
    """Einzelne Feder lokal: x = Länge, y = Breite, z = oben. Geschlossener Körper.
    barbs > 0 graviert schräge Federäste (Rillentiefe in mm) in die Oberseite.
    Optionale Zusätze (ohne sie bleibt das Ergebnis exakt wie bisher):
      soft=True   gewölbter, zum Rand hin weich abgeschrägter Querschnitt (Rand ~30 % der Dicke),
                  Spitze auch in der Dicke verrundet -> saubere, "gedruckte" Federn statt Pappkarten
      rachis_w    Breite des Schafts (Anteil der halben Federbreite, kleiner = schärfere Schaftlinie)
      notch_t / notch_dp / notch_side   Kerbe an fester Stelle / Tiefe / Seite (+1 = +y, -1 = -y)
                  statt zufällig
      emarg       Verengung beider Fahnen ab emarg_t (Anteil, z. B. 0.35) – die schlanken "Finger"
                  der äußeren Handschwingen von Raben und Krähen"""
    nL = max(10, int(L / 2.0))
    if barbs > 0:
        nL = max(nL, int(L / 0.65))
        nW = max(nW, 6)
    if soft:
        nL = max(nL, int(L / 1.5))
        nW = max(nW, 6)
    t = np.linspace(0.0, 1.0, nL + 1)
    s = np.linspace(-1.0, 1.0, 2 * nW + 1)
    base = root_w + (1 - root_w) * smoothstep(0.0, 0.32, t)
    x = np.clip((t - taper) / (1 - taper), 0, 1)
    tipf = (1 - point) * np.sqrt(np.clip(1 - x * x, 0, 1)) + point * (1 - x) ** 0.9
    base = base * np.maximum(tipf, 0.07)
    if emarg > 0:
        base = base * (1 - emarg * smoothstep(emarg_t - 0.06, emarg_t + 0.1, t))
    wpos = base.copy()
    wneg = base * asym
    for _ in range(notches):
        tn = rng.uniform(0.38, 0.9) if notch_t is None else notch_t
        dp = rng.uniform(0.25, 0.5) if notch_dp is None else notch_dp
        prof = dp * np.clip(1 - np.abs(t - tn) / 0.055, 0, 1)
        if (rng.random() < 0.5) if notch_side is None else (notch_side > 0):
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
    if soft:
        # gewölbt: dick in der Mitte, Rand weich abgeschrägt, Spitze flach auslaufend
        spitze = np.sqrt(np.clip(tipf, 0.12, 1.0))[:, None]
        h = th * 0.5 * (0.3 + 0.7 * np.sqrt(np.clip(1 - S * S, 0, 1))) * (1 - 0.3 * T) * spitze
        r = rachis * th * np.exp(-(S / rachis_w) ** 2) * (1 - 0.7 * T) * spitze
    else:
        h = th * 0.5 * (0.62 + 0.38 * (1 - np.abs(S))) * (1 - 0.3 * T)
        r = rachis * th * np.exp(-(S / rachis_w) ** 2) * (1 - 0.7 * T)
    Zt = camber + h + r
    if barbs > 0:
        A = np.abs(S)
        phase = (X - 0.9 * np.abs(Y)) / barb_gap
        mask = smoothstep(0.14, 0.3, A) * (1 - smoothstep(0.82, 1.0, A)) * smoothstep(0.08, 0.2, T)
        Zt = Zt - barbs * mask * (0.5 + 0.5 * np.cos(2 * np.pi * phase)) ** 3
    if soft:
        Zb = camber - 0.7 * h - 0.2 * r
    else:
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
KOERPER_MB_SCHWELLE = 0.6          # Metaball-Schwellwert (wie in metaball_body)
HOSEN_MITTE = (15.5, -7.0, 54.0)   # Mitte der Oberschenkel-"Hosen" (x wird gespiegelt)


def koerper_ell_weich(ell, c, semi, rot=None, stiff=2.0):
    """Metaball mit eigener Steifigkeit. Die Halbachsen werden so umgerechnet, dass die freie
    Oberfläche auch bei weicher Steifigkeit bei 'semi' liegt (weiche Bälle verschmelzen sanfter)."""
    k = math.sqrt(1.0 - (KOERPER_MB_SCHWELLE / stiff) ** (1.0 / 3.0))
    f = MB_K / k
    ell(c, tuple(s * f for s in semi), rot, stiff=stiff)


def koerper_metaballs(ell, q):
    """Rumpf, Brust, Bauch, Bürzel, Oberschenkel, Schultern. ell(mitte, halbachsen, rotation).
    Ein einziges großes, glattes Ei: höchster Punkt am Münzschlitz (y ≈ 6), der Rücken fällt
    gleichmäßig zum Kopf und zum Schwanz ab, die Unterseite ist ein sauberer Bogen ohne Hängebauch.
    Hinweis: Den Scheitel nicht weiter anheben – sonst geraten die inneren Flügelfedern
    (Schirmfedern über dem Rücken) unter die Hohlraumdecke ("ragt in den Hohlraum")."""
    ell((0, 6, 81), (36, 50, 31), q(x=-1))           # Rumpf (Scheitel über dem Schlitz)
    ell((0, -28, 76), (31, 27, 27))                  # Brust
    ell((0, 2, 69), (27, 32, 14))                    # Bauch (flach, kein Hängebauch)
    koerper_ell_weich(ell, (0, 42, 85), (20, 26, 13), q(x=4), stiff=1.4)   # Bürzel, weich eingeschmolzen
    hx, hy, hz = HOSEN_MITTE
    for sx in (-1, 1):
        ell((sx * hx, hy, hz), (11, 12, 13.5))       # Oberschenkel ("Hosen"), hängen etwas unter dem Bauch
        koerper_ell_weich(ell, (sx * 25, -16, 93), (8.5, 11, 6.5), q(y=sx * 20), stiff=1.2)  # Schulter
# <<< TEIL koerperform


# >>> TEIL kopfform
def kopf_metaballs(ell, q):
    """Hals, Kopf (hohe, runde Schädelkuppel), Wangen/Kinn, Stirn, Brauenwülste."""
    ell((0, -50, 85), (22, 20, 24))                  # Hals – Anschluss an den Rumpf (bleibt)
    ell((0, -72, 93), (21.5, 24.5, 21), q(x=6))      # Kopf: große Kuppel
    ell((0, -84, 85), (15, 14.5, 12.5))              # Wangen / Kinn
    ell((0, -88, 97), (10.5, 11, 8.5), q(x=16))      # Stirn -> Schnabelansatz
    for sx in (-1, 1):                               # Brauenwulst: schwer, schräg zum Schnabel
        ell((sx * 11.6, -89.0, 100.0), (2.4, 8.0, 2.2), q(x=22, z=-sx * 18), stiff=1.4)
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

# Vorderkante (u außen, v hinten, ungeskaliert): Schulter, Ellbogen, Handgelenk, Handspitze.
# Der Arm schwingt in sanftem Bogen nach vorn (wie im Referenzbild), die Hand zeigt nach außen.
BONE = [(-6.0, 3.0), (40.0, -6.0), (88.0, -13.0), (122.0, -12.0)]

# Haltung je Seite wie im Referenzbild: links (+X, im Referenzbild hinten) hoch erhoben, die Hand biegt
# sich in einem durchgehenden Bogen weiter nach oben; rechts (-X, vorne) weit nach vorn-außen gespreizt,
# Oberseite zum Betrachter geneigt, Handschwingen hängen leicht.
FLUEGEL_POSE = {False: dict(dihedral=8.0, sweep=-2.0, twist=26.0, hand_lift=30.0),
                True: dict(dihedral=-8.0, sweep=-20.0, twist=20.0, hand_lift=-14.0)}
HAND_BIEGUNG = (66.0, 114.0)   # u-Bereich, über den sich die Hand gleichmäßig biegt (kein Knick am Handgelenk)
VERWINDUNG = (0.3, 50.0)       # Anstellwinkel wächst von 30 % an der Schulter auf 100 % bei u = 50: innen liegt
                               # der Flügel flach am Rücken an, außen zeigt er seine Oberseite

SCHINDEL = math.radians(7.0)   # Querneigung jeder Schwungfeder (Außenseite höher) -> saubere Dachziegel-Stufen
N_STUFE = 0.35                 # Höhenversatz benachbarter Schwungfedern (innere liegen oben, wie beim Vogel)
N_OBEN = 5.5                   # Höhe der innersten Schirmfeder
HOHLRAUM_ABSTAND = 0.8         # Mindestabstand aller Flügelteile zum Hohlraum (mm)
ARM_START = -10.0              # Vorderkante beginnt im Rumpf (wird bei Bedarf nach außen verkürzt)
DREHPUNKT_N = 7.0              # Flügel drehen um einen Punkt in Höhe der Vorderkante (nicht um die Unterseite),
                               # damit der dicke Schulteransatz beim Absenken nicht in den Rumpf schwenkt


_BONE_KURVE = []


def bone_at(u):
    """Vorderkante bei u – weiche Kurve (Catmull-Rom) durch die BONE-Punkte, ohne Knicke."""
    if not _BONE_KURVE:
        pts, _ = resample(BONE, [0.0] * len(BONE), 90)
        _BONE_KURVE.extend([np.array([p[0] for p in pts]), np.array([p[1] for p in pts])])
    return float(np.interp(u, _BONE_KURVE[0], _BONE_KURVE[1]))


def schwung_index(u):
    """Fortlaufende Nummer der Schwungfeder bei u (0 = innerste Schirmfeder ... 23 = äußerste Handschwinge)."""
    return float(np.interp(u, [-2.0, 2.5, 7.0, 11.0, 86.0, 89.0, 121.0], [0.0, 1.0, 2.0, 3.0, 13.0, 14.0, 23.0]))


def n_basis(u):
    """Höhe der Schwungfeder-Lage bei u; die Deckfeder-Reihen liegen darauf."""
    return N_OBEN - N_STUFE * schwung_index(u)


def hand_angle(f):
    """Richtung der Handschwingen, f = 0 (innen) ... 1 (außen): innen geschlossen, außen gefingert."""
    return lerp(62.0, 16.0, min(max(f, 0.0), 1.0) ** 1.8)


def flight_angle(u):
    """Richtung der Federn (Grad, 0 = nach außen, 90 = nach hinten)."""
    if u <= 88:
        return lerp(88.0, 74.0, max(u, 0.0) / 88.0)
    return hand_angle((u - 89.0) / 32.0)


def _profil_vorderkante(a, t):
    """Querschnitt der Vorderkante (x = nach hinten, y = oben): runde Nase, flachere Unterseite;
    hinten läuft sie dünn und leicht angehoben aus und legt sich wie eine Haut über die Wurzeln der
    kleinen Decken (keine Stufe zwischen Wulst und Federn)."""
    c, s = math.cos(a), math.sin(a)
    k = 1.0 if s >= 0 else 0.75
    if c <= 0:
        return c, s * k
    return c * 0.9, s * k * (1.0 - 0.3 * c) + 0.6 * c * c


def vorderkante(u0):
    """Vorderkante (Patagium) ab u0: kräftige, runde Nase vorn, nach hinten flach über den kleinen
    Decken auslaufend; zum Rumpf hin deutlich dicker (weicher, polsterartiger Übergang in die Schulter)."""
    path, radii = [], []
    n_st = max(20, int((122.0 - u0) / 2.8))
    for u in np.linspace(u0, 122.0, n_st):
        senke = 0.5 * max(8.0 - u, 0.0)         # Schulterende taucht schräg in die Flanke ein
        path.append((u * WS, (bone_at(max(u, -6.0)) + 1.0) * WS, n_basis(max(u, -2.0)) + 3.0 - senke))
        rx = float(np.interp(u, [-10, 0, 20, 40, 88, 122], [11.0, 9.0, 7.0, 6.0, 4.5, 2.4]))
        ry = float(np.interp(u, [-10, 0, 20, 40, 88, 122], [10.0, 8.5, 6.4, 5.2, 3.8, 2.0]))
        radii.append((rx, ry))
    return loft(path, radii, K=28, shape=_profil_vorderkante, tips=(2.0, 1.5))


def wing_geometry():
    """Linker Flügel in lokalen Koordinaten (u außen, v hinten, n oben). Liefert Liste (V, F, x) –
    x = u-Position (mm) der Federwurzel, an der die Feder starr mitgebogen wird, oder "arm" für die
    Vorderkante (wird punktweise gebogen)."""
    parts = []
    rng = random.Random(SEED + 101)   # eigener Zufall: beide Flügel gleich, globaler RNG bleibt unberührt

    def fe(u, d0, n, ang, L, W, vofs=2.5, pitch=-0.035, roll=SCHINDEL, **kw):
        """Feder bei u; d0 = Abstand der Wurzel entlang der Federachse (Deckfedern liegen weiter hinten)."""
        a = math.radians(ang)
        D = Vector((math.cos(a), math.sin(a), pitch))
        P = Vector(((u + d0 * math.cos(a)) * WS, (bone_at(u) + vofs + d0 * math.sin(a)) * WS, n))
        V, F = feather(L * WS, W * WS, soft=True, rng=rng, **kw)
        parts.append((place(V, P, D, (0, 0, 1), roll=-roll), F, P.x))

    schwung = dict(th=2.0, bend=0.035, cup=0.05, rachis=0.5, rachis_w=0.1, nW=7)
    # Handschwingen (10): breite Lanzettfedern mit runder Spitze; die äußeren drei bilden die Spitze,
    # die äußeren fünf spreizen sich zu Fingern, die äußeren vier haben eine weiche Kerbe
    plens = [81, 84, 87, 91, 95, 99, 102, 104, 101, 94]
    for i in range(10):
        f = i / 9
        u = lerp(89.0, 121.0, f)
        fe(u, 0.0, n_basis(u), hand_angle(f) + rng.uniform(-0.5, 0.5), plens[i], lerp(25.0, 20.0, f),
           point=0.15, taper=0.6, asym=lerp(0.85, 0.68, f),
           emarg=0.0 if i < 5 else lerp(0.2, 0.38, (i - 5) / 4), emarg_t=0.52,
           notches=1 if i >= 6 else 0, notch_t=0.78, notch_dp=0.2, notch_side=1, **schwung)
    # Armschwingen (11): lang und breit -> tiefe Flügelfläche, durchgehende, sanft gewellte Hinterkante
    for i in range(11):
        f = i / 10
        u = lerp(11.0, 86.0, f)
        fe(u, 0.0, n_basis(u), flight_angle(u) + rng.uniform(-0.5, 0.5), lerp(90, 86, f), 21,
           point=0.0, taper=0.75, asym=0.8, **schwung)
    # Schirmfedern (3): liegen hinter der Schulter über der Flanke
    for i in range(3):
        u = -2.0 + 4.5 * i
        fe(u, 0.0, n_basis(u), 92.0 - 2.0 * i, 86 + 2 * i, 21, vofs=4.0,
           point=0.0, taper=0.75, asym=0.85, **schwung)

    # Deckfedern: drei klar getrennte Reihen langer, runder Federn; jede Reihe liegt höher und
    # ihre Spitzen legen sich auf die Reihe darunter (deutliche Schattenstufe)
    decke = dict(th=2.2, bend=0.045, cup=0.06, rachis=0.4, rachis_w=0.12, nW=6, asym=0.9,
                 pitch=-0.03, roll=0.0)
    for i in range(14):                                     # große Decken
        f = i / 13
        u = lerp(-1.0, 119.0, f)
        fe(u, 19.0, n_basis(u) + 2.2, flight_angle(u) + rng.uniform(-1, 1), lerp(38, 34, f), 12.5,
           point=0.0, taper=0.7, **decke)
    for i in range(13):                                     # mittlere Decken
        f = i / 12
        u = lerp(1.0, 108.0, f)
        fe(u, 10.0, n_basis(u) + 4.0, flight_angle(u) - 3 + rng.uniform(-1, 1), lerp(32, 27, f), 11.5,
           point=0.0, taper=0.68, **decke)
    for i in range(12):                                     # kleine Decken, Wurzeln versetzt unter der Vorderkante
        f = i / 11
        u = lerp(2.0, 96.0, f)
        fe(u, 2.5 + (1.2 if i % 2 else -1.2), n_basis(u) + 5.8, flight_angle(u) - 6 + rng.uniform(-1, 1),
           lerp(24, 20, f), 10.5, point=0.0, taper=0.66, **decke)

    V, F = vorderkante(ARM_START)
    parts.append((V, F, "arm"))
    return parts


def wing_transform(dihedral=8.0, sweep=-2.0, twist=26.0, hand_lift=30.0):
    """Haltung des Flügels: liefert (M, hand, verwinde). M dreht den ganzen Flügel (Pfeilung, V-Stellung);
    hand(V, x) biegt Punkte V, die an der u-Position x (mm, je Punkt oder je Feder) hängen, gleichmäßig um
    hand_lift Grad nach oben; verwinde(V, x) stellt sie um die Spannweitenachse an (zur Spitze hin zunehmend)."""
    def rx(a):
        return Matrix.Rotation(math.radians(a), 3, "X")

    def ry(a):
        return Matrix.Rotation(math.radians(a), 3, "Y")

    def rz(a):
        return Matrix.Rotation(math.radians(a), 3, "Z")

    M = rz(sweep) @ ry(-dihedral)
    x0, x1 = HAND_BIEGUNG[0] * WS, HAND_BIEGUNG[1] * WS
    k = math.radians(hand_lift) / (x1 - x0)
    zc = n_basis(88.0) + 4.0                    # Biegeachse in Höhe der Vorderkante

    def hand(V, x):
        if abs(k) < 1e-9:
            return V
        x = np.broadcast_to(np.asarray(x, float), (len(V),))
        s = np.clip(x - x0, 0.0, x1 - x0)       # gebogenes Stück
        e = np.maximum(x - x1, 0.0)             # gerade Verlängerung dahinter
        phi = k * s
        c, sn = np.cos(phi), np.sin(phi)
        ax = x - s - e + sn / k + e * c         # Achsenpunkt nach dem Biegen
        az = (1.0 - c) / k + e * sn
        rx_ = V[:, 0] - x
        rz_ = V[:, 2] - zc
        out = V.copy()
        out[:, 0] = ax + rx_ * c - rz_ * sn
        out[:, 2] = zc + az + rx_ * sn + rz_ * c
        return out

    def verwinde(V, x):
        x = np.broadcast_to(np.asarray(x, float), (len(V),))
        a = math.radians(twist) * (VERWINDUNG[0] + (1 - VERWINDUNG[0]) * smoothstep(0.0, VERWINDUNG[1] * WS, x))
        c, sn = np.cos(a), np.sin(a)
        y, z = V[:, 1], V[:, 2] - DREHPUNKT_N
        out = V.copy()
        out[:, 1] = y * c - z * sn
        out[:, 2] = DREHPUNKT_N + y * sn + z * c
        return out

    return np.array(M), hand, verwinde


def _hohlraum_bvh():
    """BVH des Hohlraums (Hilfsobjekt aus build()), um Flügelteile davon fernzuhalten."""
    cav = bpy.data.objects.get("Hohlraum")
    if cav is None:
        return None
    co = mesh_arrays(cav)
    return BVHTree.FromPolygons(co.tolist(), [tuple(p.vertices) for p in cav.data.polygons]), co.min(0), co.max(0)


def _ragt_in_hohlraum(cav, V):
    bvh, lo, hi = cav
    m = HOHLRAUM_ABSTAND + 0.5
    V = V[np.all((V > lo - m) & (V < hi + m), axis=1)]
    for v in V:
        p = Vector(v)
        loc, nrm, _, dist = bvh.find_nearest(p)
        # vorzeichenbehafteter Abstand (an Kanten des Hohlraums ist die Flächennormale allein unzuverlässig)
        if loc is not None and (dist < HOHLRAUM_ABSTAND or (p - loc).dot(nrm) < 0.0):
            return True
    return False


def build_wing(shoulder, mirror, coll, mat):
    M, hand, verwinde = wing_transform(**FLUEGEL_POSE[mirror])
    piv = np.array([0.0, 0.0, DREHPUNKT_N])
    sx = np.array([-1.0 if mirror else 1.0, 1.0, 1.0])
    cav = _hohlraum_bvh()
    acc = Acc()
    skipped = deep = 0
    aussen = M[:, 0]                       # lokale u-Achse (nach außen) in Weltkoordinaten

    def setze(V, x):
        V = np.asarray(V)
        xr = V[:, 0] if x == "arm" else x
        V = verwinde(hand(V, xr), xr)
        return (V - piv) @ M.T + piv + np.array(shoulder[:])

    for V, F, x in wing_geometry():
        V = setze(V, x)
        if x != "arm" and in_sperrzone(V * sx):
            skipped += 1
            continue
        if cav is not None and x == "arm":
            # Schulterende der Vorderkante so weit kürzen, dass es dem Hohlraum fernbleibt
            u0 = ARM_START
            while _ragt_in_hohlraum(cav, V * sx) and u0 < 4.0:
                u0 += 1.5
                V0, F = vorderkante(u0)
                V = setze(V0, x)
            if u0 > ARM_START:
                log("  Vorderkante beginnt bei u=%.1f (Hohlraum)" % u0)
        elif cav is not None:
            # Feder, die zu tief in die Flanke taucht, ein Stück nach außen rücken (max. 3 mm), sonst weglassen
            for k in range(3):
                if not _ragt_in_hohlraum(cav, V * sx):
                    break
                V = V + aussen * 1.5
            else:
                if _ragt_in_hohlraum(cav, V * sx):
                    deep += 1
                    continue
        if mirror:
            acc.add_mirrored(V, F)
        else:
            acc.add(V, F)
    if skipped:
        log("  %d Federn wegen Münzschlitz/Deckel ausgelassen" % skipped)
    if deep:
        log("  %d Federn zu nah am Hohlraum ausgelassen" % deep)
    name = "Fluegel_rechts" if mirror else "Fluegel_links"
    return acc.build(name, coll, mat)


def schulter_punkt(outer_bvh):
    """Ansatzpunkt des linken Flügels auf der Körperoberfläche (rechts wird gespiegelt)."""
    sdir = Vector((1, -0.05, 0.12)).normalized()
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
        # klares Rechteck mit senkrechten Wänden und scharfer Kante (kein Rahmen, keine Lippe)
        ("DIFFERENCE", prism(schlitz_rechteck(*SCHLITZ, r=0.6), -16.0, 8.0)),
    ]


def schlitz_rechteck(length, width, r=0.6, n=3):
    """Rechteck length x width (gegen den Uhrzeigersinn) mit kleinem Eckradius r."""
    hx, hy = length / 2 - r, width / 2 - r
    pts = []
    for cx, cy, a0 in ((hx, -hy, -90), (hx, hy, 0), (-hx, hy, 90), (-hx, -hy, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
# <<< TEIL schlitz


# >>> TEIL kopf
SCHNABEL_BASIS = (0.0, -86.0, 91.5)   # Drehpunkt des Schnabels (steckt im Gesicht)
SCHNABEL_NEIGUNG = 12.0               # Schnabelachse zeigt so viele Grad nach unten
SCHNABEL_OFFEN = 12.0                 # Öffnungswinkel des Unterschnabels
MUNDWINKEL = (3.0, -7.8)              # Drehpunkt des Unterschnabels (s, h)

# Oberschnabel (s entlang der Achse, Oberkante, Unterkante, halbe Breite) – massig, Haken nur vorne
OBERSCHNABEL = [(0, 13.6, -8.6, 12.8), (8.5, 13.1, -8.1, 12.3), (17, 11.8, -7.4, 10.7), (25, 9.6, -6.5, 8.6),
                (32.5, 6.7, -5.7, 6.5), (38.5, 3.4, -5.1, 4.6), (44, -0.2, -4.9, 3.0), (47.8, -4.0, -6.1, 1.9),
                (50.2, -7.6, -8.2, 1.0)]
# Unterschnabel geschlossen (s, Schneide, Unterkante, halbe Breite)
UNTERSCHNABEL = [(0, -7.9, -19.5, 11.6), (8.5, -7.7, -18.5, 11.1), (17, -7.1, -16.4, 9.4), (25, -6.5, -14.2, 7.5),
                 (32.5, -6.1, -12.1, 5.5), (38.5, -6.1, -10.5, 3.5), (42.5, -6.5, -9.4, 1.8),
                 (44.5, -6.9, -8.9, 0.9)]


def schnabel_rahmen():
    """Achsen des Schnabels: f nach vorne (geneigt), h nach oben, x seitlich."""
    t = math.radians(SCHNABEL_NEIGUNG)
    f = Vector((0.0, -math.cos(t), -math.sin(t)))
    h = Vector((0.0, -math.sin(t), math.cos(t)))
    return Vector(SCHNABEL_BASIS), f, h


def schnabel_punkt(s, hgt):
    B, f, h = schnabel_rahmen()
    return B + f * s + h * hgt


def unterkiefer(s, hgt):
    """Punkt am geöffneten Unterschnabel: Drehung um den Mundwinkel."""
    a = math.radians(SCHNABEL_OFFEN)
    s0, h0 = MUNDWINKEL
    ds, dh = s - s0, hgt - h0
    return s0 + ds * math.cos(a) + dh * math.sin(a), h0 - ds * math.sin(a) + dh * math.cos(a)


def build_schnabel(c_det, m_beak):
    beak = Acc()
    B, f, h = schnabel_rahmen()

    # Querschnitte: gewölbter First oben, unten scharfe Schneiden mit hohlem Gaumen
    def upper_shape(a, t):
        c, s = math.cos(a), math.sin(a)
        if s >= 0:
            return c * (1 - 0.3 * s ** 4), s ** 0.8
        return c, -0.3 * min(1.0, -4 * s) * c ** 4 + 0.08 * (1 - c * c)

    path, rad = [], []
    for s, hi, lo, w in OBERSCHNABEL:
        path.append(schnabel_punkt(s, lo + (hi - lo) / 1.3 * 0.3)[:])
        rad.append((w, (hi - lo) / 1.3))
    path, rad = resample(path, rad, 90)
    V, F = loft(path, rad, K=56, shape=upper_shape, tips=(0, 1.2), up=h[:])
    # Nasenloch: kleine ovale Delle seitlich am Oberschnabel
    for sx in (1, -1):
        c = schnabel_punkt(15.0, 3.8)
        rel = V - np.array(c[:])
        ls = rel @ np.array(f[:])
        lh = rel @ np.array(h[:])
        d2 = (ls / 1.9) ** 2 + (lh / 1.2) ** 2
        m = (d2 < 1.0) & (V[:, 0] * sx > 3.0)
        V[m, 0] -= sx * 0.9 * (1 - d2[m]) ** 1.5
    beak.add(V, F)

    def lower_shape(a, t):          # oben Rinne für die Zunge
        c, s = math.cos(a), math.sin(a)
        if s >= 0:
            return c, 0.3 * min(1.0, 4 * s) * c ** 4 - 0.1 * (1 - c * c)
        return c * (1 - 0.2 * s ** 4), -((-s) ** 0.85)

    path, rad = [], []
    for s, hi, lo, w in UNTERSCHNABEL:
        ss, hh = unterkiefer(s, hi - (hi - lo) / 1.3 * 0.3)
        path.append(schnabel_punkt(ss, hh)[:])
        rad.append((w, (hi - lo) / 1.3))
    path, rad = resample(path, rad, 60)
    V, F = loft(path, rad, K=40, shape=lower_shape, tips=(0, 0.8), up=h[:])
    beak.add(V, F)

    # Rachen: schließt den Mundwinkel innen, kurz und zurückgesetzt
    def ip(tab, col, s):
        return float(np.interp(s, [p[0] for p in tab], [p[col] for p in tab]))

    path, rad = [], []
    for s in np.linspace(0, 9, 5):
        top = ip(OBERSCHNABEL, 2, s)
        ss, bot = unterkiefer(s, ip(UNTERSCHNABEL, 1, s))
        path.append(schnabel_punkt(s, 0.5 * (top + bot))[:])
        rad.append((ip(UNTERSCHNABEL, 3, s) * 0.7, 0.5 * (top - bot) + 1.0))
    V, F = loft(path, rad, K=20, tips=(0, 1.5), up=h[:])
    beak.add(V, F)
    # Zunge: liegt in der Rinne des Unterschnabels, Spitze leicht angehoben
    path, rad = [], []
    for s in np.linspace(4, 28, 12):
        k = (s - 4) / 24
        lo_top = ip(UNTERSCHNABEL, 1, s)
        lo_bot = ip(UNTERSCHNABEL, 2, s)
        ry = (lo_top - lo_bot) / 1.3
        ss, hh = unterkiefer(s, lo_top - 0.4 * ry - 0.1 + 0.6 * k ** 2)
        path.append(schnabel_punkt(ss, hh)[:])
        rad.append((lerp(2.8, 0.9, k), lerp(1.5, 0.7, k)))
    V, F = loft(path, rad, K=20, tips=(0, 1.8), up=h[:])
    beak.add(V, F)
    beak_ob = beak.build("Schnabel", c_det, m_beak)
    set_smooth(beak_ob, angle=math.radians(60))
    return beak_ob


def kopf_feder(det, bvh, inner, direction, flow, L, W, lift=0.0, embed=1.0, roll=0.0, **kw):
    """Wie surface_feather, aber ohne Zufall (sauber, symmetrisch)."""
    p, n = on_surface(bvh, inner, direction, embed)
    if p is None:
        return None
    flow = Vector(flow)
    tang = flow - n * flow.dot(n)
    if tang.length < 1e-6:
        return None
    tang.normalize()
    D = tang * math.cos(lift) + n * math.sin(lift)
    V, F = feather(L, W, **kw)
    V[:, 2] *= 1.0 - 0.75 * np.clip(V[:, 0] / L, 0, 1) ** 1.6     # Spitze auch in der Dicke scharf
    V = place(V, p, D, n, roll=roll)
    if in_sperrzone(V):
        return None
    return V, F


def build_augen(outer_bvh, det, c_det, m_eye, m_pupil):
    """Rote Augen (flache Linse unter der Braue), Pupillen, böse Brauen, Unterlid.
    Gebaut für die linke Kopfseite (+X) und gespiegelt."""
    eye_acc, pupil_acc = Acc(), Acc()
    dirv = Vector((1.0, -0.35, 0.08)).normalized()
    p, n = on_surface(outer_bvh, (0, -84, 95), dirv, embed=0.0)
    fwd = Vector((0, -1, -0.15))
    fwd = (fwd - n * fwd.dot(n)).normalized()      # zum Schnabel
    dnv = n.cross(fwd).normalized()                # nach unten (rechtshändig: fwd, dnv, n)
    upv = -dnv
    RF, RU, RN, TIEF = 6.6, 5.5, 3.1, 1.6
    ec = p - n * TIEF
    V, F = ellipsoid((0, 0, 0), (RF, RU, RN), K=40, rings=20)
    Ve = frame_to_world(V, ec, fwd, dnv, n)
    eye_acc.add(Ve, F)
    eye_acc.add_mirrored(Ve, F)
    # Pupille: kleine, fast bündige dunkle Scheibe, nach vorne unter die Braue versetzt
    pf, pu = 1.8, 0.4
    pz = RN * math.sqrt(max(0.0, 1 - (pf / RF) ** 2 - (pu / RU) ** 2)) - 0.3
    Vp, Fp = ellipsoid((0, 0, 0), (0.8, 1.0, 0.4), K=20, rings=10)
    Vp = frame_to_world(Vp, ec + fwd * pf + upv * pu + n * pz, fwd, dnv, n)
    pupil_acc.add(Vp, Fp)
    pupil_acc.add_mirrored(Vp, Fp)

    def snap(pt, lift):
        lc, nrm = outer_bvh.find_nearest(Vector(pt))[:2]
        return (lc + nrm.normalized() * lift)[:]

    # Braue: schwerer Wulst mit steiler Kante über dem Auge, zur Stirn flach auslaufend.
    # (f, u, Abheben, Breite, Höhe) in Augenkoordinaten; Breite = Mitte bis Augenkante
    bp = [(-6.5, 4.6, -0.7, 1.4, 0.7), (-3.0, 4.3, 0.0, 2.0, 1.0), (0.5, 3.4, 0.3, 2.2, 1.3),
          (4.0, 2.0, 0.35, 2.1, 1.2), (7.5, 0.6, 0.1, 1.8, 0.9), (10.5, -0.6, -0.4, 1.3, 0.6),
          (13.0, -1.3, -0.9, 0.9, 0.4)]
    path0 = [snap(ec + fwd * fb + upv * ub, lb) for fb, ub, lb, wb, hb in bp]
    path, br = resample(path0, [(wb, hb) for fb, ub, lb, wb, hb in bp], 36)
    _, bl = resample(path0, [lb for fb, ub, lb, wb, hb in bp], 36)
    tt = np.linspace(0, 1, len(path))

    # Querschnitt: +X zeigt im Loft (n x Tangente) nach unten zum Auge. Zum Auge hin steile
    # Kante, zur Stirn läuft der Wulst tangential in die (gekrümmte) Haut aus.
    R_KOPF, X_STIRN = 20.0, 2.8

    def brow_shape(a, t):
        lift = float(np.interp(t, tt, bl))
        rx = float(np.interp(t, tt, [r[0] for r in br]))
        ry = float(np.interp(t, tt, [r[1] for r in br]))
        dmax = X_STIRN * rx
        y_bot = (-lift - 1.0 - dmax ** 2 / (2 * R_KOPF)) / ry - 0.3
        if a <= math.pi:
            x = 1.0 - (1.0 + X_STIRN) * a / math.pi
            if x >= 0:
                y_e = (-lift - 1.0) / ry
                return x, y_e + (1 - y_e) * math.sqrt(max(0.0, 1 - x ** 2.5))
            d = -x * rx
            g = math.cos(0.5 * math.pi * d / dmax) ** 2
            return x, (-d * d / (2 * R_KOPF) + (lift + ry) * g - 0.3 * (1 - g) - lift) / ry
        x = -X_STIRN + (1.0 + X_STIRN) * (a - math.pi) / math.pi
        return x, y_bot

    KB = 36
    V, F = loft(path, br, K=KB, shape=brow_shape, tips=(0.6, 0.6), up=n[:])
    # Stirnseite exakt auf die echte Haut legen (tangentialer Übergang ohne Kante)
    for i, t in enumerate(tt):
        lift = bl[i]
        rx, ry = br[i]
        dmax = X_STIRN * rx
        for k in range(KB):
            a = 2 * math.pi * k / KB
            x, _ = brow_shape(a, t)
            if x >= 0:
                continue
            d = -x * rx
            g = math.cos(0.5 * math.pi * min(d / dmax, 1.0)) ** 2
            hz = (lift + ry) * g - 0.3 * (1 - g) if a <= math.pi else -1.5
            w = float(smoothstep(0.0, 0.6, -x))
            lc, nrm = outer_bvh.find_nearest(Vector(V[i * KB + k]))[:2]
            V[i * KB + k] = (1 - w) * V[i * KB + k] + w * np.array((lc + nrm.normalized() * hz)[:])
    det.add(V, F)
    det.add_mirrored(V, F)
    # Unterlid: dünner Rand um die untere Augenhälfte
    lid = []
    for a in np.linspace(math.radians(190), math.radians(350), 9):
        lid.append(snap(ec + fwd * (RF * 0.86 * math.cos(a)) + upv * (RU * 0.86 * math.sin(a)), 0.1))
    lid, lr = resample(lid, [0.45, 0.6, 0.7, 0.7, 0.7, 0.7, 0.7, 0.6, 0.45], 24)
    V, F = loft(lid, lr, K=10, tips=(0.4, 0.4), up=n[:])
    det.add(V, F)
    det.add_mirrored(V, F)
    return eye_acc.build("Augen", c_det, m_eye), pupil_acc.build("Pupillen", c_det, m_pupil)


def build_halskrause(outer_bvh, det):
    """Federband am Übergang Kopf/Hals: oben kurze Stacheln (Nackenkamm), seitlich schmale,
    spitze Hackles nach hinten, an der Kehle flach anliegende Krausenfedern.
    Symmetrisch und ohne Zufall."""
    nhalb = 12
    for ri in range(3):
        for k in range(nhalb + 1):
            phi = math.pi * (k + 0.5 * (ri % 2)) / nhalb
            if phi > math.pi + 1e-6:
                continue
            u = (1 - math.cos(phi)) / 2               # 0 = Nacken, 1 = Kehle
            if ri == 2 and u < 0.1:
                continue                              # Nackenkamm: nur zwei Reihen
            y = lerp(-57, -86, u ** 0.8) + 6.5 * ri
            dirv = Vector((math.sin(phi), 0.0, math.cos(phi)))
            var = 1 + 0.07 * math.sin(3.7 * k + 1.3 * ri)
            L = lerp(10.5, 16.5, u ** 0.6) * var * (1.0 - 0.04 * ri)
            W = lerp(6.8, 7.0, u)
            lift = math.radians(lerp(30, 10, u ** 0.7))
            flow = (0, 1.0, lerp(0.4, -1.3, u))
            res = kopf_feder(det, outer_bvh, (0, y, 88), dirv, flow, L, W, lift=lift, embed=1.0,
                             th=lerp(2.2, 1.7, u), point=0.95, taper=lerp(0.1, 0.18, u),
                             bend=lerp(-0.05, 0.04, u), cup=0.12, rachis=0.6)
            if res is None:
                continue
            V, F = res
            det.add(V, F)
            if 1e-6 < phi < math.pi - 1e-6:
                det.add_mirrored(V, F)


def build_kopf(outer_bvh, det, c_det, m_beak, m_eye, m_pupil):
    """Schnabel, Augen, Brauen, Unterlider, Halskrause.
    Federn kommen in den Sammler det; Rückgabe: (Schnabel, Augen, Pupillen)."""
    beak_ob = build_schnabel(c_det, m_beak)
    eye_ob, pupil_ob = build_augen(outer_bvh, det, c_det, m_eye, m_pupil)
    build_halskrause(outer_bvh, det)
    # Gesicht (Schnabelansatz, Wangen unter den Augen, Kinn) bleibt glatt: Sperrzone für alle
    # danach aufgesetzten Federn (Achse nach vorne ab y = -82)
    SPERRZONEN.append((Vector((0, -82, 86)), Vector((0, -1, 0)), 24.0, 0.0, 120.0))
    return beak_ob, eye_ob, pupil_ob
# <<< TEIL kopf


# >>> TEIL koerperfedern
def koerper_feder_an(acc, P, n, flow, L, W, lift=0.05, roll=0.0, **kw):
    """Legt eine Feder bei P (Normale n) entlang flow auf die Oberfläche – ohne Zufallsrolle,
    damit die Reihe ruhig und regelmäßig wirkt. Gibt False zurück, wenn sie im Sperrbereich läge."""
    flow = Vector(flow)
    tang = flow - n * flow.dot(n)
    if tang.length < 1e-6:
        return False
    tang.normalize()
    D = tang * math.cos(lift) + n * math.sin(lift)
    V, F = feather(L, W, **kw)
    V = place(V, P, D, n, roll=roll)
    if in_sperrzone(V):
        return False
    acc.add(V, F)
    return True


def koerper_von_innen(bvh, origin, direction, embed=1.0, maxdist=18.0):
    """Strahl aus dem (massiven) Körperinneren nach außen: Austrittspunkt (leicht eingesenkt)
    und Normale – oder (None, None), wenn der Strahl zu weit läuft (z. B. ins andere Bein)."""
    d = Vector(direction).normalized()
    hit = bvh.ray_cast(Vector(origin), d)
    if hit[0] is None or (hit[0] - Vector(origin)).length > maxdist:
        return None, None
    n = hit[1].normalized()
    if n.dot(d) < 0.2:
        return None, None
    return hit[0] - n * embed, n


def build_koerperfedern(outer_bvh, det):
    """Oberschenkel-Saum (in den Sammler det). Brust, Bauch, Flanken und Schultern bleiben glatt
    wie bei der Vorlage – am Vorderkörper sorgt nur die Halskrause des Kopfes für Struktur.
    Die "Hosen" enden in einem kurzen, gleichmäßig gezackten Saum um den Lauf."""
    hx, hy, hz = HOSEN_MITTE
    for sx in (1, -1):
        for k in range(12):
            psi = math.radians(lerp(-155.0, 155.0, k / 11.0))     # 0 = außen, -90 = vorne
            dirv = Vector((sx * math.cos(psi), -math.sin(psi), -0.55))
            P, nrm = koerper_von_innen(outer_bvh, (sx * hx, hy, hz - 3.0), dirv, embed=1.1)
            if P is None:
                continue
            L = 10.5 - 1.2 * abs(math.cos(psi))                   # vorne/hinten etwas länger
            koerper_feder_an(det, P, nrm, (sx * 0.05, 0.25, -1.0), L, 7.5, lift=math.radians(10),
                             th=1.2, point=0.38, taper=0.45, bend=0.05, cup=0.16, rachis=0.35)
# <<< TEIL koerperfedern


# >>> TEIL schwanz
SCHWANZ_N = 9            # Steuerfedern (ungerade: eine Mittelfeder liegt oben)
SCHWANZ_FAECHER = 34.0   # Gesamt-Spreizung des Fächers in Grad
SCHWANZ_STUFE = 0.6      # jede Feder nach außen liegt so viel tiefer (saubere Überlappung)
SCHWANZ_TIEFE = 2.8      # Ansatz liegt so weit unter der Rückenoberfläche


def _richtung(yaw_deg, pitch_deg):
    """Einheitsvektor nach hinten (+Y), yaw > 0 nach +X, pitch > 0 nach oben."""
    a, p = math.radians(yaw_deg), math.radians(pitch_deg)
    return Vector((math.sin(a) * math.cos(p), math.cos(a) * math.cos(p), math.sin(p)))


def build_schwanz(outer_bvh, c_det, m_body):
    """Schmaler, keilförmiger Schwanz, der die Rückenlinie fast waagrecht fortsetzt,
    plus Oberschwanzdecken über der Ansatznaht. Glatte, gestufte Federn ohne Ausfransung."""
    tail = Acc()
    th_hit = outer_bvh.ray_cast(Vector((0, 300, 84)), Vector((0, -1, 0)))
    troot = th_hit[0] + Vector((0, -14, 3.5))      # Ansatz steckt im Bürzel
    oben = outer_bvh.ray_cast(Vector((0, troot.y, 300)), Vector((0, 0, -1)))[0]
    if oben is not None:                           # knapp unter der Rückenlinie: Schwanz setzt sie fort
        troot.z = max(troot.z, oben.z - SCHWANZ_TIEFE)
    mid = (SCHWANZ_N - 1) / 2
    for i in range(SCHWANZ_N):
        f = i / (SCHWANZ_N - 1) - 0.5               # -0.5 .. 0.5
        stufe = abs(i - mid)                        # 0 = Mittelfeder (oben)
        L = 64 - 18 * (2 * abs(f)) ** 1.3           # Keilform: Mitte am längsten
        D = _richtung(f * SCHWANZ_FAECHER, -6 - 4 * abs(f))
        P = troot + Vector((f * 14, 0.6 * stufe, -SCHWANZ_STUFE * stufe))
        V, F = feather(L, 20, th=2.0, point=0.12, taper=0.55, bend=0.025, cup=0.06, rachis=0.4,
                       notches=0, jag=0.0, barbs=0.0)
        tail.add(place(V, P, D, (0, 0, 1), roll=f * 0.12), F)
    # Oberschwanzdecken: breit, rund, ohne Zufallsrollen – decken die Naht Körper/Schwanz
    nc = 5
    cmid = (nc - 1) / 2
    for i in range(nc):
        f = i / (nc - 1) - 0.5
        stufe = abs(i - cmid)
        D = _richtung(f * 26, -9)
        P = troot + Vector((f * 12, -5.0 + 1.5 * stufe, 3.0 - 0.45 * stufe))
        V, F = feather(33 - 3.0 * stufe, 13, th=1.5, point=0.12, taper=0.5, bend=0.05, cup=0.08, rachis=0.4)
        tail.add(place(V, P, D, (0, 0, 1)), F)
    tail_ob = tail.build("Schwanz", c_det, m_body)
    return tail_ob
# <<< TEIL schwanz


# >>> TEIL beine
SOCKEL_R = 50.0          # Sockelradius (Ø 100 mm), schlichte Scheibe mit kleiner Fase
SOCKEL_H = 6.2           # Sockelhöhe
SOCKEL_Y = -9.0          # Sockelmitte (Y) unter den Füßen
EINSINKEN = 0.3          # Zehen/Krallen sinken so weit in den Sockel ein (druckt verbunden)
FUSS_YAW = 6.0           # Füße leicht nach außen gedreht (Grad)


def _ss(e0, e1, x):
    return float(smoothstep(e0, e1, x))


def _saege(u, kante=0.86):
    """Sägezahn 0..1 für überlappende Schuppen: steigt langsam an, fällt an der Unterkante steil ab."""
    ph = u % 1.0
    return (ph / kante) ** 1.4 if ph < kante else (1.0 - ph) / (1.0 - kante)


def _lauf(top, foot):
    """Lauf (Tarsometatarsus): oben kräftig, vorne überlappende rechteckige Hornschilde, Seiten glatt."""
    n = 150
    ts = np.linspace(0, 1, n)
    path, radii = [], []
    bow = Vector((0, -1.2, 0))                   # ganz leicht nach vorne gewölbt
    ende = foot + (foot - top).normalized() * 1.6   # rundes Fußgelenk reicht etwas unter den Fußpunkt
    te = 0.9                                     # ab hier läuft der Lauf in eine Kugel aus
    for t in ts:
        path.append((top.lerp(ende, t) + bow * math.sin(math.pi * t))[:])
        r = lerp(6.1, 4.8, _ss(0.0, 0.75, t)) + 0.35 * _ss(0.8, te, t)
        if t > te:                               # Kugelende statt Kappe -> kein Absatz am Gelenk
            r *= math.sqrt(max(1.0 - ((t - te) / (1.0 - te)) ** 2, 0.0)) ** 0.8
        radii.append((max(r, 0.05), max(r, 0.05) * 1.12))
    n_pl, t0, t1 = 8, 0.2, 0.84                  # Schilde im sichtbaren Bereich

    def shape(a, t):
        c, s = math.cos(a), math.sin(a)          # a = 90° zeigt nach vorne (up = -Y)
        d = abs(math.atan2(c, s))                # Winkel zur Vorderseite
        m = 1.0 - _ss(math.radians(46), math.radians(60), d)
        u = (t - t0) / (t1 - t0)
        k = 0.0
        if 0.0 <= u < 1.0:
            k = _saege(u * n_pl) * (1.0 - 0.25 * u)
        f = (1.0 - 0.05 * m) + 0.085 * m * k     # Vorderseite leicht abgeflacht, Schilde stehen vor
        return c * f, s * f
    return loft(path, radii, K=36, shape=shape, tips=(1.0, 0.0), up=(0, -1, 0))


def _zehe(foot, dvec, L, r0, nseg, base_top):
    """Kräftige Zehe: Gelenkpolster, feine Querschuppen oben, flache Sohle, Ballen vor der Kralle,
    jedes Glied leicht gewölbt. Liefert (V, F), Endpunkt, Endradius."""
    n = 96
    ts = np.linspace(0, 1, n)
    gelenke = [k / nseg for k in range(1, nseg)] + [0.9]
    rings = nseg * 4
    pts, rr = [], []
    for t in ts:
        joint = max(math.exp(-((t - g) / 0.07) ** 2) for g in gelenke[:-1]) if nseg > 1 else 0.0
        pad = math.exp(-((t - 0.9) / 0.06) ** 2)
        r = r0 * lerp(1.0, 0.78, t) * (1 + 0.12 * joint + 0.13 * pad)
        rx, ry = r * 1.05, r * 0.92
        # Bodenkontakt an Gelenken und Ballen, dazwischen Glieder leicht gewölbt
        kontakt = max(math.exp(-((t - g) / 0.08) ** 2) for g in gelenke)
        arch = 0.7 * (1.0 - kontakt) * _ss(0.12, 0.3, t)
        zg = base_top - EINSINKEN + 0.8 * ry + arch
        z = lerp(foot.z, zg, _ss(0.0, 0.3, t))
        p = Vector((foot.x, foot.y, 0.0)) + dvec * (L * t)
        p.z = max(z, zg)
        pts.append(p[:])
        rr.append((rx, ry))

    def shape(a, t):
        c, s = math.cos(a), math.sin(a)          # a = 90° oben
        if s < 0:                                # flache, etwas breitere Sohle
            return c * (1 + 0.08 * -s), s * 0.8
        k = _saege(t * rings + 0.3) * _ss(0.15, 0.5, s) * _ss(0.05, 0.12, t) * (1 - _ss(0.93, 0.99, t))
        f = 1.0 + 0.055 * k
        return c * f, s * f
    V, F = loft(pts, rr, K=20, shape=shape, tips=(0.5, 1.2), up=(0, 0, 1))
    return V, F, Vector(pts[-1]), rr[-1]


def _kralle(e, dvec, base_top, length=9.5):
    """Dicke, stark nach unten gekrümmte Kralle; die Spitze sitzt auf dem Sockel."""
    n = 30
    ts = np.linspace(0, 1, n)
    r_tip = (0.35, 0.4)
    z_tip = base_top - EINSINKEN + r_tip[1] * 0.85
    rise = lambda t: 1.2 * math.sin(math.pi * t * 0.6)
    drop = e.z + rise(1.0) - z_tip
    pts, rr = [], []
    for t in ts:
        w = t ** 0.85
        rx, ry = lerp(2.5, r_tip[0], w), lerp(2.8, r_tip[1], w)
        p = e + dvec * (length * t * (1 - 0.18 * t * t))   # Spitze krümmt sich steil nach unten
        p.z = e.z + rise(t) - drop * t ** 1.8
        p.z = max(p.z, base_top - EINSINKEN + 0.85 * ry)
        pts.append(p[:])
        rr.append((rx, ry))

    def shape(a, t):
        c, s = math.cos(a), math.sin(a)
        if s > 0:                                # schmaler First oben
            return c * (1 - 0.35 * s * s), s
        return c, s * 0.85
    return loft(pts, rr, K=16, shape=shape, tips=(0.0, 0.25), up=(0, 0, 1))


def build_beine(c_det, m_leg):
    """Läufe, Zehen und Krallen (Sockel-Oberseite liegt beim Aufbau bei SOCKEL_Z + SOCKEL_H)."""
    legs = Acc()
    base_top = SOCKEL_Z + SOCKEL_H
    top = Vector((14.5, -4.0, 50.0))                 # steckt im Oberschenkel
    foot = Vector((19.5, -13.0, base_top + 4.4))     # leicht nach außen und vorne gestellt
    parts = [_lauf(top, foot)]
    yaw = math.radians(FUSS_YAW)
    toes = [(-30, 26.0, 3.75, 3), (0, 30.0, 4.0, 3), (28, 24.0, 3.6, 3), (180, 19.0, 3.6, 2)]
    for ang, L, r0, nseg in toes:
        if ang == 180:
            dvec = Vector((-0.08, 1.0, 0.0)).normalized()
        else:
            a = yaw + math.radians(ang)              # positiv = nach außen
            dvec = Vector((math.sin(a), -math.cos(a), 0.0))
        V, F, e, re = _zehe(foot, dvec, L, r0, nseg, base_top)
        parts.append((V, F))
        parts.append(_kralle(e - dvec * 1.8, dvec, base_top, length=10.0 if ang != 180 else 9.0))
    for V, F in parts:                               # linker Fuß + gespiegelter rechter Fuß
        legs.add(V, F)
        legs.add_mirrored(V, F)
    legs_ob = legs.build("Beine", c_det, m_leg)
    return legs_ob


def build_sockel(c_det, m_body):
    """Schlichte runde Scheibe mit scharfer Oberkante und kleiner Fase."""
    R, H = SOCKEL_R, SOCKEL_H
    V, F = lathe([(0, 0), (R - 0.6, 0), (R, 0.6), (R, H - 0.8), (R - 0.8, H), (0, H)], K=220)
    V = V + np.array([0, SOCKEL_Y, SOCKEL_Z])
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
    m_beak = material("Kraehe_Schnabel", (0.014, 0.014, 0.015), rough=0.4, spec=0.4, coat=0.1)
    m_leg = material("Kraehe_Beine", (0.016, 0.016, 0.018), rough=0.5, spec=0.3)
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
    legs_ob = build_beine(c_det, m_leg)
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
