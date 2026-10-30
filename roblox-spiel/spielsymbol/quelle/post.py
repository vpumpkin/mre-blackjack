# FINAL icon - 2D compositing (system Python: PIL + numpy).
# Usage: python3 -I post.py RENDER.png OUT.png
# Reads RENDER.png (RGBA beauty), RENDER_id.png and RENDER_meta.json written by scene.py.
# Works at the render's own resolution (all sizes are given in 512-px units and scaled by k).
# Optional overrides: POST_CFG='{"bg": "midviolet", "tail_angle": 40, ...}' (defaults are the final look)
import sys, os, json, math
import numpy as np
from PIL import Image, ImageDraw

RENDER, OUTP = sys.argv[1], sys.argv[2]
CFG = json.loads(os.environ.get('POST_CFG', '{}'))
base = os.path.splitext(RENDER)[0]
beauty = Image.open(RENDER).convert('RGBA')
S = beauty.size[0]
k = S / 512.0
SS = 3                      # supersampling for vector-drawn FX
rng = np.random.default_rng(int(CFG.get('seed', 11)))

idimg = Image.open(base + '_id.png').convert('RGBA')
if idimg.size != (S, S):
    idimg = idimg.resize((S, S), Image.LANCZOS)
meta = json.load(open(base + '_meta.json'))
HC = np.array(meta['head']['center'], np.float32) * k
HR = meta['head']['radius'] * k
CC = np.array(meta['cross']['center'], np.float32) * k
TC = np.array(meta['tetra']['center'], np.float32) * k

idn = np.asarray(idimg).astype(np.float32) / 255.0
ida = idn[..., 3]
R_, G_, B_ = idn[..., 0], idn[..., 1], idn[..., 2]
M_CUBE = np.clip(R_ * B_ * ida, 0, 1)
M_SPH = np.clip(R_ * (1 - B_) * ida, 0, 1)
M_COMET = np.clip(M_SPH + M_CUBE, 0, 1)
M_CROSS = np.clip(G_ * (1 - B_) * (1 - R_) * ida, 0, 1)
M_TETRA = np.clip(B_ * (1 - R_) * (1 - G_) * ida, 0, 1)
M_DROP = np.clip(G_ * B_ * ida, 0, 1)
M_ALL = ida

yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) + 0.5


# ------------------------------------------------------------------ helpers
def gblur(img, sigma):
    """gaussian blur via FFT (2D or HxWxC)"""
    if sigma <= 0.3:
        return img
    squeeze = img.ndim == 2
    x = img[..., None] if squeeze else img
    pad = int(3 * sigma) + 2
    P = np.pad(x, ((pad, pad), (pad, pad), (0, 0)), mode='edge')
    Hp, Wp = P.shape[:2]
    fy = np.fft.fftfreq(Hp)[:, None]
    fx = np.fft.rfftfreq(Wp)[None, :]
    G = np.exp(-2 * (math.pi ** 2) * sigma ** 2 * (fx ** 2 + fy ** 2))
    out = np.fft.irfft2(np.fft.rfft2(P, axes=(0, 1)) * G[..., None], s=(Hp, Wp), axes=(0, 1))
    out = out[pad:-pad, pad:-pad].astype(np.float32)
    return out[..., 0] if squeeze else out


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def screen(a, b):
    return 1 - (1 - a) * (1 - b)


def over(dst, rgb, a):
    a = a[..., None] if a.ndim == 2 else a
    return dst * (1 - a) + np.asarray(rgb, np.float32) * a


def lut(t, stops):
    t = np.clip(t, 0, 1)
    ts = np.array([s[0] for s in stops], np.float32)
    cs = np.array([s[1] for s in stops], np.float32) / 255.0
    out = np.zeros(t.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, ts, cs[:, c])
    return out


def grow(m, r):
    """soft morphological dilation by ~r px (blur + low threshold)"""
    b = gblur(m, r * 0.5)
    return np.maximum(m, smoothstep(0.015, 0.06, b))


