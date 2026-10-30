# Face decals for the final Fusion Comet icon. Run with the system Python: python3 -I faces.py OUTDIR
# Each face is drawn in object units (x right, z up) and saved as
#   <name>_col.png  RGBA colour decal (projected along the object's -Y axis in Blender)
#   <name>_h.png    grayscale height for bump (128 = flat)
# The texture covers x,z in [-S, S] of the object's local space.
import sys, math, os
from PIL import Image, ImageDraw, ImageFilter, ImageChops

OUT = sys.argv[1] if len(sys.argv) > 1 else 'tex'
os.makedirs(OUT, exist_ok=True)
N = 2048          # drawing resolution (downsampled to 1024 for anti-aliasing)
FINAL = 1024

INK = (14, 10, 26)          # near-black with a hint of violet
WHITE = (255, 255, 255)
EYEW = (250, 250, 255)
MOUTH_IN = (62, 6, 30)
TONGUE = (238, 72, 112)


class Face:
    def __init__(self, S):
        self.S = S
        self.col = Image.new('RGBA', (N, N), (0, 0, 0, 0))
        self.h = Image.new('L', (N, N), 128)

    def p(self, x, z):
        return ((x / self.S * 0.5 + 0.5) * N, (0.5 - z / self.S * 0.5) * N)

    def r(self, d):
        return d / self.S * 0.5 * N

    def mask(self):
        return Image.new('L', (N, N), 0)

    def ellipse(self, m, cx, cz, rx, rz, fill=255):
        x0, y0 = self.p(cx - rx, cz + rz)
        x1, y1 = self.p(cx + rx, cz - rz)
        ImageDraw.Draw(m).ellipse((x0, y0, x1, y1), fill=fill)

    def poly(self, m, pts, fill=255):
        ImageDraw.Draw(m).polygon([self.p(*q) for q in pts], fill=fill)

    def bar(self, m, a, b, t, fill=255):
        """thick line with round caps from a to b, thickness t (object units)"""
        d = ImageDraw.Draw(m)
        pa, pb = self.p(*a), self.p(*b)
        w = self.r(t)
        d.line((pa, pb), fill=fill, width=int(round(w)))
        for q in (pa, pb):
            d.ellipse((q[0] - w / 2, q[1] - w / 2, q[0] + w / 2, q[1] + w / 2), fill=fill)

    def tapered(self, m, pts, t0, t1, fill=255, n=48):
        """smooth stroke along a quadratic Bezier through 3 control points (or a straight
        segment for 2), thickness going from t0 to t1, round caps"""
        if len(pts) == 2:
            pts = [pts[0], ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2), pts[1]]
        (ax, az), (bx, bz), (cx, cz) = pts
        d = ImageDraw.Draw(m)
        samples = []
        for i in range(n + 1):
            t = i / n
            x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * bx + t * t * cx
            z = (1 - t) ** 2 * az + 2 * (1 - t) * t * bz + t * t * cz
            samples.append((self.p(x, z), self.r(t0 + (t1 - t0) * t) / 2))
        for (pa, ra), (pb, rb) in zip(samples[:-1], samples[1:]):
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            L = math.hypot(dx, dy) or 1.0
            ux, uy = dx / L, dy / L
            nx, ny = -uy, ux
            # overlap each segment by 1.5 px on both ends so neighbouring quads leave no hairline gaps
            pa = (pa[0] - ux * 1.5, pa[1] - uy * 1.5); pb = (pb[0] + ux * 1.5, pb[1] + uy * 1.5)
            d.polygon([(pa[0] + nx * ra, pa[1] + ny * ra), (pb[0] + nx * rb, pb[1] + ny * rb),
                       (pb[0] - nx * rb, pb[1] - ny * rb), (pa[0] - nx * ra, pa[1] - ny * ra)], fill=fill)
        for (q, rq) in samples:          # round joints at every sample: watertight stroke
            d.ellipse((q[0] - rq, q[1] - rq, q[0] + rq, q[1] + rq), fill=fill)

    def curve_bar(self, m, pts, t, fill=255):
        for a, b in zip(pts[:-1], pts[1:]):
            self.bar(m, a, b, t, fill)

    def dilate(self, m, t):
        """grow a mask by t object units (blur + threshold, fast and smooth)"""
        rad = self.r(t)
        b = m.filter(ImageFilter.GaussianBlur(rad * 0.5))
        return b.point(lambda v: 255 if v > 6 else 0).filter(ImageFilter.GaussianBlur(1.2))

    def paint(self, m, rgb):
        layer = Image.new('RGBA', (N, N), (*rgb, 255))
        layer.putalpha(m)
        self.col = Image.alpha_composite(self.col, layer)

    def bump(self, m, amount, blur_t=0.04):
        b = m.filter(ImageFilter.GaussianBlur(self.r(blur_t)))
        base = self.h
        if amount >= 0:
            self.h = ImageChops.add(base, b.point(lambda v: v * amount / 255))
        else:
            self.h = ImageChops.subtract(base, b.point(lambda v: v * (-amount) / 255))

    def save(self, name):
        col = self.col.resize((FINAL, FINAL), Image.LANCZOS)
        h = self.h.filter(ImageFilter.GaussianBlur(3)).resize((FINAL, FINAL), Image.LANCZOS)
        col.save(os.path.join(OUT, name + '_col.png'))
        h.save(os.path.join(OUT, name + '_h.png'))


