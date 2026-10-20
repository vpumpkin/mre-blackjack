// Round plumber hero: rig + skinned meshes.
//
// glTF conventions: +Y up, the character faces +Z, +X is his left. Units are
// metres (about 1.25 m tall). Every bone has an identity rest rotation, so all
// geometry is authored in model space and animation rotations are expressed in
// parent-aligned axes. All geometry is skinned (Roblox only deforms skinned
// MeshParts), the Root bone carries no influence, and every mesh stays below
// 10k triangles.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import {
	V, vec, lerp, smooth, clamp01, makeRandom, finish, transform, ellipsoid, cone, cylinder, torus,
	sphereCap, extrudeShape, loft, patch, skinRigid, skinBy,
} from './geometry.js';

const rand = makeRandom(42);
export const TRI_LIMIT = 10000;

// ---------------------------------------------------------------------------
// The egg-shaped body surface
// ---------------------------------------------------------------------------
export const EGG = { cy: 0.62, rx: 0.5, ry: 0.53, rz: 0.47, taper: 0.05 };
const kAt = (dy) => 1 - EGG.taper * dy;
const C = V(0, EGG.cy, 0);

export function eggPoint(theta, phi) {
	const dy = Math.cos(theta), s = Math.sin(theta), k = kAt(dy);
	return V(EGG.rx * k * s * Math.sin(phi), EGG.cy + EGG.ry * dy, EGG.rz * k * s * Math.cos(phi));
}
function eggF(p) {
	const dy = (p.y - EGG.cy) / EGG.ry, k = kAt(dy);
	return (p.x / (EGG.rx * k)) ** 2 + dy * dy + (p.z / (EGG.rz * k)) ** 2 - 1;
}
export function eggNormal(p) {
	const e = 1e-4;
	return V(
		eggF(V(p.x + e, p.y, p.z)) - eggF(V(p.x - e, p.y, p.z)),
		eggF(V(p.x, p.y + e, p.z)) - eggF(V(p.x, p.y - e, p.z)),
		eggF(V(p.x, p.y, p.z + e)) - eggF(V(p.x, p.y, p.z - e)),
	).normalize();
}
// radial projection from the egg centre onto the surface
export function eggProject(p) {
	const d = vec(p).sub(C);
	let lo = 0, hi = 3;
	for (let i = 0; i < 40; i++) {
		const m = (lo + hi) / 2;
		if (eggF(C.clone().addScaledVector(d, m)) < 0) lo = m; else hi = m;
	}
	return C.clone().addScaledVector(d, lo);
}
function eggFront(x, y) {
	const dy = (y - EGG.cy) / EGG.ry, k = kAt(dy);
	return V(x, y, EGG.rz * k * Math.sqrt(Math.max(0, 1 - dy * dy - (x / (EGG.rx * k)) ** 2)));
}

// Cheek and chin bulges displace the face part of the egg.
const BUMPS = [
	{ c: [0.215, 0.68], r: 0.135, h: 0.028 }, { c: [-0.215, 0.68], r: 0.135, h: 0.028 },
	{ c: [0, 0.545], r: 0.09, h: 0.004 },
];
function bumpAt(p) {
	if (p.z < 0.1) return 0;
	let h = 0;
	for (const b of BUMPS) {
		const d = Math.hypot(p.x - b.c[0], p.y - b.c[1]) / b.r;
		if (d < 1) h += b.h * (0.5 + 0.5 * Math.cos(Math.PI * d));
	}
	return h;
}
// surface point (with face bulges) + offset along the normal
function bodySurface(p) {
	const n = eggNormal(p);
	return p.clone().addScaledVector(n, bumpAt(p));
}
function face(x, y, off = 0) {
	const p = bodySurface(eggFront(x, y));
	return p.addScaledVector(eggNormal(p), off);
}

// ---------------------------------------------------------------------------
// Cap surface: the egg top above a tilted cut, puffed outwards
// ---------------------------------------------------------------------------
const yCut = (z) => 0.935 + 0.095 * (z / EGG.rz);
function capEdgeTheta(phi) {
	let lo = 0.05, hi = 2.2;
	for (let i = 0; i < 40; i++) {
		const m = (lo + hi) / 2;
		const p = eggPoint(m, phi);
		if (p.y - yCut(p.z) > 0) lo = m; else hi = m;
	}
	return lo;
}
const capPuff = (v) => 0.03 + 0.052 * Math.sin(clamp01(v) * Math.PI / 2);
function capPoint(a, phi, extra = 0) { // a: 0 at the edge, 1 at the top
	const te = capEdgeTheta(phi);
	const p = eggPoint(Math.max(1e-3, te * (1 - a)), phi);
	return p.addScaledVector(eggNormal(p), capPuff(a) + extra);
}
function capNormal(a, phi) {
	const e = 1e-3;
	const pa = capPoint(Math.min(1, a + e), phi).sub(capPoint(Math.max(0, a - e), phi));
	const pp = capPoint(a, phi + e).sub(capPoint(a, phi - e));
	return new THREE.Vector3().crossVectors(pp, pa).normalize();
}
// cap point from a direction (used to bend decals onto the cap)
function capFromDir(dir, extra = 0) {
	const d = vec(dir).normalize();
	const theta = Math.acos(THREE.MathUtils.clamp(d.y, -1, 1));
	const phi = Math.atan2(d.x, d.z);
	const a = 1 - theta / capEdgeTheta(phi);
	return { p: capPoint(a, phi, extra), n: capNormal(a, phi) };
}

// Bends a flat (x right, y up, z out) geometry onto a surface around `center`.
function conform(geo, center, normal, project) {
	const n0 = vec(normal).normalize();
	const t1 = new THREE.Vector3().crossVectors(V(0, 1, 0), n0).normalize();
	const t2 = new THREE.Vector3().crossVectors(n0, t1).normalize();
	const pos = geo.attributes.position;
	const p = new THREE.Vector3();
	for (let i = 0; i < pos.count; i++) {
		p.fromBufferAttribute(pos, i);
		const s = project(vec(center).addScaledVector(t1, p.x).addScaledVector(t2, p.y));
		const q = s.p.addScaledVector(s.n, p.z);
		pos.setXYZ(i, q.x, q.y, q.z);
	}
	geo.computeVertexNormals();
	return geo;
}
const onBody = (off) => (q) => {
	const p = bodySurface(eggProject(q));
	const n = eggNormal(p);
	return { p: p.addScaledVector(n, off), n };
};
const onCap = (off) => (q) => capFromDir(vec(q).sub(C), off);