def noise1(n, seed, smooth_len):
    """smooth 1D noise sampled on n points, features about smooth_len samples long, range ~[-1, 1]"""
    g = np.random.default_rng(seed).standard_normal(n + 64).astype(np.float32)
    x = np.arange(n + 64, dtype=np.float32)
    kern = np.exp(-0.5 * ((np.arange(-3 * smooth_len, 3 * smooth_len + 1)) / smooth_len) ** 2)
    s = np.convolve(g, kern / kern.sum(), mode='same')
    s = s / (np.abs(s).max() + 1e-6)
    return s[32:32 + n]


def sample1(arr, t):
    """linear interpolation of a 1D array at float indices t (clamped)"""
    t = np.clip(t, 0, len(arr) - 1.001)
    i = np.floor(t).astype(int)
    f = t - i
    return arr[i] * (1 - f) + arr[i + 1] * f


def canvas():
    im = Image.new('L', (S * SS, S * SS), 0)
    return im, ImageDraw.Draw(im)


def finish(im):
    return np.asarray(im.resize((S, S), Image.LANCZOS)).astype(np.float32) / 255.0


def taper_poly(d, p0, p1, w0, w1, fill=255):
    """quad from p0 (half width w0) to p1 (half width w1), in px (drawn supersampled)"""
    p0 = np.asarray(p0, np.float32); p1 = np.asarray(p1, np.float32)
    v = p1 - p0
    L = float(np.hypot(*v)) or 1.0
    n = np.array([-v[1], v[0]], np.float32) / L
    pts = [p0 + n * w0, p1 + n * w1, p1 - n * w1, p0 - n * w0]
    d.polygon([(float(q[0]) * SS, float(q[1]) * SS) for q in pts], fill=fill)
    if w0 > 0.6:
        d.ellipse(((p0[0] - w0) * SS, (p0[1] - w0) * SS, (p0[0] + w0) * SS, (p0[1] + w0) * SS), fill=fill)


# ------------------------------------------------------------------ motion geometry
ang = math.radians(CFG.get('tail_angle', 40.0))           # tail direction, degrees above +x (screen up = -y)
D = np.array([math.cos(ang), -math.sin(ang)], np.float32)  # unit vector from the head toward the tail
NRM = np.array([-D[1], D[0]], np.float32)
U = (xx - HC[0]) * D[0] + (yy - HC[1]) * D[1]             # along the tail (px)
V = (xx - HC[0]) * NRM[0] + (yy - HC[1]) * NRM[1]         # across the tail (px)
R = np.hypot(xx - HC[0], yy - HC[1])

# contact point: where the comet and the Kreuz touch (fallback: scene's estimate)
touch = grow(M_COMET, 5 * k) * grow(M_CROSS, 5 * k)
if touch.sum() > 4:
    w_ = touch / touch.sum()
    IMP = np.array([(xx * w_).sum(), (yy * w_).sum()], np.float32)
else:
    IMP = np.array(meta['impact'], np.float32) * k
IMP = IMP + np.array(CFG.get('imp_offset', [0, 0]), np.float32) * k

# ------------------------------------------------------------------ background: hot halo around the comet
BG_STOPS = {
    'magenta': [(0.00, (214, 112, 236)), (0.20, (178, 66, 222)), (0.36, (124, 38, 196)), (0.58, (68, 20, 150)),
                (0.82, (30, 10, 88)), (1.10, (10, 4, 36))],
    'violet': [(0.00, (225, 160, 255)), (0.20, (170, 80, 240)), (0.34, (120, 48, 214)), (0.55, (66, 24, 160)),
               (0.80, (30, 12, 92)), (1.10, (10, 5, 38))],
    'indigo': [(0.00, (120, 92, 255)), (0.22, (84, 62, 220)), (0.38, (56, 38, 176)), (0.60, (32, 20, 120)),
               (0.85, (16, 9, 66)), (1.10, (6, 4, 28))],
    'deepviolet': [(0.00, (150, 70, 240)), (0.22, (104, 40, 200)), (0.38, (70, 24, 160)), (0.60, (40, 13, 110)),
                   (0.85, (18, 6, 58)), (1.10, (7, 3, 26))],
    'midviolet': [(0.00, (172, 84, 244)), (0.22, (124, 50, 214)), (0.38, (88, 32, 178)), (0.60, (52, 17, 126)),
                  (0.85, (24, 8, 68)), (1.10, (8, 4, 28))],
    'brightviolet': [(0.00, (196, 110, 255)), (0.22, (150, 70, 236)), (0.38, (112, 46, 206)), (0.60, (70, 26, 156)),
                     (0.85, (34, 12, 90)), (1.10, (12, 5, 36))],
    'navy': [(0.00, (70, 96, 230)), (0.22, (44, 64, 190)), (0.38, (28, 40, 140)), (0.60, (16, 22, 92)),
             (0.85, (8, 10, 50)), (1.10, (3, 4, 22))],
}
GC = HC + D * HR * CFG.get('glow_back', 0.35)
RG = np.hypot(xx - GC[0], (yy - GC[1]) * 1.0) / S
bg = lut(RG / 1.10, [(s[0] / 1.10, s[1]) for s in BG_STOPS[CFG.get('bg', 'brightviolet')]])
theta = np.arctan2(yy - GC[1], xx - GC[0])
rays = (0.5 + 0.5 * np.cos(theta * CFG.get('nrays', 14) + 0.4)) ** 6
rays = rays * smoothstep(0.18, 0.32, RG) * (1 - smoothstep(0.45, 0.95, RG))
bg = screen(bg, rays[..., None] * np.array(CFG.get('ray_rgb', [0.24, 0.12, 0.36]), np.float32) * CFG.get('rays', 1.25))