def intersect(a, b):
    return ImageChops.multiply(a, b)


def subtract(a, b):
    return ImageChops.subtract(a, b)


def halfplane(face, p0, p1, below=True):
    """mask of everything below (smaller z than) the infinite line through p0 and p1"""
    m = face.mask()
    (x0, z0), (x1, z1) = p0, p1
    k = (z1 - z0) / (x1 - x0)
    X = 10 * face.S
    zl, zr = z0 + k * (-X - x0), z0 + k * (X - x0)
    far = -100 * face.S if below else 100 * face.S
    face.poly(m, [(-X, zl), (X, zr), (X, far), (-X, far)])
    return m


def grin_points(x0, x1, zc0, zc1, sag, tilt=0.0, n=40):
    """curve from (x0,zc0) to (x1,zc1) sagging down by sag in the middle"""
    pts = []
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        z = zc0 + (zc1 - zc0) * t - sag * math.sin(math.pi * t) + tilt * (t - 0.5)
        pts.append((x, z))
    return pts


def arc(cx, cz, rx, rz, a0, a1, n=24):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cz + rz * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


# ---------------------------------------------------------------- comet (Kugel): fierce clenched grin
def comet_face(look=(-0.05, -0.065)):
    f = Face(1.0)
    for sgn in (-1, 1):
        cx, cz = 0.30 * sgn, 0.215
        eye = f.mask(); f.ellipse(eye, cx, cz, 0.21, 0.25)
        # angry cut: brow line from outer-high to inner-low
        outer, inner = (0.66 * sgn, 0.56), (0.06 * sgn, 0.305)
        cut = halfplane(f, outer, inner, below=True)
        eye_c = intersect(eye, cut)
        f.paint(f.dilate(eye_c, 0.05), INK)
        f.paint(eye_c, EYEW)
        f.bump(eye_c, 70)
        pup = f.mask(); f.ellipse(pup, cx + look[0], cz + look[1], 0.118, 0.128)
        f.paint(intersect(pup, eye_c), INK)
        hl = f.mask(); f.ellipse(hl, cx + look[0] - 0.045, cz + look[1] + 0.05, 0.056, 0.056)
        f.paint(intersect(hl, eye_c), WHITE)
        hl2 = f.mask(); f.ellipse(hl2, cx + look[0] + 0.042, cz + look[1] - 0.047, 0.024, 0.024)
        f.paint(intersect(hl2, eye_c), WHITE)
        brow = f.mask(); f.tapered(brow, [(0.67 * sgn, 0.63), (0.37 * sgn, 0.50), (0.08 * sgn, 0.355)], 0.12, 0.20)
        f.paint(brow, INK)
        f.bump(brow, 60)
    # clenched toothy grin, corners pulled up, slight smirk (right corner higher)
    top = grin_points(-0.57, 0.59, -0.16, -0.09, 0.11)
    bot = grin_points(-0.57, 0.59, -0.16, -0.09, 0.47)[::-1]
    mouth = f.mask(); f.poly(mouth, top + bot)
    f.paint(f.dilate(mouth, 0.055), INK)
    f.paint(mouth, EYEW)
    # few, thin, light dividers: at 64 px the grin must read as one bright white crescent, not a grey checker band
    lines = f.mask()
    mid = grin_points(-0.57, 0.59, -0.16, -0.09, 0.29)
    f.curve_bar(lines, mid, 0.022)
    for xi in (-0.27, 0.0, 0.27):
        f.bar(lines, (xi, 0.2), (xi, -0.9), 0.022)
    f.paint(intersect(lines, mouth), (96, 84, 140))
    f.bump(mouth, -12)                                 # shallow: a deep recess shaded the teeth grey
    f.save('comet')