// ---------------------------------------------------------------------------
// Rig
// ---------------------------------------------------------------------------
class Rig {
	constructor() {
		this.bones = [];
		this.byName = {};
		this.rest = {};
		this.parts = { body: [], limbs: [], head: [], eyes: [], gear: [], glow: [] };
		this.meta = {};
	}

	bone(name, parent, pos) {
		const b = new THREE.Bone();
		b.name = name;
		const wp = vec(pos);
		this.rest[name] = wp;
		if (parent) {
			b.position.copy(wp.clone().sub(this.rest[parent]));
			this.byName[parent].add(b);
		} else b.position.copy(wp);
		this.byName[name] = b;
		this.bones.push(b);
		return b;
	}

	bi(name) {
		const i = this.bones.indexOf(this.byName[name]);
		if (i < 0) throw new Error(`unknown bone ${name}`);
		if (i === 0) throw new Error('Root must not carry skin influences');
		return i;
	}

	rigid(mesh, bone, geo) { this.parts[mesh].push(skinRigid(geo, this.bi(bone))); }
	skinned(mesh, geo) { this.parts[mesh].push(geo); }
}

const SIDES = [[1, '_L'], [-1, '_R']];
const M = (p, sx) => [p[0] * sx, p[1], p[2]];

const EYE = { y: 0.81, x: 0.113, R: 0.088, embed: 0.046 };
const ARM = { S: [0.34, 0.53, 0.32], E: [0.483, 0.392, 0.435], W: [0.602, 0.23, 0.511] };
const FINGERS = [
	{ name: 'Index', off: 0.036, len: [0.046, 0.04], r: 0.021 },
	{ name: 'Middle', off: 0.012, len: [0.049, 0.042], r: 0.022 },
	{ name: 'Ring', off: -0.012, len: [0.046, 0.039], r: 0.021 },
	{ name: 'Pinky', off: -0.034, len: [0.036, 0.032], r: 0.018 },
];
const TANK = { c: [0, 0.62, -0.63], r: 0.17, h: 0.46 };
const HOSE_BONES = 10;

function basisQuat(x, y, z) {
	return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
}

// Equipment rest frames (canonical local axes: +Z forward/beam, +Y up).
function frameMatrix(origin, xAxis, yAxis, zAxis) {
	return new THREE.Matrix4().makeBasis(vec(xAxis).normalize(), vec(yAxis).normalize(), vec(zAxis).normalize()).setPosition(vec(origin));
}
const NOZZLE_REST = (() => {
	const z = V(0, 1, -0.22).normalize(), y = V(1, 0, 0);
	return frameMatrix([-0.585, 0.33, 0.1], new THREE.Vector3().crossVectors(y, z), y, z);
})();
const FLASH_REST = (() => {
	const z = V(0, -1, 0), y = V(0.86, 0, 0.51).normalize();
	return frameMatrix([0.445, 0.4, 0.275], new THREE.Vector3().crossVectors(y, z), y, z);
})();
const atFrame = (m, p) => vec(p).applyMatrix4(m);
const dirFrame = (m, d) => vec(d).transformDirection(m);

function buildSkeleton(R) {
	R.bone('Root', null, [0, 0, 0]);
	R.bone('Body', 'Root', [0, EGG.cy, 0]);
	R.bone('BodyLower', 'Body', [0, 0.3, 0.05]);
	R.bone('BodySide_L', 'Body', [0.42, 0.48, 0]);
	R.bone('BodySide_R', 'Body', [-0.42, 0.48, 0]);
	R.bone('BodyUpper', 'Body', [0, 0.8, 0]);
	R.bone('Head', 'BodyUpper', [0, 0.72, 0]);
	R.bone('Cap', 'Head', [0, 1.1, -0.02]);
	for (const [sx, s] of SIDES) {
		const e = eyeCenter(sx);
		R.bone(`Eye${s}`, 'Head', e);
		R.bone(`Pupil${s}`, `Eye${s}`, e);
		R.bone(`LidUpper${s}`, 'Head', e);
		R.bone(`LidLower${s}`, 'Head', e);
		R.bone(`BrowIn${s}`, 'Head', face(0.035 * sx, 0.918, 0.03));
		R.bone(`BrowOut${s}`, 'Head', face(0.185 * sx, 0.928, 0.03));
		R.bone(`Cheek${s}`, 'Head', face(0.215 * sx, 0.68, 0));
		R.bone(`Mustache${s}`, 'Head', face(0.03 * sx, 0.656, 0.02));
		R.bone(`MouthCorner${s}`, 'Head', face(0.075 * sx, 0.587, 0.003));
		R.bone(`Ear${s}`, 'Head', [0.47 * sx, 0.79, -0.04]);
	}
	R.bone('Nose', 'Head', face(0, 0.708, 0.042));
	R.bone('MouthUpper', 'Head', face(0, 0.575, 0.003));
	R.bone('MouthLower', 'Head', face(0, 0.569, 0.003));
	for (const [sx, s] of SIDES) {
		R.bone(`UpperArm${s}`, 'Body', M(ARM.S, sx));
		R.bone(`LowerArm${s}`, `UpperArm${s}`, M(ARM.E, sx));
		R.bone(`Hand${s}`, `LowerArm${s}`, M(ARM.W, sx));
		const hf = handFrame(sx);
		R.meta[`hand${s}`] = hf;
		R.bone(`Thumb1${s}`, `Hand${s}`, hf.thumb.base);
		R.bone(`Thumb2${s}`, `Thumb1${s}`, hf.thumb.joint);
		for (const f of hf.fingers) {
			R.bone(`${f.name}1${s}`, `Hand${s}`, f.base);
			R.bone(`${f.name}2${s}`, `${f.name}1${s}`, f.joint);
		}
		R.bone(`Foot${s}`, 'Root', [0.16 * sx, 0.06, 0.04]);
	}
	R.bone('Backpack', 'Body', TANK.c);
	const hose = hoseRest();
	R.meta.hose = hose;
	hose.points.forEach((p, i) => R.bone(hose.names[i], 'Body', p));
	R.bone('Nozzle', 'Body', atFrame(NOZZLE_REST, [0, 0, 0]));
	R.bone('NozzleTip', 'Nozzle', atFrame(NOZZLE_REST, [0, 0, 0.48]));
	R.bone('GrabPoint', 'NozzleTip', atFrame(NOZZLE_REST, [0, 0, 0.48]));
	R.bone('Flashlight', 'Body', atFrame(FLASH_REST, [0, 0, 0]));
	R.bone('FlashTip', 'Flashlight', atFrame(FLASH_REST, [0, 0, 0.14]));
}

function eyeCenter(sx) {
	const s = face(EYE.x * sx, EYE.y, 0);
	return s.addScaledVector(eggNormal(s), -EYE.embed).toArray();
}
const eyeAxis = (sx) => V(0.12 * sx, 0.04, 1).normalize();