# arena floor: dark disc with a gold rim, seen in perspective along the bottom
floor = np.zeros((S, S), np.float32)
if CFG.get('arena', 1):
    fcx, fcy, fax, fay = S * 0.5, S * CFG.get('floor_cy', 1.40), S * 1.02, S * 0.56
    ell = np.sqrt(((xx - fcx) / fax) ** 2 + ((yy - fcy) / fay) ** 2)
    floor = smoothstep(1.0 + 1.5 / S, 1.0 - 1.5 / S, ell)
    floorc = lut(np.clip((yy / S - 0.78) / 0.22, 0, 1), [(0, tuple(CFG.get('floor_top', (40, 18, 96)))), (1, tuple(CFG.get('floor_bot', (12, 6, 36))))])
    bg = bg * (1 - floor[..., None]) + floorc * floor[..., None]
    # light from the comet pooling on the floor (cyan hot spot, magenta wash)
    fx0 = IMP[0] + 0.15 * HR
    wash = np.exp(-(((xx - fx0) / (S * 0.36)) ** 2 + ((yy - S * 0.93) / (S * 0.12)) ** 2))
    hot = np.exp(-(((xx - fx0) / (S * 0.14)) ** 2 + ((yy - S * 0.90) / (S * 0.04)) ** 2))
    bg = bg + (wash * floor)[..., None] * np.array([0.40, 0.12, 0.55], np.float32) * CFG.get('floor_glow', 1.0)
    bg = bg + (hot * floor)[..., None] * np.array([0.25, 0.60, 0.80], np.float32) * CFG.get('floor_glow', 1.0)
    rim = np.exp(-((ell - 1.0) * S / (2.2 * k)) ** 2)
    rim_glow = np.exp(-((ell - 1.0) * S / (9.0 * k)) ** 2)
    gold = np.array([1.0, 0.78, 0.30], np.float32)
    bg = screen(bg, (rim * 0.95)[..., None] * gold + (rim_glow * 0.35)[..., None] * np.array([1.0, 0.55, 0.15], np.float32))
bg = np.clip(bg, 0, 1)
comp = bg.copy()

# speed lines parallel to the motion (background only, faint)
im, d = canvas()
for i in range(int(CFG.get('nlines', 16))):
    for _ in range(40):
        u0 = rng.uniform(-0.6, 2.8) * HR
        v0 = rng.uniform(-3.2, 3.2) * HR
        if abs(v0) > 1.55 * HR:
            break
    p0 = HC + D * u0 + NRM * v0
    L_ = rng.uniform(60, 150) * k
    p1 = p0 + D * L_
    if p0[1] > S * 0.80:
        continue
    taper_poly(d, p0, p1, rng.uniform(0.8, 1.8) * k, 0.0, fill=int(rng.uniform(90, 200)))
lines = finish(im) * (1 - floor)
comp = screen(comp, lines[..., None] * np.array([0.9, 0.85, 1.0], np.float32) * CFG.get('lines_gain', 0.35))

