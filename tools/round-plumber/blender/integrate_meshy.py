"""Put a Meshy model of the round plumber onto the procedural rig (hybrid).

    python3 blender/integrate_meshy.py [meshy_model.zip|obj|glb] [out.glb] [--triangles N]     (needs bpy + pillow)

Default input: meshy/Meshy_AI_Luigi_1021080809_texture_obj.zip (the Meshy OBJ export: .obj, .mtl, .png).

The Meshy model supplies head, face, cap, mustache, ears and the ball body. Its arms are only short stubs
fused onto the belly, too short for the vacuum / flashlight / uppercut clips, so the procedural arms with
their finger rig and the shoes stay, together with the animated eyes, lids, brows, mouth and the gear.

1. imports the procedural character (public/round-plumber.glb: rig, 32 clips) and the Meshy model,
   welds UV-seam copies and decimates it to about N triangles (default 70000)
2. aligns it to the bind pose against the procedural body + head (yaw candidates, bounding box, trimmed ICP)
3. flattens the Meshy arms onto the ball (fitted ellipsoid) and repaints them with the surrounding fabric
4. paints the painted-on eyes and brows over with skin, the animated ones take their place
5. transfers skin weights from the procedural body + head (closest face facing the same way, smoothed),
   at most 4 influences per vertex
6. moves the animated eyes, brows and mouth onto the Meshy face surface
7. exports meshes + skin from Blender, then copies the original clip tracks and clip info (scene extras)
   in unchanged: Blender would resample every clip over all bones, scale channels included
8. writes public/round-plumber-meshy.glb (texture as 2048 px JPEG)
"""
import colorsys
import io
import json
import math
import os
import struct
import sys
import tempfile
import zipfile

import bpy  # first: bmesh / mathutils come with it
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc
from mathutils.kdtree import KDTree
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
SRC_GLB = os.path.join(ROOT, 'public', 'round-plumber.glb')
MESHY_ZIP = os.path.join(HERE, '..', 'meshy', 'Meshy_AI_Luigi_1021080809_texture_obj.zip')
TEXTURE = 2048
DONORS = ['PlumberBody', 'PlumberHead']  # replaced by the Meshy model, donate weights
OVERLAYS = ['PlumberLimbs', 'PlumberEyes', 'PlumberFace', 'PlumberGear', 'PlumberGlow']  # stay as they are


def world_verts(obj):
    m = obj.matrix_world
    return np.array([tuple(m @ v.co) for v in obj.data.vertices])