// Iris and pupil are spheres intersecting the eyeball; the visible disc size
// depends on how far they poke out, so the pupil "dilates" by translating
// along the eye axis (Roblox animations cannot scale bones).
const IRIS = { a: 0.048, c: 0.036 };
const irisR = Math.sqrt((Math.sqrt(EYE.R ** 2 - IRIS.a ** 2) - IRIS.c) ** 2 + IRIS.a ** 2);
const PUPIL_R = 0.034;
export function pupilOffset(visibleRadius) {
	let lo = irisR - PUPIL_R + 1e-5, hi = Math.sqrt(irisR ** 2 - PUPIL_R ** 2);
	for (let i = 0; i < 50; i++) {
		const e = (lo + hi) / 2;
		const x = (irisR ** 2 - PUPIL_R ** 2 + e * e) / (2 * e);
		const a = Math.sqrt(Math.max(0, irisR ** 2 - x * x));
		if (a < visibleRadius) lo = e; else hi = e;
	}
	return IRIS.c + (lo + hi) / 2; // distance of the pupil centre from the eye centre
}
const PUPIL_REST = 0.022;

function handFrame(sx) {
	const E = vec(M(ARM.E, sx)), W = vec(M(ARM.W, sx));
	const f0 = W.clone().sub(E).normalize();
	const inward = V(-sx, 0, 0);
	const n0 = inward.clone().addScaledVector(f0, -inward.dot(f0)).normalize();
	let s0 = new THREE.Vector3().crossVectors(f0, n0).normalize();
	if (s0.z < 0) s0.negate();
	const sigma = Math.sign(s0.dot(new THREE.Vector3().crossVectors(f0, n0)));
	const palm = W.clone().addScaledVector(f0, 0.068);
	const fingers = FINGERS.map((f) => {
		const d = f0.clone().addScaledVector(s0, f.off * 1.3).normalize();
		const base = palm.clone().addScaledVector(f0, 0.048).addScaledVector(s0, f.off).addScaledVector(n0, 0.004);
		const joint = base.clone().addScaledVector(d, f.len[0]);
		const tip = joint.clone().addScaledVector(d, f.len[1]);
		return { ...f, d, base, joint, tip, axis: new THREE.Vector3().crossVectors(d, n0).normalize() };
	});
	const td = f0.clone().multiplyScalar(0.55).addScaledVector(s0, 0.75).addScaledVector(n0, 0.3).normalize();
	const tbase = palm.clone().addScaledVector(s0, 0.05).addScaledVector(f0, -0.022).addScaledVector(n0, 0.012);
	const tjoint = tbase.clone().addScaledVector(td, 0.042);
	const thumb = {
		d: td, base: tbase, joint: tjoint, tip: tjoint.clone().addScaledVector(td, 0.036), r: 0.023,
		axis: new THREE.Vector3().crossVectors(td, n0.clone().addScaledVector(s0, -0.6)).normalize(),
	};
	// grip point (centre of a held handle) in rest coordinates, without handle radius
	return { f0, n0, s0, sigma, palm, fingers, thumb, gripOffset: f0.clone().multiplyScalar(0.075).addScaledVector(n0, 0.034) };
}

function hoseRest() {
	const outlet = V(-0.12, 0.4, -0.72);
	const outDir = V(-0.4, -0.85, 0.3).normalize();
	const rear = atFrame(NOZZLE_REST, [0, 0, 0]);
	const inDir = dirFrame(NOZZLE_REST, [0, 0, 1]);
	const curve = hoseCurve(outlet, outDir, rear, inDir);
	const names = [], points = [], ts = [];
	for (let i = 0; i < HOSE_BONES; i++) {
		const t = i / (HOSE_BONES - 1);
		names.push(`Hose${String(i + 1).padStart(2, '0')}`);
		points.push(curve.getPoint(t));
		ts.push(t);
	}
	return { outlet, outDir, names, points, ts, curve, tankLocal: outlet.clone().sub(vec(TANK.c)), outDirLocal: outDir.clone() };
}

// Hose from the tank outlet to the nozzle coupling. `sag` drops the middle,
// `lag` drags the middle against the nozzle's motion (secondary motion).
export function hoseCurve(outlet, outDir, rear, inDir, sag = 0, lag = V(0, 0, 0)) {
	const len = outlet.distanceTo(rear);
	const h0 = 0.14 + len * 0.18, h1 = 0.16 + len * 0.22;
	const p1 = outlet.clone().addScaledVector(outDir, h0).add(V(0, -sag * 0.6, 0)).addScaledVector(lag, 0.5);
	const p2 = rear.clone().addScaledVector(inDir, -h1).add(V(0, -sag, 0)).addScaledVector(lag, 1);
	return new THREE.CubicBezierCurve3(outlet.clone(), p1, p2, rear.clone());
}

// ---------------------------------------------------------------------------
// Body mesh: egg, clothes, arms, gloves, shoes
// ---------------------------------------------------------------------------
const Y_SKIN = 0.538, Y_BIB = 0.493;
const thetaY = (y) => Math.acos(THREE.MathUtils.clamp((y - EGG.cy) / EGG.ry, -1, 1));

function bodyWeights(R) {
	const B = R.bi('Body'), U = R.bi('BodyUpper'), Lo = R.bi('BodyLower'), Hd = R.bi('Head');
	const SL = R.bi('BodySide_L'), SR = R.bi('BodySide_R'), CL = R.bi('Cheek_L'), CR = R.bi('Cheek_R');
	return (p) => {
		const wHead = smooth((p.y - 0.45) / 0.12);
		const wUpper = smooth((p.y - 0.36) / 0.16) * (1 - wHead);
		const wLower = smooth((0.4 - p.y) / 0.22);
		const bell = Math.exp(-(((p.y - 0.45) / 0.2) ** 2));
		const wSide = (sx) => smooth((p.x * sx - 0.2) / 0.25) * bell * 0.9;
		const cheek = (sx) => (p.z > 0.15 ? 0.85 * smooth(1 - Math.hypot(p.x - 0.215 * sx, p.y - 0.68) / 0.13) : 0);
		const cl = cheek(1) * wHead, cr = cheek(-1) * wHead;
		const out = [[Hd, wHead - cl - cr], [CL, cl], [CR, cr], [U, wUpper], [Lo, wLower * (1 - wHead)], [SL, wSide(1)], [SR, wSide(-1)]];
		const sum = out.reduce((s, e) => s + Math.max(0, e[1]), 0);
		if (sum < 1) out.push([B, 1 - sum]);
		return out;
	};
}