# ------------------------------------------------------------------ plasma plume: vector-style flame (one outline, nested bands)
PS = CFG.get('plume_scale', 1.0)
W0 = CFG.get('cap_r', 1.22) * HR * PS                 # radius of the plasma sheath around the Kugel
LT = CFG.get('tail_len', 5.0) * HR * PS               # tail length behind the head centre
PW = CFG.get('plume_w', 1.3)


def licks(u, seed, n, u_lo, u_hi):
    """backward-swept flame licks along one edge: sharp rise, long trailing decay (in px of extra width)"""
    r = np.random.default_rng(seed)
    e = np.zeros_like(u)
    pos = np.sort(r.uniform(u_lo, u_hi, n))
    for ui in pos:
        A = r.uniform(0.30, 0.62) * HR * PS * CFG.get('lick_amp', 1.0)
        Ll = r.uniform(0.75, 1.45) * HR * PS
        x = (u - ui) / Ll
        rise = smoothstep(-0.22, 0.0, x) * (x < 0)
        fall = np.clip(1 - x, 0, 1) ** 1.6 * (x >= 0)
        e = np.maximum(e, A * (rise + fall) * smoothstep(0, 1.2 * HR, ui))
    return e


uc = np.clip(U / LT, 0, 1)
w_body = W0 * (1 + (PW - 1) * smoothstep(0, 1.6 * HR * PS, U)) * (1 - uc) ** CFG.get('taper', 0.9)
e_pos = licks(U, 5, int(CFG.get('nlicks', 4)), 0.5 * HR * PS, 3.6 * HR * PS)
e_neg = licks(U, 9, int(CFG.get('nlicks', 4)), 0.6 * HR * PS, 3.6 * HR * PS)
w_edge = w_body + np.where(V >= 0, e_pos, e_neg) * (1 - uc) ** 0.5
w_cap = np.sqrt(np.clip(W0 ** 2 - U ** 2, 0, None))
w_out = np.where(U < 0, w_cap, w_edge)
w_out = np.where(U > LT, 0.0, w_out)
AV = np.abs(V)
FE = 1.2 * k                                          # crisp anti-aliased band edges
BANDS = CFG.get('bands', [  # fraction of the outline width, colour, fade-in start/end (HR along the tail)
    (1.00, (255, 64, 192), -9, -8),
    (0.88, (170, 70, 255), -9, -8),
    (0.80, (66, 132, 255), -9, -8),
    # inner bands stay saturated cyan: near-white cores clipped the visible tail (top-right corner)
    # to flat grey-white, the largest bright area in the frame, brighter than the impact
    (0.72, (30, 190, 255), 0.0, 0.7),
    (0.48, (60, 222, 255), 1.3, 2.0),
    (0.26, (150, 242, 255), 1.6, 2.3),
])
plume_rgb = np.zeros((S, S, 3), np.float32)
plume_a = np.zeros((S, S), np.float32)
for (fr, col, f0, f1) in BANDS:
    wb = w_out * fr
    m = smoothstep(wb + FE, wb - FE, AV) * (w_out > 0.5)
    m = m * smoothstep(f0 * HR * PS, f1 * HR * PS, U)
    plume_rgb = over(plume_rgb, np.array(col, np.float32) / 255.0, m)      # premultiplied accumulation
    plume_a = m + plume_a * (1 - m)
# the far tail fades out instead of ending in a hard point
fade_t = 1 - smoothstep(0.55, 1.0, uc) * 0.85
plume_rgb = plume_rgb * fade_t[..., None]
plume_a = plume_a * fade_t
# a few long, smooth speed streaks inside the core
im, d = canvas()
for (v0, u0, L_, w_) in [(-0.30, 1.5, 2.2, 2.0), (0.06, 1.8, 2.6, 2.4), (0.36, 1.4, 2.0, 1.7)]:
    p0 = HC + D * u0 * HR * PS + NRM * v0 * HR * PS
    taper_poly(d, p0, p0 + D * L_ * HR * PS, w_ * k, 0.0)