# ---------------------------------------------------------------- Kreuz: screaming terror
def cross_face(look=(0.075, 0.085), arm=0.55):
    f = Face(1.3)
    for sgn in (-1, 1):
        cx, cz = 0.325 * sgn, 0.08
        eye = f.mask(); f.ellipse(eye, cx, cz, 0.28, 0.325)
        f.paint(f.dilate(eye, 0.085), INK)
        f.paint(eye, EYEW)
        f.bump(eye, 70)
        # pinpoint pupils = terror
        pup = f.mask(); f.ellipse(pup, cx + look[0], cz + look[1], 0.072, 0.078)
        f.paint(pup, INK)
        hl = f.mask(); f.ellipse(hl, cx + look[0] - 0.018, cz + look[1] + 0.022, 0.017, 0.017)
        f.paint(hl, WHITE)
        # worried brows: inner ends shoot up, outer ends drop (kept inside the arms of the plus)
        brow = f.mask(); f.tapered(brow, [(0.47 * sgn, 0.47), (0.27 * sgn, 0.55), (0.13 * sgn, 0.79)], 0.16, 0.23)
        f.paint(brow, INK)
        f.bump(brow, 15)
    # big scream: tall rounded mouth, wider at the bottom, upper teeth and a tongue
    mouth = f.mask()
    pts = []
    for i in range(96):
        a = 2 * math.pi * i / 96
        s = math.sin(a)
        x = 0.30 * math.cos(a) * (1.0 - 0.18 * s)
        z = 0.43 * s
        pts.append((x, -0.70 + z))
    f.poly(mouth, pts)
    f.paint(f.dilate(mouth, 0.075), INK)
    f.paint(mouth, MOUTH_IN)
    tongue = f.mask(); f.ellipse(tongue, 0.02, -1.08, 0.24, 0.18)
    f.paint(intersect(tongue, mouth), TONGUE)
    teeth = f.mask(); f.poly(teeth, [(-0.4, -0.25), (0.4, -0.25), (0.4, -0.41), (-0.4, -0.41)])
    f.paint(intersect(teeth, mouth), EYEW)
    f.bump(mouth, -70)
    f.save('cross')


# ---------------------------------------------------------------- Tetraeder: panic
def tetra_face(look=(-0.06, 0.07)):
    f = Face(1.0)
    for sgn in (-1, 1):
        cx, cz = 0.285 * sgn, -0.03
        eye = f.mask(); f.ellipse(eye, cx, cz, 0.245, 0.275)
        f.paint(f.dilate(eye, 0.065), INK)
        f.paint(eye, EYEW)
        f.bump(eye, 70)
        pup = f.mask(); f.ellipse(pup, cx + look[0], cz + look[1], 0.065, 0.07)
        f.paint(pup, INK)
        hl = f.mask(); f.ellipse(hl, cx + look[0] - 0.016, cz + look[1] + 0.02, 0.016, 0.016)
        f.paint(hl, WHITE)
        brow = f.mask(); f.tapered(brow, [(0.40 * sgn, 0.33), (0.24 * sgn, 0.37), (0.10 * sgn, 0.52)], 0.095, 0.135)
        f.paint(brow, INK)
        f.bump(brow, 60)
    mouth = f.mask()
    pts = []
    for i in range(72):
        a = 2 * math.pi * i / 72
        s = math.sin(a)
        pts.append((0.22 * math.cos(a) * (1.0 - 0.15 * s), -0.50 + 0.19 * s))
    f.poly(mouth, pts)
    f.paint(f.dilate(mouth, 0.05), INK)
    f.paint(mouth, MOUTH_IN)
    tongue = f.mask(); f.ellipse(tongue, 0.01, -0.645, 0.15, 0.09)
    f.paint(intersect(tongue, mouth), TONGUE)
    f.bump(mouth, -70)
    f.save('tetra')


# ---------------------------------------------------------------- fused Wuerfel: angry partner (optional)
def cube_face(look=(-0.06, -0.05)):
    f = Face(1.0)
    for sgn in (-1, 1):
        cx, cz = 0.30 * sgn, 0.20
        eye = f.mask(); f.ellipse(eye, cx, cz, 0.20, 0.235)
        outer, inner = (0.64 * sgn, 0.52), (0.06 * sgn, 0.29)
        eye_c = intersect(eye, halfplane(f, outer, inner, below=True))
        f.paint(f.dilate(eye_c, 0.05), INK)
        f.paint(eye_c, EYEW)
        f.bump(eye_c, 70)
        pup = f.mask(); f.ellipse(pup, cx + look[0], cz + look[1], 0.11, 0.12)
        f.paint(intersect(pup, eye_c), INK)
        hl = f.mask(); f.ellipse(hl, cx + look[0] - 0.04, cz + look[1] + 0.045, 0.042, 0.042)
        f.paint(intersect(hl, eye_c), WHITE)
        brow = f.mask(); f.tapered(brow, [(0.64 * sgn, 0.59), (0.35 * sgn, 0.47), (0.08 * sgn, 0.335)], 0.11, 0.18)
        f.paint(brow, INK)
        f.bump(brow, 60)
    top = grin_points(-0.5, 0.5, -0.22, -0.18, 0.08)
    bot = grin_points(-0.5, 0.5, -0.22, -0.18, 0.40)[::-1]
    mouth = f.mask(); f.poly(mouth, top + bot)
    f.paint(f.dilate(mouth, 0.05), INK)
    f.paint(mouth, EYEW)
    lines = f.mask()
    f.curve_bar(lines, grin_points(-0.5, 0.5, -0.22, -0.18, 0.25), 0.032)
    for xi in (-0.25, 0.0, 0.25):
        f.bar(lines, (xi, 0.2), (xi, -0.9), 0.03)
    f.paint(intersect(lines, mouth), (52, 40, 84))
    f.bump(mouth, -40)
    f.save('cube')


if __name__ == '__main__':
    comet_face()
    cross_face()
    tetra_face()
    cube_face()
    print('faces written to', OUT)