function buildBody(R) {
	const wts = bodyWeights(R);
	const bands = [
		{ y0: 1.2, y1: Y_SKIN, rings: 22, swatch: 'skin' },
		{ y0: Y_SKIN, y1: Y_BIB, rings: 3, swatch: 'shirt' },
		{ y0: Y_BIB, y1: -1, rings: 16, swatch: 'overalls' },
	];
	for (const b of bands) {
		const t0 = b.y0 > EGG.cy + EGG.ry ? 0.001 : thetaY(b.y0);
		const t1 = b.y1 < EGG.cy - EGG.ry ? Math.PI - 0.001 : thetaY(b.y1);
		const g = patch((u, v) => ({ p: bodySurface(eggPoint(lerp(t0, t1, u), v * Math.PI * 2)) }), {
			nu: b.rings, nv: 56, wrapV: true, swatch: b.swatch,
		});
		R.skinned('body', skinBy(g, wts));
	}
	// bib seam band + stitching around the whole body
	const ring = (y, off, swatch, r, n = 48) => {
		const pts = [];
		for (let i = 0; i <= n; i++) {
			const p = eggPoint(thetaY(y), (i / n) * Math.PI * 2);
			pts.push(bodySurface(p).addScaledVector(eggNormal(p), off));
		}
		return loft(pts, { radii: [[r[0], r[1]]], up: [0, 1, 0], perSeg: 1, radial: 6, swatch, capStart: false, capEnd: false });
	};
	R.skinned('body', skinBy(ring(Y_BIB + 0.004, 0.006, 'overallsDark', [0.011, 0.007]), wts));
	R.skinned('body', skinBy(ring(Y_BIB - 0.018, 0.004, 'stitch', [0.0025, 0.0025]), wts));
	R.skinned('body', skinBy(ring(0.4, 0.012, 'strap', [0.012, 0.022]), wts)); // harness belt

	// bib tabs with buttons (front and back)
	for (const [sx] of SIDES) {
		for (const front of [1, -1]) {
			const phi = front > 0 ? 0.62 * sx : Math.PI - 0.62 * sx;
			const g = patch((u, v) => {
				const y = lerp(Y_BIB - 0.01, 0.562, u);
				return { p: bodySurface(eggPoint(thetaY(y), phi + (v - 0.5) * 0.2)) };
			}, { nu: 3, nv: 4, offset: 0.005, flip: true, swatch: 'overalls' });
			R.skinned('body', skinBy(g, wts));
			const bp = bodySurface(eggPoint(thetaY(0.535), phi));
			const bn = eggNormal(bp);
			const q = new THREE.Quaternion().setFromUnitVectors(V(0, 1, 0), bn);
			R.skinned('body', skinBy(ellipsoid(bp.clone().addScaledVector(bn, 0.008), [0.034, 0.013, 0.034], 'button', { q, w: 14, h: 6 }), wts));
			R.skinned('body', skinBy(torus(bp.clone().addScaledVector(bn, 0.013), 0.022, 0.004, bn, 'button', { seg: 14, tube: 4 }), wts));
		}
	}
	// stars on the trousers
	const star = (rOut) => {
		const s = new THREE.Shape();
		for (let i = 0; i < 10; i++) {
			const a = Math.PI / 2 + (i * Math.PI) / 5;
			const r = i % 2 === 0 ? rOut : rOut * 0.45;
			if (i === 0) s.moveTo(Math.cos(a) * r, Math.sin(a) * r); else s.lineTo(Math.cos(a) * r, Math.sin(a) * r);
		}
		s.closePath();
		return s;
	};
	for (const [x, y, size, rot] of [[0.25, 0.27, 0.042, 0.2], [-0.29, 0.34, 0.03, -0.3], [0.05, 0.16, 0.024, 0.5]]) {
		const g = extrudeShape(star(size), 0.004, 'star', 0.0015, 2);
		g.rotateZ(rot);
		const c = eggFront(x, y);
		R.skinned('body', skinBy(conform(g, c, eggNormal(c), onBody(0.004)), wts));
	}
	// side pocket seams
	for (const [sx] of SIDES) {
		const pts = [];
		for (let i = 0; i <= 10; i++) {
			const f = i / 10;
			pts.push(face(sx * lerp(0.2, 0.4, f), lerp(0.47, 0.25, f * f), 0.004));
		}
		R.skinned('body', skinBy(loft(pts, { radii: [[0.0025, 0.0025]], radial: 5, perSeg: 2, swatch: 'stitch' }), wts));
	}
	buildArms(R);
	buildShoes(R);
}

function buildArms(R) {
	for (const [sx, s] of SIDES) {
		const S = vec(M(ARM.S, sx)), E = vec(M(ARM.E, sx)), W = vec(M(ARM.W, sx));
		const up = S.clone().sub(E).normalize();
		const inner = S.clone().addScaledVector(up, 0.06);
		R.skinned('limbs', loft([inner, S, E, W], {
			radii: [[0.078, 0.078], [0.077, 0.077], [0.066, 0.066], [0.055, 0.055]],
			owners: [R.bi(`UpperArm${s}`), R.bi(`UpperArm${s}`), R.bi(`LowerArm${s}`)], ownerBefore: R.bi('Body'),
			ownerAfter: R.bi(`Hand${s}`), perSeg: 5, radial: 14, up: [0, 0, 1], swatch: 'shirt',
		}));
		buildGlove(R, sx, s);
	}
}

function buildGlove(R, sx, s) {
	const hf = R.meta[`hand${s}`];
	const { f0, n0, s0, palm } = hf;
	const W = vec(M(ARM.W, sx));
	const hand = `Hand${s}`;
	// cuff
	R.rigid('limbs', hand, loft([W.clone().addScaledVector(f0, -0.012), W.clone().addScaledVector(f0, 0.02), W.clone().addScaledVector(f0, 0.035)], {
		radii: [[0.06, 0.06], [0.064, 0.064], [0.055, 0.055]], radial: 16, perSeg: 2, up: n0, swatch: 'glove',
	}));
	// palm (oriented ellipsoid)
	const q = basisQuat(s0, n0, f0);
	R.rigid('limbs', hand, ellipsoid(palm, [0.062, 0.036, 0.06], 'glove', { q, w: 16, h: 12 }));
	// stitched lines on the back of the glove
	for (const o of [-0.02, 0, 0.02]) {
		const a = palm.clone().addScaledVector(s0, o).addScaledVector(n0, -0.035).addScaledVector(f0, -0.02);
		const b = a.clone().addScaledVector(f0, 0.04).addScaledVector(n0, -0.002);
		R.rigid('limbs', hand, loft([a, b], { radii: [[0.0028, 0.0028]], radial: 5, perSeg: 1, swatch: 'gloveLine' }));
	}
	const digit = (bone1, bone2, base, joint, tip, r) => {
		R.rigid('limbs', bone1, cylinder(base, joint, r, r * 0.97, 'glove', 10, true));
		R.rigid('limbs', bone2, ellipsoid(joint, [r * 0.97, r * 0.97, r * 0.97], 'glove', { w: 10, h: 7 }));
		R.rigid('limbs', bone2, cylinder(joint, tip, r * 0.97, r * 0.92, 'glove', 10, true));
		R.rigid('limbs', bone2, ellipsoid(tip, [r * 0.92, r * 0.92, r * 0.92], 'glove', { w: 10, h: 7 }));
	};
	for (const f of hf.fingers) digit(`${f.name}1${s}`, `${f.name}2${s}`, f.base, f.joint, f.tip, f.r);
	digit(`Thumb1${s}`, `Thumb2${s}`, hf.thumb.base, hf.thumb.joint, hf.thumb.tip, hf.thumb.r);
}