streaks = gblur(finish(im), 0.6 * k) * (plume_a > 0.5)
plume_rgb = screen(plume_rgb, streaks[..., None] * 0.70)
plume = plume_a
glow_p = gblur(plume_a, 12 * k)
comp = comp * (1 - CFG.get('sky_deep', 0.48) * np.clip(glow_p * 1.5, 0, 1))[..., None]      # deepen the sky right around the plume
PLASMA = [(0.00, (0, 0, 0)), (0.10, (60, 0, 110)), (0.25, (150, 20, 200)), (0.40, (200, 60, 255)),
          (0.55, (90, 120, 255)), (0.68, (40, 200, 255)), (0.82, (150, 245, 255)), (0.93, (225, 255, 255)),
          (1.00, (255, 255, 255))]
TG = CFG.get('tail_gain', 1.0)
comp = comp * (1 - plume_a * TG)[..., None] + plume_rgb * TG          # premultiplied over
comp = screen(comp, gblur(plume_rgb, 14 * k) * CFG.get('plume_glow', 0.3))

# corona: a hot rim hugging the comet's silhouette, strongest on the trailing side, plus a bow shock in front
trail_side = smoothstep(-0.6, 0.9, ((xx - HC[0]) * D[0] + (yy - HC[1]) * D[1]) / HR)
ring = np.clip(gblur(M_COMET, 6 * k) * 2.2 - M_COMET, 0, 1)
corona = ring * (0.35 + 0.75 * trail_side) * CFG.get('corona', 1.0)
comp = screen(comp, lut(np.clip(0.62 + 0.38 * corona, 0, 1), PLASMA) * np.clip(corona * 1.3, 0, 1)[..., None])
bow_ring = np.clip(grow(M_SPH, 7 * k) - M_COMET, 0, 1) * (1 - M_ALL)
lead = smoothstep(0.1, 0.9, -((xx - HC[0]) * D[0] + (yy - HC[1]) * D[1]) / HR)
bow = gblur(bow_ring, 1.6 * k) * lead * CFG.get('bow', 0.9)
comp = screen(comp, np.clip(bow, 0, 1)[..., None] * np.array([0.55, 0.95, 1.0], np.float32))

# ------------------------------------------------------------------ characters
rgba = np.asarray(beauty).astype(np.float32) / 255.0
ca = rgba[..., 3:4]
INK = np.array([0.05, 0.02, 0.12], np.float32)
# outer outline around every character (helps at 64 px)
ol_all = np.clip(grow(M_ALL, CFG.get('outline', 4.2) * k) - M_ALL, 0, 1)
comp = over(comp, INK, ol_all)
comp = comp * (1 - ca) + rgba[..., :3] * ca
# seams where the comet passes in front of the Kreuz / where the sphere sits on the cube
seam_cc = np.clip(grow(M_COMET, 3.2 * k) - M_COMET, 0, 1) * M_CROSS
comp = over(comp, INK, seam_cc * 0.9)
seam_sc = np.clip(grow(M_SPH, 2.4 * k) - M_SPH, 0, 1) * M_CUBE
comp = over(comp, INK, seam_sc * 0.75)
seam_ct = np.clip(grow(M_CROSS + M_COMET, 2.5 * k) - M_CROSS - M_COMET, 0, 1) * M_TETRA
comp = over(comp, INK, np.clip(seam_ct, 0, 1) * 0.8)

# fusion weld: a thin cyan energy line where Kugel and Wuerfel are welded together
if CFG.get('weld', 1):
    weld = np.clip(grow(M_SPH, 5.5 * k) - grow(M_SPH, 2.6 * k), 0, 1) * M_CUBE
    weld = gblur(weld, 0.8 * k)
    comp = screen(comp, np.clip(weld * 1.3, 0, 1)[..., None] * np.array([0.55, 0.95, 1.0], np.float32) * CFG.get('weld', 1))

# plasma licking around the comet's trailing edge (in front, thin)
edge = np.clip(M_SPH - np.clip(gblur(M_SPH, 3 * k) * 2 - 1, 0, 1), 0, 1) * (1 - M_CUBE)
lick = gblur(edge, 1.5 * k) * smoothstep(0.2, 1.0, ((xx - HC[0]) * D[0] + (yy - HC[1]) * D[1]) / HR) * 0.8
comp = screen(comp, lut(np.clip(lick, 0, 1) * 0.92, PLASMA))