def bvh_of(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def edge_array(obj):
    return np.array([e.vertices[:] for e in obj.data.edges])


def neighbour_mean(values, edges):
    acc = np.zeros_like(values)
    np.add.at(acc, edges[:, 0], values[edges[:, 1]])
    np.add.at(acc, edges[:, 1], values[edges[:, 0]])
    deg = np.bincount(edges.ravel(), minlength=len(values)).reshape(-1, *([1] * (values.ndim - 1)))
    return np.where(deg > 0, acc / np.maximum(deg, 1), values)


def umeyama(src, dst, scale_range):
    """similarity transform (s, R, t) minimising |s R src + t - dst|, s clamped to scale_range"""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / len(src)
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    s = float(np.clip(np.trace(np.diag(D) @ S) / xs.var(0).sum(), *scale_range))
    return s, R, mu_d - s * R @ mu_s


def homogeneous(m3):
    m = np.eye(4)
    m[:3, :3] = m3
    return m


def align(meshy, donor_pts, trim=0.8):
    """yaw candidates, bounding-box fit, then ICP; the scale may only drift a little from the
    bounding-box fit (nearest-vertex matches against the inner donor surfaces pull it inwards)"""
    kd = KDTree(len(donor_pts))
    for i, p in enumerate(donor_pts):
        kd.insert(p, i)
    kd.balance()
    base = world_verts(meshy)
    rng = np.random.default_rng(1)
    sample = base[rng.choice(len(base), min(6000, len(base)), replace=False)]
    sample_h = np.c_[sample, np.ones(len(sample))]
    dmin, dmax = donor_pts.min(0), donor_pts.max(0)
    best = None
    for yaw in (0, 90, 180, 270):
        Rz = np.array(Matrix.Rotation(math.radians(yaw), 3, 'Z'))
        pts = sample @ Rz.T
        lo, hi = pts.min(0), pts.max(0)
        s0 = (dmax[2] - dmin[2]) / (hi[2] - lo[2])
        t = np.array([(dmin[0] + dmax[0]) / 2, (dmin[1] + dmax[1]) / 2, dmin[2]]) - s0 * np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        M = np.eye(4)
        M[:3, :3] = s0 * Rz
        M[:3, 3] = t
        scale = 1.0
        for _ in range(30):
            cur = (sample_h @ M.T)[:, :3]
            hits = [kd.find(p) for p in cur]
            nn, dist = np.array([tuple(h[0]) for h in hits]), np.array([h[2] for h in hits])
            near = dist <= np.quantile(dist, trim)  # parts the procedural model lacks must not drag the fit
            s2, R2, t2 = umeyama(cur[near], nn[near], (0.9 / scale, 1.1 / scale))
            scale *= s2
            step = homogeneous(s2 * R2)
            step[:3, 3] = t2
            M = step @ M
        cur = (sample_h @ M.T)[:, :3]
        dist = np.array([kd.find(p)[2] for p in cur])
        err = float(np.mean(dist[dist <= np.quantile(dist, trim)]))
        print(f'  yaw {yaw:3d}: mean distance {err * 1000:.1f} mm, scale {scale:.3f} of the bounding-box fit')
        if best is None or err < best[0]:
            best = (err, M, yaw)
    print(f'aligned with yaw {best[2]}, mean surface distance {best[0] * 1000:.1f} mm')
    meshy.matrix_world = Matrix(best[1].tolist()) @ meshy.matrix_world
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    meshy.select_set(True)
    bpy.context.view_layer.objects.active = meshy
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return best[0]


# ---------------------------------------------------------------------------
# texture: per-vertex colours and repainting
# ---------------------------------------------------------------------------
def texel(tex, uv):
    """texels of an (h, w, c) array at Blender uvs (v up, image rows go down)"""
    h, w = tex.shape[:2]
    x = np.clip((uv[:, 0] * w).astype(int), 0, w - 1)
    y = np.clip(((1 - uv[:, 1]) * h).astype(int), 0, h - 1)
    return tex[y, x]


def vertex_uvs(obj):
    uv = obj.data.uv_layers.active.data
    out = np.zeros((len(obj.data.vertices), 2))
    for loop in obj.data.loops:
        out[loop.vertex_index] = uv[loop.index].uv
    return out


def hsv_of(rgb):
    return np.array([colorsys.rgb_to_hsv(*c) for c in rgb / 255]) * [360, 1, 1]


def raster(q, margin):
    """pixels of a triangle (pixel coords, rows down), widened by margin pixels: (xy, barycentric)"""
    a, e1, e2 = q[0], q[1] - q[0], q[2] - q[0]
    det = e1[0] * e2[1] - e2[0] * e1[1]
    if abs(det) < 1e-9:
        return np.zeros((0, 2), int), np.zeros((0, 3))
    lo, hi = np.floor(q.min(0) - margin).astype(int), np.ceil(q.max(0) + margin).astype(int)
    xs, ys = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
    rel = np.c_[xs.ravel() + 0.5, ys.ravel() + 0.5] - a
    b1 = (rel[:, 0] * e2[1] - e2[0] * rel[:, 1]) / det
    b2 = (e1[0] * rel[:, 1] - rel[:, 0] * e1[1]) / det
    bc = np.c_[1 - b1 - b2, b1, b2]
    tol = margin / max(np.linalg.norm(e1), np.linalg.norm(e2), 1e-6)
    inside = (bc > -tol).all(1)
    bc = np.clip(bc[inside], 0, 1)
    return np.c_[xs.ravel()[inside], ys.ravel()[inside]], bc / bc.sum(1, keepdims=True)


def repaint(tex, obj, co, tris, fabrics, classify=None, gutter=4, vote_k=12, colour_k=24):
    """overwrite the texels of the given loop triangles with what the surface around them is made of.

    fabrics: [(points, colours)] per material next to the area (shirt, overalls, skin ...). A texel
    belongs to the fabric classify(point) names, or else to the one most of its closest source points
    belong to (weighted by 1 / distance^2, so borders stay crisp), and gets the smooth inverse-distance
    average of that fabric's colours (wide, so stitches and specks next to the area do not stamp patches
    into it). The triangles are widened by `gutter` pixels into texels no other triangle uses: texture
    filtering and mip maps read those, and they still hold the old colours."""
    h, w = tex.shape[:2]
    uv = obj.data.uv_layers.active.data
    lts = obj.data.loop_triangles
    if not all(len(p) for p, _ in fabrics):
        raise SystemExit('nothing to repaint from')

    def tree(pts):
        kd = KDTree(len(pts))
        for i, p in enumerate(pts):
            kd.insert(p, i)
        kd.balance()
        return kd

    def pixel_tri(t):
        q = np.array([uv[l].uv[:] for l in lts[t].loops]) * [w, h]
        q[:, 1] = h - q[:, 1]
        return q

    chosen = set(tris)
    used = np.zeros((h, w), bool)  # texels of the other triangles stay as they are
    for t in range(len(lts)):
        if t not in chosen:
            xy, _ = raster(pixel_tri(t), 0.5)
            xy = xy[(xy[:, 0] >= 0) & (xy[:, 0] < w) & (xy[:, 1] >= 0) & (xy[:, 1] < h)]
            used[xy[:, 1], xy[:, 0]] = True
    owner = np.concatenate([np.full(len(p), k) for k, (p, _) in enumerate(fabrics)])
    vote = tree(np.concatenate([p for p, _ in fabrics]))
    trees = [tree(p) for p, _ in fabrics]
    pix, pts = [], []
    for t in tris:
        xy, bc = raster(pixel_tri(t), gutter)
        ok = (xy[:, 0] >= 0) & (xy[:, 0] < w) & (xy[:, 1] >= 0) & (xy[:, 1] < h)
        xy, bc = xy[ok], bc[ok]
        ok = ~used[xy[:, 1], xy[:, 0]]
        pix.append(xy[ok])
        pts.append(bc[ok] @ co[list(lts[t].vertices)])
    if not pix:
        return 0
    pix, pts = np.concatenate(pix), np.concatenate(pts)
    kinds = classify(pts) if classify else None
    for n, ((x, y), p) in enumerate(zip(pix, pts)):
        if kinds is not None:
            k = int(kinds[n])
        else:
            score = np.zeros(len(fabrics))
            for _, i, d in vote.find_n(p, vote_k):
                score[owner[i]] += 1 / (d + 0.003) ** 2
            k = int(score.argmax())
        hits = trees[k].find_n(p, colour_k)
        wts = np.array([1 / (d + 0.01) for _, _, d in hits])
        tex[y, x] = (wts[:, None] * fabrics[k][1][[i for _, i, _ in hits]]).sum(0) / wts.sum()
    return len(pix)


def triangles_touching(obj, mask):
    return [i for i, lt in enumerate(obj.data.loop_triangles) if mask[list(lt.vertices)].any()]


def grow(mask, edges, rings, allowed=None):
    for _ in range(rings):
        nxt = mask.copy()
        nxt[edges[mask[edges[:, 0]], 1]] = True
        nxt[edges[mask[edges[:, 1]], 0]] = True
        mask = nxt if allowed is None else (nxt & allowed) | mask
    return mask


# ---------------------------------------------------------------------------
# remove the Meshy arms: flatten them onto the ball, repaint with the fabric around them
# ---------------------------------------------------------------------------
class Ellipsoid:
    def __init__(self, centre, radii):
        self.c, self.r = centre, radii

    def scale(self, p):
        return np.sqrt((((p - self.c) / self.r) ** 2).sum(-1))

    def project(self, p):
        return self.c + (p - self.c) / self.scale(p)[:, None]

    def excess(self, p):
        """how far a point sticks out of the surface (along the ray from the centre)"""
        return np.linalg.norm(p - self.c, axis=-1) * (1 - 1 / self.scale(p))


def fit_ball(pts, iters=8, tol=0.006):
    """axis-aligned ellipsoid, symmetric in x; refitted without the points that stick out (arms, hands,
    buttons) until it hugs the bare ball. Solved as a x^2 + b y^2 + c z^2 + d y + e z = 1 around the
    centroid, which has to lie inside the ellipsoid for that form."""
    off = np.array([0, pts[:, 1].mean(), pts[:, 2].mean()])
    keep = np.ones(len(pts), bool)
    for _ in range(iters):
        x, y, z = (pts[keep] - off).T
        a, b, c, d, e = np.linalg.lstsq(np.c_[x * x, y * y, z * z, y, z], np.ones(len(x)), rcond=None)[0]
        y0, z0 = -d / (2 * b), -e / (2 * c)
        rhs = 1 + b * y0 * y0 + c * z0 * z0
        ball = Ellipsoid(off + np.array([0, y0, z0]), np.sqrt(rhs / np.array([a, b, c])))
        keep = ball.excess(pts) < tol
    return ball


def remove_arms(obj, tex, cols):
    """The Meshy arms are a relief on the sides of the ball (sleeve from the flank, glove on the belly).
    Push them down onto the ball, then repaint them with the shirt / overalls around them."""
    co = world_verts(obj)
    edges = edge_array(obj)
    hsv = hsv_of(cols)
    x, y, z = co.T
    ball = fit_ball(co[(z > 0.1) & (z < 0.62)])
    print(f'ball: centre {ball.c.round(3)}, radii {ball.r.round(3)}')
    ex = ball.excess(co)
    green = (hsv[:, 0] > 90) & (hsv[:, 0] < 150) & (hsv[:, 1] > 0.4)
    white = (hsv[:, 1] < 0.15) & (hsv[:, 2] > 0.75)
    flank = (np.abs(x) > 0.22) & (y < 0.15) & (z > 0.2) & (z < 0.68)
    seed = flank & (np.abs(x) > 0.27) & (ex > 0.012) & (green | white)
    arm = grow(seed, edges, 80, allowed=flank & (ex > 0.0025) & (green | white))
    # the glove lies flush on the belly at its rim: take the white around the hand as well (not lower
    # down, where the 1-up mushroom sticker sits)
    hand_level = z > 0.32
    arm = grow(arm, edges, 12, allowed=flank & white & hand_level)
    arm = grow(arm, edges, 2)
    ring = grow(arm, edges, 1) & ~arm
    print(f'arms: {arm.sum()} vertices flattened onto the ball')
    # height over the ellipsoid: what the bare ball around the arm has, spread smoothly across the arm
    h = np.where(ring, ex, 0.0)
    kd = KDTree(int(ring.sum()))
    for i, j in enumerate(np.nonzero(ring)[0]):
        kd.insert(co[j], i)
    kd.balance()
    ring_h = ex[ring]
    for j in np.nonzero(arm)[0]:
        hits = kd.find_n(co[j], 6)
        wts = np.array([1 / (d + 1e-3) for _, _, d in hits])
        h[j] = (wts * ring_h[[i for _, i, _ in hits]]).sum() / wts.sum()
    for _ in range(300):
        h[arm] = neighbour_mean(h, edges)[arm]
    # even spacing on the ellipsoid (boundary pinned), then lift by the height field
    target = co.copy()
    target[arm] = ball.project(co[arm])
    for _ in range(80):
        target[arm] = ball.project((0.5 * target + 0.5 * neighbour_mean(target, edges))[arm])
    radial = target[arm] - ball.c
    target[arm] += radial / np.linalg.norm(radial, axis=1, keepdims=True) * h[arm, None]
    inv = obj.matrix_world.inverted()
    for i in np.nonzero(arm)[0]:
        obj.data.vertices[i].co = inv @ Vector(target[i])
    obj.data.update()
    obj.data.calc_loop_triangles()
    navy = (hsv[:, 0] > 195) & (hsv[:, 0] < 255) & (hsv[:, 1] > 0.45) & (hsv[:, 2] < 0.6)
    # Meshy painted the hidden belly under the hands with glove remnants: repaint a bit wider (fabric only)
    area = grow(arm, edges, 4, allowed=(green | navy | white) & hand_level)
    near = (z > 0.1) & (z < 0.75) & ~grow(arm, edges, 6) & (np.abs(ex) < 0.008)
    fabrics = [(target[m], cols[m].astype(float)) for m in (near & green, near & navy)]
    # where the overalls end and the shirt starts, as a height over the angle around the body, from the
    # shirt / overalls edges outside the arms (0.3..0.56 leaves out the straps up to the chin), carried
    # on under the arm
    outside = ~grow(arm, edges, 1)
    hem = (green[edges[:, 0]] & navy[edges[:, 1]]) | (navy[edges[:, 0]] & green[edges[:, 1]])
    hem &= outside[edges[:, 0]] & outside[edges[:, 1]]
    mid = co[edges[hem]].mean(1)
    mid = mid[(mid[:, 2] > 0.3) & (mid[:, 2] < 0.56)]
    hem_angle, hem_z = np.arctan2(mid[:, 0], -mid[:, 1]), mid[:, 2]

    def shirt_or_overalls(p):
        angle = np.arctan2(p[:, 0], -p[:, 1])
        d = np.angle(np.exp(1j * (angle[:, None] - hem_angle[None, :])))
        wts = np.exp(-(d / 0.35) ** 2) + 1e-12
        return np.where(p[:, 2] > (wts * hem_z).sum(1) / wts.sum(1), 0, 1)

    n = repaint(tex, obj, target, triangles_touching(obj, area), fabrics, classify=shirt_or_overalls)
    print(f'arms: {n} texels repainted')
    return target


def paint_out_face(obj, tex, co, cols):
    """the animated eyes and brows replace the painted ones: skin over the painted eyes and brows"""
    edges = edge_array(obj)
    hsv = hsv_of(cols)
    h, s, v = hsv.T
    x, y, z = co.T
    front = y < -0.2
    eye_zone = front & (np.abs(x) > 0.02) & (np.abs(x) < 0.23) & (z > 0.74) & (z < 0.965)
    brow_zone = front & (np.abs(x) < 0.27) & (z > 0.9) & (z < 1.04)
    sclera = (s < 0.18) & (v > 0.7)
    iris = (h > 180) & (h < 240) & (s > 0.3)
    darkc = v < 0.45
    skin = (h > 8) & (h < 42) & (s > 0.18) & (s < 0.62) & (v > 0.6)
    green = (h > 90) & (h < 150) & (s > 0.35)
    stache = darkc & (z < 0.8)  # the mustache reaches up to the eyes; it stays
    paint = (eye_zone & (sclera | iris | (darkc & ~stache))) | (brow_zone & darkc)
    paint = grow(paint, edges, 1, allowed=front & ~green & ~stache & (z > 0.72))
    src = front & skin & ~grow(paint, edges, 1) & (z > 0.6) & (z < 1.05) & (np.abs(x) < 0.35)
    n = repaint(tex, obj, co, triangles_touching(obj, paint), [(co[src], cols[src].astype(float))])
    print(f'face: {paint.sum()} vertices / {n} texels painted over with skin')


# ---------------------------------------------------------------------------
# skin weights and overlay placement
# ---------------------------------------------------------------------------
def transfer_weights(meshy, donor, min_facing=0.2, smooth_steps=4, smooth=0.5, max_influences=4):
    """skin weights for the Meshy mesh from the procedural meshes.

    Shapes differ a little, and the closest procedural surface can be one facing the other way (an inner
    layer, the underside of a fold), which would tie a vertex to the wrong bone. So a vertex takes the
    closest procedural face that also faces its way (normals agree), interpolated over that face, and the
    result is smoothed along the Meshy edges."""
    names = [g.name for g in donor.vertex_groups]
    dw = np.zeros((len(donor.data.vertices), len(names)))
    for v in donor.data.vertices:
        for g in v.groups:
            dw[v.index, g.group] = g.weight
    tree = bvh_of(donor)
    dco = [donor.matrix_world @ v.co for v in donor.data.vertices]
    polys = donor.data.polygons
    rot = meshy.matrix_world.to_3x3()
    w = np.zeros((len(meshy.data.vertices), len(names)))
    rescued = 0
    for v in meshy.data.vertices:
        p, n = meshy.matrix_world @ v.co, (rot @ v.normal).normalized()
        loc, normal, face, dist = tree.find_nearest(p)
        if normal.dot(n) < min_facing:
            ok = [h for h in tree.find_nearest_range(p, dist + 0.04) if h[1].dot(n) >= min_facing]
            if ok:
                loc, normal, face, dist = min(ok, key=lambda h: h[3])
                rescued += 1
        idx = polys[face].vertices[:]
        w[v.index] = np.asarray(poly_3d_calc([dco[i] for i in idx], loc)) @ dw[list(idx)]
    edges = edge_array(meshy)
    for _ in range(smooth_steps):
        w = (1 - smooth) * w + smooth * neighbour_mean(w, edges)
    if 'Root' in names:
        w[:, names.index('Root')] = 0  # the Root bone must not carry influence
    top = np.argsort(-w, axis=1)[:, :max_influences]
    keep = np.zeros_like(w, dtype=bool)
    np.put_along_axis(keep, top, True, axis=1)
    w = np.where(keep & (w > 0.01), w, 0)
    w /= w.sum(1, keepdims=True)
    groups = [meshy.vertex_groups.new(name=n) for n in names]
    for vi, row in enumerate(w):
        for gi in np.nonzero(row)[0]:
            groups[gi].add([vi], float(row[gi]), 'REPLACE')
    for k, n in enumerate(names):
        if not w[:, k].any():
            meshy.vertex_groups.remove(meshy.vertex_groups[n])
    print(f'weights transferred ({rescued} vertices took a facing surface instead of the closest one)')


def offset_along(meshy_bvh, donor_bvh, origin, normal, reach=0.08):
    """signed distance between the Meshy surface and the procedural surface along a line; the ray starts
    only `reach` in front of the origin, under the cap brim that overhangs the brows"""
    start = origin + normal * reach
    hit_m = meshy_bvh.ray_cast(start, -normal, 0.6)[0]
    hit_d = donor_bvh.ray_cast(start, -normal, 0.6)[0]
    if hit_m is None or hit_d is None:
        return 0.0
    return (hit_m - hit_d).dot(normal)


def shift_vertices(obj, predicate, delta):
    inv = obj.matrix_world.inverted()
    d = inv.to_3x3() @ delta
    names = {g.index: g.name for g in obj.vertex_groups}
    n = 0
    for v in obj.data.vertices:
        groups = {names[g.group] for g in v.groups if g.weight > 0.01}
        if predicate(obj.matrix_world @ v.co, groups):
            v.co += d
            n += 1
    return n


# ---------------------------------------------------------------------------
# GLB post-processing
# ---------------------------------------------------------------------------
def read_glb(path):
    """(json, [bytes of each buffer view])"""
    data = open(path, 'rb').read()
    n = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20 + n])
    binary = data[20 + n + 8:]
    views = [binary[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']] for v in gltf['bufferViews']]
    return gltf, views


def write_glb(path, gltf, views):
    out = bytearray()
    for view, chunk in zip(gltf['bufferViews'], views):
        out += b'\0' * (-len(out) % 4)
        view.update(buffer=0, byteOffset=len(out), byteLength=len(chunk))
        out += chunk
    out += b'\0' * (-len(out) % 4)
    gltf['buffers'] = [{'byteLength': len(out)}]
    js = json.dumps(gltf, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, 28 + len(js) + len(out)))
        f.write(struct.pack('<II', len(js), 0x4E4F534A) + js)
        f.write(struct.pack('<II', len(out), 0x004E4942) + out)


def transplant_animations(dst, dst_views, src, src_views):
    """give dst the clips of src (bone nodes matched by name) and its clip info"""
    node = {n.get('name'): i for i, n in enumerate(dst['nodes'])}
    views, accessors = {}, {}

    def view(i):
        if i not in views:
            dst['bufferViews'].append({k: v for k, v in src['bufferViews'][i].items() if k not in ('byteOffset', 'byteLength')})
            dst_views.append(src_views[i])
            views[i] = len(dst_views) - 1
        return views[i]

    def accessor(i):
        if i not in accessors:
            dst['accessors'].append({**src['accessors'][i], 'bufferView': view(src['accessors'][i]['bufferView'])})
            accessors[i] = len(dst['accessors']) - 1
        return accessors[i]

    dst['animations'] = [{
        **anim,
        'samplers': [{**s, 'input': accessor(s['input']), 'output': accessor(s['output'])} for s in anim['samplers']],
        'channels': [{**c, 'target': {**c['target'], 'node': node[src['nodes'][c['target']['node']]['name']]}} for c in anim['channels']],
    } for anim in src['animations']]
    dst['scenes'][dst.get('scene', 0)]['extras'] = src['scenes'][src.get('scene', 0)]['extras']


def skinned_meshes_to_root(gltf):
    """skinned mesh nodes ignore their parent transform: keep them at the scene root (glTF validator)"""
    skinned = {i for i, n in enumerate(gltf['nodes']) if 'skin' in n}
    for n in gltf['nodes']:
        kids = [c for c in n.pop('children', []) if c not in skinned]
        if kids:
            n['children'] = kids
    scene = gltf['scenes'][gltf.get('scene', 0)]
    scene['nodes'] += sorted(skinned - set(scene['nodes']))


def shrink_images(gltf, views, size, min_bytes=300_000):
    """re-encode the big images (the Meshy texture, not the small palettes) as JPEG of at most size px"""
    for img in gltf['images']:
        data = views[img['bufferView']]
        if len(data) < min_bytes:
            continue
        im = Image.open(io.BytesIO(data))
        im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        im.convert('RGB').save(buf, 'JPEG', quality=90)
        views[img['bufferView']] = buf.getvalue()
        img['mimeType'] = 'image/jpeg'


# ---------------------------------------------------------------------------
def unpack(path):
    """the .obj of a Meshy OBJ export zip, extracted (flat) into a temporary folder"""
    folder = tempfile.mkdtemp()
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = os.path.basename(info.filename)
            if name.lower().endswith(('.obj', '.mtl', '.png', '.jpg', '.jpeg')):
                with z.open(info) as src, open(os.path.join(folder, name), 'wb') as dst:
                    dst.write(src.read())
    return next(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith('.obj'))


def import_meshy(path, triangles):
    if path.lower().endswith('.zip'):
        path = unpack(path)
    before = set(bpy.context.scene.objects)
    if path.lower().endswith('.obj'):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.context.scene.objects if o not in before]
    parts = [o for o in new if o.type == 'MESH']
    for o in new:
        if o.animation_data:
            o.animation_data_clear()
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    meshy = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in new:
        if o != meshy and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    meshy.name = meshy.data.name = 'PlumberMeshy'
    # Meshy glTF files split every vertex on a UV seam; one vertex per position, or seam copies could
    # end up with different weights and the surface would tear open when it deforms
    bm = bmesh.new()
    bm.from_mesh(meshy.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(meshy.data)
    bm.free()
    tris = sum(len(p.vertices) - 2 for p in meshy.data.polygons)
    if tris > triangles:
        dec = meshy.modifiers.new('decimate', 'DECIMATE')
        dec.ratio = triangles / tris
        bpy.ops.object.modifier_apply(modifier=dec.name)
    meshy.data.shade_smooth()
    print(f'Meshy model: {tris} -> {len(meshy.data.polygons)} triangles')
    return meshy


def meshy_texture(meshy):
    """the base colour image node of the Meshy material, and its pixels (0..255, rows going down)"""
    mat = meshy.data.materials[0]
    node = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')
    img = node.image
    w, h = img.size
    path = bpy.path.abspath(img.filepath)
    if img.packed_file is None and os.path.exists(path):
        px = np.asarray(Image.open(path).convert('RGB'), dtype=np.float64)
    else:  # packed (glTF import): Blender stores rows bottom-up
        px = np.round(np.array(img.pixels[:]).reshape(h, w, img.channels)[::-1, :, :3] * 255)
    return mat, node, px


def main():
    args = sys.argv[1:]
    triangles = 70000
    if '--triangles' in args:
        i = args.index('--triangles')
        triangles = int(args[i + 1])
        del args[i:i + 2]
    meshy_path = os.path.abspath(args[0] if args else MESHY_ZIP)
    out = os.path.abspath(args[1]) if len(args) > 1 else os.path.join(ROOT, 'public', 'round-plumber-meshy.glb')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30
    bpy.ops.import_scene.gltf(filepath=SRC_GLB)
    arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    arm.data.pose_position = 'REST'
    objs = {o.name: o for o in bpy.context.scene.objects if o.type == 'MESH'}
    meshy = import_meshy(meshy_path, triangles)

    # alignment against the procedural body + head (rest pose)
    err = align(meshy, np.concatenate([world_verts(objs[n]) for n in DONORS]))

    # arms away, painted eyes / brows away
    mat, node, tex = meshy_texture(meshy)
    cols = texel(tex, vertex_uvs(meshy))
    co = remove_arms(meshy, tex, cols)
    paint_out_face(meshy, tex, co, cols)
    painted = os.path.join(tempfile.mkdtemp(), 'PlumberMeshy_color.png')
    Image.fromarray(tex.astype(np.uint8)).save(painted)
    node.image = bpy.data.images.load(painted)
    node.image.pack()
    mat.name = 'Plumber_Meshy'
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Metallic'].default_value = 0
    bsdf.inputs['Roughness'].default_value = 0.6
    mat.use_backface_culling = True

    # weight transfer from a joined copy of the donor meshes
    bpy.ops.object.select_all(action='DESELECT')
    copies = []
    for n in DONORS:
        c = objs[n].copy()
        c.data = objs[n].data.copy()
        for m in list(c.modifiers):
            c.modifiers.remove(m)
        bpy.context.collection.objects.link(c)
        copies.append(c)
    for c in copies:
        c.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.object.join()
    donor = bpy.context.view_layer.objects.active
    donor.name = 'WeightDonor'
    transfer_weights(meshy, donor)
    mod = meshy.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
    meshy.parent = arm
    meshy.matrix_parent_inverse = arm.matrix_world.inverted()

    # move eyes, brows and mouth onto the new face surface
    meshy_bvh, donor_bvh = bvh_of(meshy), bvh_of(donor)
    bones = arm.data.bones
    head = lambda n: arm.matrix_world @ bones[n].head_local
    fwd = Vector((0, -1, 0))  # glTF +Z (the character's front) is Blender -Y
    for side, sx in (('L', 1), ('R', -1)):
        c = head(f'Eye_{side}')
        axis = Vector((0.12 * sx, -1, 0.04)).normalized()
        d = offset_along(meshy_bvh, donor_bvh, c, axis)
        k = shift_vertices(objs['PlumberEyes'], lambda p, g: (p - c).length < 0.115, axis * d)
        print(f'eye {side}: moved {k} vertices by {d * 1000:.1f} mm')
        b0 = (head(f'BrowIn_{side}') + head(f'BrowOut_{side}')) / 2
        d = offset_along(meshy_bvh, donor_bvh, b0 + fwd * -0.03, fwd)
        k = shift_vertices(objs['PlumberFace'], lambda p, g, s=side: any(n.startswith('Brow') and n.endswith(s) for n in g), fwd * d)
        print(f'brow {side}: moved {k} vertices by {d * 1000:.1f} mm')
    m0 = head('MouthUpper')
    d = offset_along(meshy_bvh, donor_bvh, m0, fwd)
    k = shift_vertices(objs['PlumberFace'], lambda p, g: any(n.startswith('Mouth') for n in g), fwd * d)
    print(f'mouth: moved {k} vertices by {d * 1000:.1f} mm')

    # drop the replaced procedural meshes and the helper
    for n in DONORS:
        bpy.data.objects.remove(objs[n], do_unlink=True)
    bpy.data.objects.remove(donor, do_unlink=True)
    arm.data.pose_position = 'POSE'

    bpy.ops.object.select_all(action='DESELECT')
    keep = [arm, meshy] + [objs[n] for n in OVERLAYS if n in objs]
    for o in keep:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    print(f'PlumberMeshy: {len(meshy.data.polygons)} triangles, {len(meshy.data.vertices)} vertices')
    tmp = out + '.blender.glb'
    bpy.ops.export_scene.gltf(
        filepath=tmp, export_format='GLB', use_selection=True, export_animations=False,
        export_skins=True, export_all_influences=False, export_yup=True, export_apply=False,
    )
    gltf, views = read_glb(tmp)
    os.remove(tmp)
    transplant_animations(gltf, views, *read_glb(SRC_GLB))
    skinned_meshes_to_root(gltf)
    shrink_images(gltf, views, TEXTURE)
    write_glb(out, gltf, views)
    print(f'wrote {out} (alignment error {err * 1000:.1f} mm)')


if __name__ == '__main__':
    main()