function buildShoes(R) {
	for (const [sx, s] of SIDES) {
		R.rigid('limbs', `Foot${s}`, ellipsoid([0.16 * sx, 0.06, 0.1], [0.085, 0.058, 0.125], 'shoe', { w: 16, h: 10 }));
		R.rigid('limbs', `Foot${s}`, ellipsoid([0.16 * sx, 0.018, 0.1], [0.088, 0.02, 0.128], 'sole', { w: 16, h: 6 }));
	}
}

// ---------------------------------------------------------------------------
// Head mesh: cap, hair, ears, eyes + lids, brows, nose, mustache, mouth
// ---------------------------------------------------------------------------
function buildHead(R) {
	// cap dome
	R.rigid('head', 'Cap', patch((a, b) => ({ p: capPoint(a, b * Math.PI * 2) }), { nu: 14, nv: 48, wrapV: true, flip: true, swatch: 'cap' }));
	// rolled lower edge of the cap
	const edge = [];
	for (let i = 0; i <= 48; i++) edge.push(capPoint(0, (i / 48) * Math.PI * 2, -0.004));
	R.rigid('head', 'Cap', loft(edge, { radii: [[0.017, 0.017]], up: [0, 1, 0], perSeg: 1, radial: 8, swatch: 'capDark', capStart: false, capEnd: false }));
	// brim over the forehead
	const arc = 1.08;
	R.rigid('head', 'Cap', patch((u, v) => {
		const phi = (u - 0.5) * 2 * arc;
		const pe = capPoint(0, phi, -0.004);
		const o = V(pe.x, 0, pe.z).normalize();
		const w = 0.15 * Math.pow(Math.cos((phi / arc) * Math.PI / 2), 0.55);
		const a = v * Math.PI * 2;
		const outer = (1 + Math.cos(a)) / 2;
		const p = pe.clone().addScaledVector(o, w * outer).add(V(0, 0.02 * Math.sin(a) * (1 - 0.4 * outer) - 0.028 * outer * outer, 0));
		return { p };
	}, { nu: 24, nv: 10, wrapV: true, flip: true, swatch: 'cap' }));
	// emblem disc + symbol (a plumber's wrench)
	const emblemDir = V(0, 0.9, 0.46).normalize();
	const ec = capFromDir(emblemDir, 0.002);
	R.rigid('head', 'Cap', patch((u, v) => {
		const a = v * Math.PI * 2, r = 0.072 * u;
		const t1 = new THREE.Vector3().crossVectors(V(0, 1, 0), ec.n).normalize();
		const t2 = new THREE.Vector3().crossVectors(ec.n, t1);
		const q = ec.p.clone().addScaledVector(t1, Math.cos(a) * r).addScaledVector(t2, Math.sin(a) * r);
		return capFromDir(q.sub(C), 0.004);
	}, { nu: 4, nv: 28, wrapV: true, swatch: 'emblem' }));
	R.rigid('head', 'Cap', conform(extrudeShape(wrench(), 0.005, 'emblemSymbol', 0.0012, 6), ec.p, ec.n, onCap(0.006)));

	// hair: wavy band under the cap from the sideburns around the back
	R.rigid('head', 'Head', patch((u, v) => {
		const phi = lerp(0.92, Math.PI * 2 - 0.92, u);
		const side = Math.abs(Math.sin(phi));
		const len = (0.13 + 0.07 * side) * (1 + 0.22 * Math.sin(phi * 11)) * (Math.cos(phi) > 0.1 ? 1.25 : 1);
		const te = capEdgeTheta(phi) - 0.04;
		const p = eggPoint(te + v * len, phi);
		return { p: p.addScaledVector(eggNormal(p), 0.022 - 0.012 * v) };
	}, { nu: 56, nv: 4, flip: true, swatch: 'hair' }));
	for (const [sx, s] of SIDES) {
		// curly tufts at the sideburns
		for (const [phi, dy, len] of [[1.02, 0.0, 0.07], [1.25, -0.02, 0.06], [2.0, 0.0, 0.06], [2.6, 0.01, 0.05]]) {
			const p0 = capPoint(0, phi * sx, -0.01);
			const n = eggNormal(p0);
			const p1 = p0.clone().add(V(0, -len * 0.6 + dy, 0)).addScaledVector(n, 0.03);
			const p2 = p1.clone().add(V(0, -len * 0.5, 0)).addScaledVector(n, -0.01).add(V(0, 0, 0.02 * Math.cos(phi)));
			R.rigid('head', 'Head', loft([p0, p1, p2], { radii: [[0.03, 0.022], [0.028, 0.02], [0.006, 0.006]], up: n, perSeg: 4, radial: 8, swatch: 'hair' }));
		}
		// ears
		const ec2 = vec([0.495 * sx, 0.79, -0.035]);
		R.rigid('head', `Ear${s}`, ellipsoid(ec2, [0.032, 0.066, 0.05], 'ear', { rot: [0.1, 0, -0.2 * sx], w: 14, h: 10 }));
		R.rigid('head', `Ear${s}`, ellipsoid(ec2.clone().add(V(0.018 * sx, 0, 0.006)), [0.012, 0.043, 0.03], 'skinShade', { rot: [0.1, 0, -0.2 * sx], w: 10, h: 8 }));
		buildEye(R, sx, s);
		buildBrow(R, sx, s);
		buildMustache(R, sx, s);
	}
	// nose
	R.rigid('head', 'Nose', ellipsoid(R.rest.Nose, [0.092, 0.082, 0.082], 'skin', { w: 22, h: 16 }));
	buildMouth(R);
}