# cool contact shadow where the comet overlaps the near-white Kreuz: gives the white flash local contrast
occ = np.clip(gblur(M_COMET, CFG.get('shade_r', 16) * k) * 2.2, 0, 1) * M_CROSS * (1 - M_COMET) * CFG.get('contact_shade', 0.9)
comp = comp * (1 - occ[..., None] * (1 - np.array([0.58, 0.62, 0.95], np.float32)))

# ------------------------------------------------------------------ impact at the contact point
mot = -D                                             # comet's direction of motion
away = (IMP - HC) / (np.linalg.norm(IMP - HC) + 1e-6)  # from the comet centre out through the contact
FACE_KEEP = np.clip(M_SPH * smoothstep(0.75 * HR, 0.35 * HR, R) + smoothstep(0.80, 0.45, np.hypot(xx - CC[0], yy - CC[1]) / (meta['cross']['size'] * k * 0.5)), 0, 1)

# comic impact lines radiating from the contact, only on the open side (away from the comet's face)
im, d = canvas()
base_a = math.atan2(away[1], away[0])
side_a = [math.atan2(-NRM[1], -NRM[0]), math.atan2(NRM[1], NRM[0])]   # the two sideways directions
fan = []
# only into the open space below the contact (between the comet's underside and the Kreuz's arm)
for da in np.linspace(-0.45, 0.45, int(CFG.get('nimpact', 3))):
    fan.append(side_a[1] + da)
for j, a0 in enumerate(fan):
    da = 0.0
    a = a0 + rng.uniform(-0.06, 0.06)
    u = np.array([math.cos(a), math.sin(a)], np.float32)
    r0 = rng.uniform(26, 34) * k
    r1 = r0 + rng.uniform(34, 58) * k * (1.0 - 0.25 * abs(da))
    taper_poly(d, IMP + u * r0, IMP + u * r1, rng.uniform(3.2, 4.6) * k, 0.4 * k)
hit_lines = finish(im) * (1 - FACE_KEEP) * (1 - M_ALL)   # background only: on a body they read as tape

# star flare (4 long + 4 short spikes)
im, d = canvas()
rot = base_a + math.pi / 2 + math.radians(CFG.get('star_rot', 0))
for j in range(8):
    a = rot + j * math.pi / 4
    L_ = (44 if j % 4 == 0 else (16 if j % 4 == 2 else 22)) * k * CFG.get('star', 1.15)
    u = np.array([math.cos(a), math.sin(a)], np.float32)
    taper_poly(d, IMP, IMP + u * L_, (3.4 if j % 2 == 0 else 2.4) * k, 0.0)
star = gblur(finish(im), 0.6 * k) * (1 - 0.85 * FACE_KEEP)

rr = np.hypot(xx - IMP[0], yy - IMP[1])
core_f = np.exp(-0.5 * (rr / (8.5 * k)) ** 2)
glow_f = np.exp(-0.5 * (rr / (CFG.get('glow_sigma', 22.0) * k)) ** 2) * (1 - 0.7 * FACE_KEEP)   # tight: one crisp hot spot
big_f = np.exp(-0.5 * (rr / (110.0 * k)) ** 2) * (1 - M_ALL)
warm = np.array([1.0, 0.86, 0.52], np.float32)
comp = screen(comp, np.clip(big_f * CFG.get('impact_light', 0.30), 0, 1)[..., None] * np.array([1.0, 0.75, 0.55], np.float32))
comp = screen(comp, np.clip(glow_f * CFG.get('glow_gain', 0.6), 0, 1)[..., None] * warm)
comp = screen(comp, np.clip(hit_lines * 0.95, 0, 1)[..., None] * np.array([1.0, 0.97, 0.85], np.float32))
comp = screen(comp, np.clip(star * 1.0 + core_f * 1.2, 0, 1)[..., None] * np.array([1.0, 0.99, 0.95], np.float32))