function wrench() {
	const s = new THREE.Shape();
	const R0 = 0.028, cy = 0.024, hw = 0.011, a0 = Math.acos(hw / R0);
	s.moveTo(Math.cos(a0) * R0, cy + Math.sin(a0) * R0);
	for (let i = 1; i <= 12; i++) {
		const a = lerp(a0, -1.15, i / 12);
		s.lineTo(Math.cos(a) * R0, cy + Math.sin(a) * R0);
	}
	s.lineTo(0.011, -0.05);
	s.quadraticCurveTo(0, -0.058, -0.011, -0.05);
	s.lineTo(-Math.cos(-1.15) * R0, cy + Math.sin(-1.15) * R0);
	for (let i = 1; i <= 12; i++) {
		const a = lerp(Math.PI + 1.15, Math.PI - a0, i / 12);
		s.lineTo(Math.cos(a) * R0, cy + Math.sin(a) * R0);
	}
	s.lineTo(-hw, cy + 0.004);
	s.lineTo(hw, cy + 0.004);
	s.closePath();
	return s;
}

function buildEye(R, sx, s) {
	const c = vec(R.rest[`Eye${s}`]);
	const axis = eyeAxis(sx);
	const q = new THREE.Quaternion().setFromUnitVectors(V(0, 0, 1), axis);
	R.rigid('eyes', 'Head', ellipsoid(c, [EYE.R, EYE.R, EYE.R], 'sclera', { w: 22, h: 16 }));
	// iris (two-tone ring) and pupil
	const iris = ellipsoid(c.clone().addScaledVector(axis, IRIS.c), [irisR, irisR, irisR], 'iris', { w: 20, h: 14 });
	finish(iris, (p) => {
		const d = p.clone().sub(c);
		const radial = d.clone().addScaledVector(axis, -d.dot(axis)).length();
		return radial > IRIS.a * 0.78 ? 'irisRing' : 'iris';
	});
	R.rigid('eyes', `Eye${s}`, iris);
	R.rigid('eyes', `Pupil${s}`, ellipsoid(c.clone().addScaledVector(axis, pupilOffset(PUPIL_REST)), [PUPIL_R, PUPIL_R, PUPIL_R], 'pupil', { w: 14, h: 10 }));
	// fixed specular highlights
	const hDir = axis.clone().add(V(-0.36, 0.42, 0)).normalize();
	R.rigid('eyes', 'Head', ellipsoid(c.clone().addScaledVector(hDir, EYE.R + 0.004), [0.013, 0.013, 0.006], 'highlight', { q: new THREE.Quaternion().setFromUnitVectors(V(0, 0, 1), hDir), w: 10, h: 6 }));
	const hDir2 = axis.clone().add(V(0.22, -0.2, 0)).normalize();
	R.rigid('eyes', 'Head', ellipsoid(c.clone().addScaledVector(hDir2, EYE.R + 0.003), [0.006, 0.006, 0.003], 'highlight', { q: new THREE.Quaternion().setFromUnitVectors(V(0, 0, 1), hDir2), w: 8, h: 5 }));
	// eyelids: skin shells around the eyeball poles; they rotate about X to blink
	const lidR = EYE.R + 0.011;
	R.rigid('eyes', `LidUpper${s}`, sphereCap(c, lidR, 1.0, 'skin', { w: 24, h: 9 }));
	R.rigid('eyes', `LidLower${s}`, sphereCap(c, lidR * 0.995, 1.05, 'skin', { w: 24, h: 8, bottom: true }));
	R.meta[`eye${s}`] = { center: c, axis, pupilRest: pupilOffset(PUPIL_REST) };
}

function buildBrow(R, sx, s) {
	const pts = [[0.035, 0.918], [0.075, 0.942], [0.115, 0.952], [0.155, 0.945], [0.185, 0.928]].map(([x, y]) => face(x * sx, y, 0.03));
	const n = eggNormal(pts[2]);
	const g = loft(pts, {
		radii: (u) => { const k = 1 - Math.abs(u - 0.4) * 1.2; return [0.014 + 0.013 * k, 0.009 + 0.006 * k]; },
		up: n, perSeg: 4, radial: 10, swatch: 'brow',
	});
	const bIn = R.bi(`BrowIn${s}`), bOut = R.bi(`BrowOut${s}`);
	R.skinned('head', skinBy(g, (p) => {
		const u = clamp01((Math.abs(p.x) - 0.035) / 0.15);
		return [[bIn, 1 - smooth(u)], [bOut, smooth(u)]];
	}));
}

function buildMustache(R, sx, s) {
	const pts = [[-0.012, 0.661], [0.075, 0.655], [0.14, 0.644], [0.198, 0.624], [0.226, 0.594]].map(([x, y]) => face(x * sx, y, 0.022));
	const n = eggNormal(pts[2]);
	R.rigid('head', `Mustache${s}`, loft(pts, {
		radii: (u) => [0.05 - 0.028 * u * u, 0.024 - 0.008 * u],
		up: n, perSeg: 8, radial: 16, swatch: 'mustache',
		noise: (u, th) => 1 + 0.2 * Math.pow(Math.max(0, Math.cos(th)), 2) * Math.sin(u * Math.PI * 3.2 + 0.4),
	}));
}

// Mouth: thin dark patch on the face, skinned to MouthUpper / MouthLower /
// corners. Teeth and tongue are zero-height strips that only open up when
// the lower lip bone moves down.
const MOUTH = { w: 0.078, y: 0.575, curve: 0.014, gap: 0.006 };
const mouthTop = (x) => MOUTH.y + MOUTH.curve * (x / MOUTH.w) ** 2;
const mouthBot = (x) => mouthTop(x) - MOUTH.gap * (1 - (x / MOUTH.w) ** 2);
function buildMouth(R) {
	const U = R.bi('MouthUpper'), Lo = R.bi('MouthLower'), CL = R.bi('MouthCorner_L'), CR = R.bi('MouthCorner_R');
	const strip = (w, top, bot, off, swatch) => patch((t, sNorm) => {
		const x = lerp(-w, w, sNorm);
		const p = face(x, lerp(top(x), bot(x), t), off);
		return { p, n: eggNormal(p) };
	}, { nu: 3, nv: 16, swatch });
	const corner = (x) => smooth((Math.abs(x) / MOUTH.w - 0.5) / 0.5);
	const weights = (topW, botW) => (p) => {
		const tb = mouthTop(p.x) - mouthBot(p.x);
		const t = tb > 1e-5 ? clamp01((mouthTop(p.x) - p.y) / tb) : 0.5;
		const c = corner(p.x);
		const mix = [[U, (1 - t) * topW[0] + t * botW[0]], [Lo, (1 - t) * topW[1] + t * botW[1]]];
		return [...mix.map(([b, w]) => [b, w * (1 - c)]), [p.x > 0 ? CL : CR, c]];
	};
	R.skinned('head', skinBy(strip(MOUTH.w, mouthTop, mouthBot, 0.005, 'mouth'), weights([1, 0], [0, 1])));
	R.skinned('head', skinBy(strip(0.05, mouthTop, mouthTop, 0.0062, 'teeth'), (p) => [[U, 0.62], [Lo, 0.38]].map(([b, w]) => [b, w])));
	R.skinned('head', skinBy(strip(0.042, mouthBot, mouthBot, 0.0058, 'tongue'), (p) => [[U, 0.2], [Lo, 0.8]]));
	// lower lip / chin crease
	const lip = [];
	for (let i = 0; i <= 8; i++) {
		const x = lerp(-0.05, 0.05, i / 8);
		lip.push(face(x, mouthBot(x) - 0.03 - 0.006 * (1 - (x / 0.05) ** 2), 0.002));
	}
	R.skinned('head', skinBy(loft(lip, { radii: [[0.0035, 0.002]], radial: 5, perSeg: 2, swatch: 'skinShade' }), () => [[Lo, 1]]));
}

// ---------------------------------------------------------------------------
// Gear: vacuum backpack, hose, nozzle, flashlight
// ---------------------------------------------------------------------------
function buildGear(R) {
	const tc = vec(TANK.c), r = TANK.r, h = TANK.h;
	const top = tc.clone().add(V(0, h / 2, 0)), bot = tc.clone().add(V(0, -h / 2, 0));
	const BP = 'Backpack';
	R.rigid('gear', BP, cylinder(bot, top, r, r, 'tank', 24, true));
	R.rigid('gear', BP, sphereCap(top, r, Math.PI / 2, 'tank', { w: 24, h: 8 }));
	R.rigid('gear', BP, sphereCap(bot, r, Math.PI / 2, 'tankDark', { w: 24, h: 6, bottom: true }));
	for (const y of [-0.17, 0, 0.17]) R.rigid('gear', BP, torus(tc.clone().add(V(0, y, 0)), r + 0.004, 0.012, [0, 1, 0], 'copper', { seg: 28, tube: 6 }));
	// exhaust chimney + cap
	const ch = top.clone().add(V(0.05, 0.12, -0.02));
	R.rigid('gear', BP, cylinder(top.clone().add(V(0.05, 0.08, -0.02)), ch.clone().add(V(0, 0.06, 0)), 0.03, 0.028, 'copper', 12));
	R.rigid('gear', BP, ellipsoid(ch.clone().add(V(0, 0.075, 0)), [0.042, 0.014, 0.042], 'tankDark', { w: 12, h: 6 }));
	// side gauge
	const gc = tc.clone().add(V(r + 0.01, 0.06, 0));
	R.rigid('gear', BP, cylinder(gc.clone().add(V(-0.02, 0, 0)), gc.clone().add(V(0.012, 0, 0)), 0.055, 0.055, 'copper', 18));
	R.rigid('gear', BP, cylinder(gc.clone().add(V(0.011, 0, 0)), gc.clone().add(V(0.015, 0, 0)), 0.045, 0.045, 'gaugeFace', 18));
	R.rigid('gear', BP, cone(gc.clone().add(V(0.017, -0.005, 0)), gc.clone().add(V(0.017, 0.03, 0.02)), 0.005, 'needle', { seg: 4 }));
	// energy meter on the back of the tank (glow cells in their own mesh)
	const back = tc.clone().add(V(0, 0, -r));
	R.rigid('gear', BP, ellipsoid(back.clone().add(V(0, 0.02, -0.005)), [0.05, 0.16, 0.025], 'tankDark', { w: 12, h: 10 }));
	for (let i = 0; i < 4; i++) {
		R.rigid('glow', BP, ellipsoid(back.clone().add(V(0, -0.09 + i * 0.06, -0.022)), [0.03, 0.022, 0.012], 'glowCyan', { w: 10, h: 6 }));
	}
	R.rigid('glow', BP, ellipsoid(top.clone().add(V(-0.07, 0.035, 0.05)), [0.022, 0.022, 0.022], 'glowGreen', { w: 10, h: 8 }));
	// outlet
	const hose = R.meta.hose;
	R.rigid('gear', BP, cylinder(hose.outlet.clone().addScaledVector(hose.outDir, -0.05), hose.outlet.clone().addScaledVector(hose.outDir, 0.01), 0.048, 0.044, 'copper', 14));
	// frame plate between tank and back
	R.rigid('gear', BP, ellipsoid(tc.clone().add(V(0, 0, r * 0.75)), [0.13, 0.2, 0.03], 'strap', { w: 12, h: 10 }));

	// hose: a ribbed tube skinned along the hose bone chain
	const hb = hose.names.map((n) => R.bi(n));
	const curve = hose.curve;
	const pts = [];
	for (let i = 0; i <= 36; i++) pts.push(curve.getPoint(i / 36));
	const hoseGeo = loft(pts, { radii: [[0.034, 0.034]], perSeg: 2, radial: 12, up: [0, 1, 0], swatch: (u, th, d, ring) => (ring % 3 === 0 ? 'hoseRib' : 'hose') });
	const ringT = [];
	for (let i = 0; i <= 72; i++) ringT.push(i / 72);
	R.skinned('gear', skinBy(hoseGeo, (p) => {
		// nearest curve parameter -> blend between neighbouring hose bones
		let best = 0, bd = Infinity;
		for (const t of ringT) { const d = curve.getPoint(t).distanceToSquared(p); if (d < bd) { bd = d; best = t; } }
		const s = best * (HOSE_BONES - 1);
		const i = Math.min(HOSE_BONES - 2, Math.floor(s));
		return [[hb[i], 1 - (s - i)], [hb[i + 1], s - i]];
	}));

	// nozzle (authored in its canonical frame, then placed at the holster)
	const N = (geo) => geo.applyMatrix4(NOZZLE_REST);
	const nz = 'Nozzle';
	R.rigid('gear', nz, N(cylinder([0, 0, -0.035], [0, 0, 0.03], 0.054, 0.052, 'copper', 16)));
	R.rigid('gear', nz, N(cylinder([0, 0, 0], [0, 0, 0.34], 0.044, 0.044, 'tank', 16, true)));
	for (const z of [0.06, 0.2, 0.31]) R.rigid('gear', nz, N(torus([0, 0, z], 0.046, 0.007, [0, 0, 1], 'copper', { seg: 18, tube: 5 })));
	R.rigid('gear', nz, N(cylinder([0, 0, 0.34], [0, 0, 0.48], 0.046, 0.096, 'steel', 20, true)));
	const inner = N(cylinder([0, 0, 0.35], [0, 0, 0.475], 0.04, 0.09, 'tankDark', 20, true));
	flipFaces(inner);
	R.rigid('gear', nz, inner);
	R.rigid('gear', nz, N(cylinder([0, 0, 0.35], [0, 0, 0.36], 0.042, 0.042, 'rubber', 16)));
	R.rigid('gear', nz, N(torus([0, 0, 0.478], 0.094, 0.008, [0, 0, 1], 'copper', { seg: 24, tube: 5 })));
	R.rigid('glow', nz, N(torus([0, 0, 0.385], 0.052, 0.007, [0, 0, 1], 'glowCyan', { seg: 20, tube: 5 })));
	R.rigid('gear', nz, N(cylinder([0, -0.03, 0.1], [0, -0.15, 0.075], 0.021, 0.021, 'rubber', 10)));
	R.rigid('gear', nz, N(ellipsoid([0, -0.152, 0.075], [0.024, 0.012, 0.024], 'rubber', { w: 10, h: 6 })));
	// carry handle on top for the second hand
	R.rigid('gear', nz, N(cylinder([0.05, 0.035, 0.15], [0.055, 0.088, 0.15], 0.009, 0.009, 'copper', 8)));
	R.rigid('gear', nz, N(cylinder([-0.05, 0.035, 0.15], [-0.055, 0.088, 0.15], 0.009, 0.009, 'copper', 8)));
	R.rigid('gear', nz, N(cylinder([-0.065, 0.088, 0.15], [0.065, 0.088, 0.15], 0.017, 0.017, 'rubber', 10)));
	R.rigid('gear', nz, N(ellipsoid([0, -0.045, 0.135], [0.008, 0.012, 0.012], 'needle', { w: 8, h: 6 })));
	R.meta.nozzle = {
		rest: NOZZLE_REST.clone(),
		grips: {
			// normal: side of the handle the palm sits on; thumb: +1 thumb along axis, -1 against it
			rear: { c: V(0, -0.09, 0.0875), axis: V(0, -0.115, -0.025).normalize(), normal: V(-1, 0, 0), r: 0.021, thumb: -1 },
			top: { c: V(0, 0.088, 0.15), axis: V(1, 0, 0), normal: V(0, 1, 0), r: 0.017, thumb: -1 },
		},
		tip: V(0, 0, 0.48),
	};

	// flashlight
	const F = (geo) => geo.applyMatrix4(FLASH_REST);
	const fl = 'Flashlight';
	R.rigid('gear', fl, F(cylinder([0, 0, -0.112], [0, 0, -0.095], 0.026, 0.027, 'rubber', 14)));
	R.rigid('gear', fl, F(cylinder([0, 0, -0.096], [0, 0, 0.06], 0.027, 0.027, 'flashBody', 14, true)));
	for (const z of [-0.07, -0.045, -0.02]) R.rigid('gear', fl, F(torus([0, 0, z], 0.0275, 0.0038, [0, 0, 1], 'rubber', { seg: 14, tube: 4 })));
	R.rigid('gear', fl, F(cylinder([0, 0, 0.06], [0, 0, 0.1], 0.027, 0.043, 'flashHead', 16, true)));
	R.rigid('gear', fl, F(cylinder([0, 0, 0.1], [0, 0, 0.136], 0.044, 0.044, 'flashHead', 16)));
	R.rigid('gear', fl, F(torus([0, 0, 0.136], 0.041, 0.004, [0, 0, 1], 'rubber', { seg: 16, tube: 4 })));
	R.rigid('glow', fl, F(cylinder([0, 0, 0.134], [0, 0, 0.139], 0.037, 0.037, 'glowWarm', 16)));
	R.rigid('gear', fl, F(ellipsoid([0, 0.028, 0.025], [0.008, 0.006, 0.014], 'rubber', { w: 8, h: 6 })));
	R.rigid('gear', fl, F(torus([0, 0, -0.118], 0.012, 0.003, [1, 0, 0], 'steel', { seg: 10, tube: 4 })));
	R.meta.flashlight = {
		rest: FLASH_REST.clone(),
		grips: { main: { c: V(0, 0, -0.035), axis: V(0, 0, 1), normal: V(1, 0, 0), r: 0.027, thumb: 1 } },
		tip: V(0, 0, 0.14),
	};
	// holster loop for the flashlight on the harness belt
	R.skinned('body', skinBy(torus(atFrame(FLASH_REST, [0, 0, -0.03]), 0.033, 0.006, dirFrame(FLASH_REST, [0, 0, 1]), 'strap', { seg: 16, tube: 4 }), bodyWeights(R)));
}