# debris: Kreuz chips and hot sparks flung out of the contact, plus embers in the plume
spk = Image.new('RGB', (S * SS, S * SS), (0, 0, 0))
ds = ImageDraw.Draw(spk)
SPARK_COLS = [(255, 240, 200), (255, 196, 80), (255, 150, 40), (255, 210, 120)]
for i in range(int(CFG.get('nsparks', 12))):
    a = side_a[1] + rng.uniform(-0.8, 0.8)
    u = np.array([math.cos(a), math.sin(a)], np.float32)
    r0 = rng.uniform(22, 70) * k
    p0 = IMP + u * r0
    L_ = rng.uniform(16, 36) * k * CFG.get('spark_len', 1.2)
    col = SPARK_COLS[rng.integers(len(SPARK_COLS))]
    w0 = rng.uniform(1.8, 3.0) * k
    pts0, pts1 = p0, p0 + u * L_
    vv = pts1 - pts0
    n_ = np.array([-vv[1], vv[0]]) / (np.hypot(*vv) + 1e-6)
    poly = [pts0 + n_ * w0 * 0.3, pts1 + n_ * w0, pts1 - n_ * w0, pts0 - n_ * w0 * 0.3]
    ds.polygon([(float(q[0]) * SS, float(q[1]) * SS) for q in poly], fill=col)
for i in range(int(CFG.get('nembers', 10))):
    u0 = rng.uniform(1.3, 3.2) * HR
    v0 = rng.normal(0, 0.55) * HR
    p0 = HC + D * u0 + NRM * v0
    L_ = rng.uniform(10, 22) * k
    col = SPARK_COLS[rng.integers(len(SPARK_COLS))]
    w0 = rng.uniform(1.2, 2.2) * k
    ds.line([(float(p0[0]) * SS, float(p0[1]) * SS), (float(p0[0] + D[0] * L_) * SS, float(p0[1] + D[1] * L_) * SS)],
            fill=col, width=max(1, int(w0 * SS)))
spk = np.asarray(spk.resize((S, S), Image.LANCZOS)).astype(np.float32) / 255.0
spk = spk * (1 - FACE_KEEP)[..., None] * (1 - M_TETRA)[..., None] * (1 - M_COMET)[..., None] * (1 - M_DROP)[..., None]
spk = spk * (1 - M_CROSS)[..., None]          # no sparks painted across the Kreuz's arm (read as scratches)
comp = screen(comp, np.clip(spk + gblur(spk, 2.5 * k) * 1.2, 0, 1))

# ------------------------------------------------------------------ bloom
lum = comp @ np.array([0.3, 0.55, 0.15], np.float32)
bright = comp * smoothstep(0.70, 1.0, lum)[..., None] * (1 - 0.9 * M_ALL)[..., None]
bloom = gblur(bright, 4 * k) * 0.45 + gblur(bright, 14 * k) * 0.35 + gblur(bright, 36 * k) * 0.25
comp = screen(comp, np.clip(bloom * CFG.get('bloom', 1.0), 0, 1))

# ------------------------------------------------------------------ grade
cxy = np.hypot((xx - S / 2) / S, (yy - S / 2) / S)
vig = 1 - CFG.get('vig', 0.22) * smoothstep(0.38, 0.74, cxy)
comp = comp * vig[..., None]
g = comp @ np.array([0.299, 0.587, 0.114], np.float32)
comp = np.clip(g[..., None] + (comp - g[..., None]) * CFG.get('sat', 1.22), 0, 1)
comp = np.clip((comp - 0.5) * CFG.get('contrast', 1.05) + 0.5, 0, 1)
# soft highlight shoulder: whites top out around 245 except the impact core
cap = CFG.get('cap', 0.955)
hot_ok = np.clip(core_f * 1.5 + star, 0, 1)[..., None]
# compress only the white component (min channel) so near-whites keep shading but saturated colours keep their punch
knee = 0.80
wmin = comp.min(-1, keepdims=True)
over_k = np.clip(wmin - knee, 0, None)
w_soft = np.where(wmin > knee, knee + (cap - knee) * (1 - np.exp(-over_k / (cap - knee))), wmin)
comp_soft = np.clip(comp - wmin + w_soft, 0, 1)
comp = comp_soft * (1 - hot_ok) + comp * hot_ok

out = Image.fromarray((np.clip(comp, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB')
out.save(OUTP)
json.dump({'impact': [float(IMP[0] / k), float(IMP[1] / k)]}, open(os.path.splitext(OUTP)[0] + '_post.json', 'w'))
print('wrote', OUTP)