function flipFaces(geo) {
	const idx = geo.index.array;
	for (let i = 0; i < idx.length; i += 3) { const t = idx[i + 1]; idx[i + 1] = idx[i + 2]; idx[i + 2] = t; }
	const n = geo.attributes.normal;
	for (let i = 0; i < n.count; i++) n.setXYZ(i, -n.getX(i), -n.getY(i), -n.getZ(i));
}

// ---------------------------------------------------------------------------
function makeMaterials() {
	return {
		main: new THREE.MeshStandardMaterial({ name: 'Plumber_Mat', color: 0xffffff, roughness: 1, metalness: 1 }),
		glow: new THREE.MeshStandardMaterial({ name: 'Plumber_Glow', color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 4, roughness: 0.3, metalness: 0 }),
	};
}

export function buildCharacter() {
	const R = new Rig();
	buildSkeleton(R);
	buildBody(R);
	buildHead(R);
	buildGear(R);

	const scene = new THREE.Scene();
	scene.name = 'RoundPlumber';
	scene.add(R.bones[0]);
	scene.updateMatrixWorld(true);
	const skeleton = new THREE.Skeleton(R.bones);
	const mats = makeMaterials();
	const meshes = {};
	const names = { body: 'PlumberBody', limbs: 'PlumberLimbs', head: 'PlumberHead', eyes: 'PlumberEyes', gear: 'PlumberGear', glow: 'PlumberGlow' };
	for (const [key, geos] of Object.entries(R.parts)) {
		const geo = mergeGeometries(geos.map((g) => finish(g)));
		const tris = geo.index.count / 3;
		if (tris > TRI_LIMIT) throw new Error(`${names[key]} has ${tris} triangles (limit ${TRI_LIMIT})`);
		const mesh = new THREE.SkinnedMesh(geo, key === 'glow' ? mats.glow : mats.main);
		mesh.name = names[key];
		scene.add(mesh);
		mesh.bind(skeleton, new THREE.Matrix4());
		meshes[key] = mesh;
	}
	return { scene, rig: R, meshes, skeleton };
}
