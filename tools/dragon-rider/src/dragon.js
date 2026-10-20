// Procedural "dragon + Link-style rider" model.
//
// Coordinate system follows glTF: +Y up, the model faces +Z, +X is the
// dragon's left. Units are metres (the dragon is ~17 m long, ~18 m wingspan).
// Every node is created with an identity rest rotation, so all geometry can be
// authored directly in model space and animation rotations are expressed in
// parent-aligned axes (X = pitch, Y = yaw, Z = roll).
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import {
	V, vec, lerp, smooth, makeRandom, finish, paint, transform, ellipsoid, icosphere,
	cone, cylinder, loft, skinBySegments, ruledPanel, extrudeShape,
} from './geometry.js';
import { buildAnimations } from './animations.js';

const rand = makeRandom(7);
const hex = (h) => new THREE.Color(h);
const tmp = new THREE.Color();
const jitter = (c, amount = 0.1) => tmp.copy(c).multiplyScalar(1 - amount / 2 + rand() * amount);

export const PAL = {
	scaleTop: hex(0x22060a), scaleSide: hex(0x701217), scaleHi: hex(0xa3201d),
	belly: hex(0xc99541), bellyDark: hex(0x93652a),
	memDark: hex(0x34060a), memLight: hex(0x9a2a19),
	horn: hex(0xd6c6a2), hornTip: hex(0x241b16), claw: hex(0x15120f), tooth: hex(0xf4ecdc),
	tongue: hex(0x7c1c2a), pupil: hex(0x050505), spikeBase: hex(0x2b080b), spikeTip: hex(0xc9b088),
	tunic: hex(0x2f8a3c), tunicDark: hex(0x1f6a2b), cream: hex(0xeee0bd), skin: hex(0xf3c9a2),
	hair: hex(0xf0cc5a), boot: hex(0x6a4426), belt: hex(0x4d301a), glove: hex(0x7a4f2b),
	eyeBlue: hex(0x1f4fa0), white: hex(0xfafafa), brow: hex(0xc99a2e),
	blade: hex(0xe3e8f0), hilt: hex(0x3d3fae), grip: hex(0x262a7a), gold: hex(0xe2b33f),
	shield: hex(0x2e57b8), emblem: hex(0xcc2a2a), rim: hex(0xcfd5dd),
	fireHot: hex(0xffe9a0), fireMid: hex(0xff7614), fireEnd: hex(0x8a1206),
	leather: hex(0x5b3a1f), blanket: hex(0x23409c), trim: hex(0xd8a93a),
};

function makeMaterials() {
	const std = (o) => new THREE.MeshStandardMaterial({ vertexColors: true, ...o });
	return {
		scales: std({ name: 'DragonScales', roughness: 0.42, metalness: 0.28 }),
		membrane: std({ name: 'WingMembrane', roughness: 0.7, metalness: 0.05, side: THREE.DoubleSide }),
		horn: std({ name: 'HornAndClaw', roughness: 0.38, metalness: 0.1 }),
		cloth: std({ name: 'Cloth', roughness: 0.85 }),
		skin: std({ name: 'Skin', roughness: 0.6 }),
		metal: std({ name: 'Metal', roughness: 0.2, metalness: 0.95 }),
		eye: new THREE.MeshStandardMaterial({
			name: 'DragonEye', color: 0xffd04a, emissive: 0xffa200, emissiveIntensity: 5, roughness: 0.3,
		}),
		fireCore: new THREE.MeshStandardMaterial({
			name: 'FireCore', color: 0xfff0b0, emissive: 0xffc850, emissiveIntensity: 5,
			transparent: true, opacity: 0.9, depthWrite: false,
		}),
		fireOuter: new THREE.MeshBasicMaterial({
			name: 'FireFlame', vertexColors: true, transparent: true, opacity: 0.72, depthWrite: false, side: THREE.DoubleSide,
		}),
	};
}

class Rig {
	constructor() {
		this.objects = {};
		this.world = {};
		this.bones = [];
		this.rigidParts = new Map();
		this.skinParts = new Map();
	}

	add(name, parent, pos, isBone = true) {
		const o = isBone ? new THREE.Bone() : new THREE.Object3D();
		o.name = name;
		const wp = vec(pos);
		this.world[name] = wp;
		if (parent) {
			o.position.copy(wp.clone().sub(this.world[parent]));
			this.objects[parent].add(o);
		} else {
			o.position.copy(wp);
		}
		this.objects[name] = o;
		if (isBone) this.bones.push(o);
		return o;
	}

	bi(name) {
		const i = this.bones.indexOf(this.objects[name]);
		if (i < 0) throw new Error(`unknown bone ${name}`);
		return i;
	}

	rigid(node, mat, geo) {
		if (!this.objects[node]) throw new Error(`unknown node ${node}`);
		const key = `${node}|${mat}`;
		if (!this.rigidParts.has(key)) this.rigidParts.set(key, []);
		this.rigidParts.get(key).push(geo);
	}

	skin(mat, geo) {
		if (!this.skinParts.has(mat)) this.skinParts.set(mat, []);
		this.skinParts.get(mat).push(geo);
	}

	build(group, materials) {
		group.add(this.bones[0]);
		group.updateMatrixWorld(true);
		const skeleton = new THREE.Skeleton(this.bones);
		for (const [mat, geos] of this.skinParts) {
			const geo = mergeGeometries(geos);
			fixNormals(geo);
			const mesh = new THREE.SkinnedMesh(geo, materials[mat]);
			mesh.name = `Dragon_${materials[mat].name}`;
			group.add(mesh);
			mesh.bind(skeleton, new THREE.Matrix4());
		}
		for (const [key, geos] of this.rigidParts) {
			const [node, mat] = key.split('|');
			const geo = mergeGeometries(geos);
			fixNormals(geo);
			const w = this.world[node];
			geo.translate(-w.x, -w.y, -w.z);
			const mesh = new THREE.Mesh(geo, materials[mat]);
			mesh.name = `${node}_${materials[mat].name}`;
			this.objects[node].add(mesh);
		}
	}
}

// Unit-length normals everywhere (degenerate fan centres get a default).
function fixNormals(geo) {
	const n = geo.attributes.normal;
	const v = new THREE.Vector3();
	for (let i = 0; i < n.count; i++) {
		v.fromBufferAttribute(n, i);
		if (v.lengthSq() < 1e-8) v.set(0, 1, 0);
		v.normalize();
		n.setXYZ(i, v.x, v.y, v.z);
	}
}

// Colour gradient along the a->b axis of a part.
function gradient(geo, a, b, c0, c1, pow = 1) {
	a = vec(a); b = vec(b);
	const d = b.clone().sub(a);
	const len2 = d.lengthSq();
	const out = new THREE.Color();
	return paint(geo, (p) => out.copy(c0).lerp(c1, Math.pow(Math.min(1, Math.max(0, p.clone().sub(a).dot(d) / len2)), pow)));
}

const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mirror = (p, sx) => [p[0] * sx, p[1], p[2]];
const SIDES = [[1, '_L'], [-1, '_R']];

// ---------------------------------------------------------------------------
// Dragon skeleton
// ---------------------------------------------------------------------------
const J = {
	hips: [0, 2.3, -1.2], spine1: [0, 2.45, -0.2], spine2: [0, 2.55, 0.8], chest: [0, 2.62, 1.8],
	neck1: [0, 2.86, 2.9], neck2: [0, 3.36, 3.55], neck3: [0, 3.96, 4.0], neck4: [0, 4.5, 4.36],
	neck5: [0, 4.9, 4.74], head: [0, 5.15, 5.15],
};
const TAIL = [
	[0, 2.2, -2.0], [0, 2.02, -2.9], [0, 1.78, -3.8], [0, 1.5, -4.7], [0, 1.22, -5.6],
	[0, 0.97, -6.5], [0, 0.77, -7.4], [0, 0.62, -8.3], [0, 0.52, -9.2], [0, 0.46, -10.0],
];
const TAIL_END = [0, 0.43, -10.8];
const H = J.head;
const h = (x, y, z) => add3(H, [x, y, z]);

const WING = {
	S: [0.55, 3.42, 1.3], E: [2.4, 4.3, 0.9], W: [4.3, 4.6, 1.55], B: [0.7, 2.86, -1.6],
	fingers: [
		{ j: [6.3, 4.72, 0.85], t: [8.9, 4.5, -0.7], r: [0.13, 0.085, 0.02] },
		{ j: [5.8, 4.42, -0.65], t: [7.0, 4.0, -2.9], r: [0.1, 0.07, 0.015] },
		{ j: [5.0, 4.22, -1.25], t: [5.3, 3.7, -4.0], r: [0.1, 0.065, 0.015] },
		{ j: [4.1, 4.1, -1.05], t: [3.4, 3.4, -3.45], r: [0.09, 0.06, 0.015] },
	],
};

function buildSkeleton(R) {
	R.add('root', null, [0, 0, 0]);
	R.add('hips', 'root', J.hips);
	R.add('spine1', 'hips', J.spine1);
	R.add('spine2', 'spine1', J.spine2);
	R.add('chest', 'spine2', J.chest);
	let prev = 'chest';
	for (let k = 1; k <= 5; k++) { R.add(`neck${k}`, prev, J[`neck${k}`]); prev = `neck${k}`; }
	R.add('head', 'neck5', J.head);
	R.add('jaw', 'head', h(0, -0.15, 0.08));
	prev = 'hips';
	TAIL.forEach((p, i) => { R.add(`tail${i + 1}`, prev, p); prev = `tail${i + 1}`; });

	for (const [sx, s] of SIDES) {
		R.add(`upperArm${s}`, 'chest', mirror([0.72, 2.2, 1.75], sx));
		R.add(`foreArm${s}`, `upperArm${s}`, mirror([0.98, 1.3, 1.25], sx));
		R.add(`hand${s}`, `foreArm${s}`, mirror([0.98, 0.35, 1.7], sx));
		R.add(`thigh${s}`, 'hips', mirror([0.78, 2.15, -1.05], sx));
		R.add(`shin${s}`, `thigh${s}`, mirror([1.05, 1.35, -0.35], sx));
		R.add(`foot${s}`, `shin${s}`, mirror([1.05, 0.55, -1.05], sx));
		R.add(`wingUpper${s}`, 'chest', mirror(WING.S, sx));
		R.add(`wingFore${s}`, `wingUpper${s}`, mirror(WING.E, sx));
		R.add(`wingHand${s}`, `wingFore${s}`, mirror(WING.W, sx));
		WING.fingers.forEach((f, i) => {
			R.add(`finger${i + 1}a${s}`, `wingHand${s}`, mirror(WING.W, sx));
			R.add(`finger${i + 1}b${s}`, `finger${i + 1}a${s}`, mirror(f.j, sx));
		});
	}
}

// ---------------------------------------------------------------------------
// Dragon body, neck and tail: one continuous skinned loft
// ---------------------------------------------------------------------------
function buildBody(R) {
	const chain = [TAIL_END, ...[...TAIL].reverse(), J.hips, J.spine1, J.spine2, J.chest,
		J.neck1, J.neck2, J.neck3, J.neck4, J.neck5, J.head];
	const ownerNames = [];
	for (let k = 10; k >= 1; k--) ownerNames.push(`tail${k}`);
	ownerNames.push('hips', 'hips', 'spine1', 'spine2', 'chest', 'neck1', 'neck2', 'neck3', 'neck4', 'neck5');
	const owners = ownerNames.map((n) => R.bi(n));
	const radii = [
		[0.035, 0.035], [0.09, 0.08], [0.13, 0.12], [0.17, 0.16], [0.22, 0.2], [0.28, 0.26], [0.34, 0.32],
		[0.42, 0.4], [0.52, 0.5], [0.65, 0.64], [0.8, 0.82],
		[0.95, 0.98], [1.04, 1.1], [1.05, 1.12], [0.98, 1.05],
		[0.7, 0.76], [0.52, 0.58], [0.43, 0.48], [0.38, 0.43], [0.36, 0.4], [0.34, 0.36],
	];
	const c = new THREE.Color();
	const bodyColor = (u, th, dir, ring) => {
		const s = Math.sin(th);
		const belly = smooth((-s - 0.25) / 0.35);
		c.copy(PAL.scaleSide).lerp(PAL.scaleTop, smooth((s + 0.15) / 0.85));
		// a subtle brighter crimson band along the flanks
		c.lerp(PAL.scaleHi, 0.35 * Math.exp(-Math.pow((s + 0.05) / 0.25, 2)));
		if (belly > 0) c.lerp(ring % 2 === 0 ? PAL.belly : PAL.bellyDark, belly);
		return jitter(c, 0.14);
	};
	const geo = loft(chain, {
		radii, owners, ownerAfter: R.bi('head'), perSeg: 8, radial: 28, ridge: 0.1, color: bodyColor, capStart: true,
	});
	R.skin('scales', geo);

	// dorsal spikes along the spine, skipping the saddle
	const frames = geo.userData.frames;
	const spikeH = [0.07, 0.11, 0.15, 0.19, 0.23, 0.28, 0.32, 0.37, 0.41, 0.45, 0.5,
		0.54, 0.55, 0.55, 0.52, 0.44, 0.38, 0.33, 0.29, 0.26, 0.22];
	let acc = 0;
	for (let i = 1; i < frames.length - 4; i++) {
		const f = frames[i];
		acc += f.c.distanceTo(frames[i - 1].c);
		const hgt = lerp(spikeH[Math.floor(f.u * 20)], spikeH[Math.min(20, Math.floor(f.u * 20) + 1)], (f.u * 20) % 1);
		const spacing = 0.28 + hgt * 0.55;
		if (acc < spacing) continue;
		acc = 0;
		if (f.c.z > 1.35 && f.c.z < 2.85) continue; // rider sits here
		const base = f.c.clone().addScaledVector(f.n, f.ry * 0.93);
		const tip = base.clone().addScaledVector(f.n, hgt).addScaledVector(f.t, -hgt * 0.65);
		const g = cone(base, tip, hgt * 0.42, 0xffffff, { seg: 6, sx: 0.32 });
		gradient(g, base, tip, PAL.spikeBase, PAL.spikeTip, 1.6);
		R.rigid(ownerNames[Math.min(19, Math.floor(f.u * 20))], 'horn', g);
	}
	return geo;
}

// ---------------------------------------------------------------------------
// Legs with clawed feet
// ---------------------------------------------------------------------------
function legColor() {
	const c = new THREE.Color();
	return (u, th, dir) => {
		c.copy(PAL.scaleSide).lerp(PAL.scaleTop, smooth(0.5 + 0.6 * dir.y));
		c.lerp(PAL.scaleHi, 0.25 * Math.max(0, -dir.y));
		return jitter(c, 0.14);
	};
}

function toes(R, bone, ball, sx, angles, len, dirSign = 1) {
	for (const a of angles) {
		const d = V(Math.sin(a) * sx, 0, Math.cos(a) * dirSign);
		const base = vec(ball).addScaledVector(d, 0.05);
		const mid = base.clone().addScaledVector(d, len * 0.55).add(V(0, -0.02, 0));
		const tip = base.clone().addScaledVector(d, len);
		R.rigid(bone, 'scales', loft([base, mid, tip], {
			radii: [[0.08, 0.075], [0.065, 0.058], [0.05, 0.045]], radial: 10, perSeg: 3, color: legColor(),
		}));
		const c1 = tip.clone().addScaledVector(d, 0.13).add(V(0, -0.01, 0));
		const c2 = tip.clone().addScaledVector(d, 0.22).add(V(0, -0.1, 0));
		R.rigid(bone, 'horn', gradient(loft([tip, c1, c2], {
			radii: [[0.05, 0.055], [0.033, 0.036], [0.004, 0.004]], radial: 8, perSeg: 3,
		}), tip, c2, PAL.claw, PAL.claw.clone().multiplyScalar(2.2)));
	}
}

function buildLegs(R) {
	for (const [sx, s] of SIDES) {
		// front legs
		R.skin('scales', loft([
			mirror([0.55, 2.55, 1.8], sx), R.world[`foreArm${s}`].toArray(), R.world[`hand${s}`].toArray(),
			mirror([0.98, 0.12, 2.05], sx),
		], {
			radii: [[0.42, 0.46], [0.25, 0.27], [0.17, 0.17], [0.14, 0.11]],
			owners: [R.bi(`upperArm${s}`), R.bi(`foreArm${s}`), R.bi(`hand${s}`)], ownerBefore: R.bi('chest'),
			up: [0, 0, 1], perSeg: 7, radial: 18, color: legColor(),
		}));
		toes(R, `hand${s}`, mirror([0.98, 0.12, 2.0], sx), sx, [-0.45, -0.15, 0.15, 0.45], 0.38);
		// hind legs
		R.skin('scales', loft([
			mirror([0.6, 2.7, -1.15], sx), R.world[`shin${s}`].toArray(), R.world[`foot${s}`].toArray(),
			mirror([1.05, 0.12, -0.55], sx),
		], {
			radii: [[0.62, 0.66], [0.32, 0.34], [0.2, 0.2], [0.15, 0.12]],
			owners: [R.bi(`thigh${s}`), R.bi(`shin${s}`), R.bi(`foot${s}`)], ownerBefore: R.bi('hips'),
			up: [0, 0, 1], perSeg: 7, radial: 18, color: legColor(),
		}));
		toes(R, `foot${s}`, mirror([1.05, 0.12, -0.6], sx), sx, [-0.4, 0, 0.4], 0.45);
		// dew claw spur on the hock
		const hock = R.world[`foot${s}`];
		const spurTip = hock.clone().add(V(0.05 * sx, -0.15, -0.35));
		R.rigid(`foot${s}`, 'horn', gradient(cone(hock.clone().add(V(0, -0.05, -0.12)), spurTip, 0.07, 0xffffff, { seg: 6 }),
			hock, spurTip, PAL.claw, PAL.hornTip));
	}
}

// ---------------------------------------------------------------------------
// Wings: skinned arm/finger spars plus a scalloped membrane
// ---------------------------------------------------------------------------
function buildWings(R) {
	const memColor = new THREE.Color();
	for (const [sx, s] of SIDES) {
		const M = (p) => vec(mirror(p, sx));
		const S = M(WING.S), E = M(WING.E), W = M(WING.W), B = M(WING.B);
		const fingerCurves = WING.fingers.map((f) => new THREE.CatmullRomCurve3([W, M(f.j), M(f.t)]));

		// arm spar
		R.skin('scales', loft([S, E, W], {
			radii: [[0.26, 0.24], [0.17, 0.16], [0.13, 0.12]], owners: [R.bi(`wingUpper${s}`), R.bi(`wingFore${s}`)],
			ownerBefore: R.bi('chest'), ownerAfter: R.bi(`wingHand${s}`), perSeg: 8, radial: 14, color: legColor(),
		}));
		// finger spars
		WING.fingers.forEach((f, i) => {
			R.skin('scales', loft([W, M(f.j), M(f.t)], {
				radii: [[f.r[0], f.r[0]], [f.r[1], f.r[1]], [f.r[2], f.r[2]]],
				owners: [R.bi(`finger${i + 1}a${s}`), R.bi(`finger${i + 1}b${s}`)], perSeg: 8, radial: 10, color: legColor(),
			}));
		});
		// wrist knuckle, thumb claw and elbow spur
		R.rigid(`wingHand${s}`, 'scales', ellipsoid(W, [0.17, 0.15, 0.17], PAL.scaleTop));
		const thumbTip = W.clone().add(V(0.15 * sx, 0.25, 0.55));
		R.rigid(`wingHand${s}`, 'horn', gradient(loft([W, W.clone().add(V(0.08 * sx, 0.15, 0.3)), thumbTip], {
			radii: [[0.08, 0.08], [0.055, 0.055], [0.004, 0.004]], radial: 8, perSeg: 4,
		}), W, thumbTip, PAL.horn, PAL.hornTip));
		const spurTip = E.clone().add(V(0.15 * sx, 0.12, -0.55));
		R.rigid(`wingFore${s}`, 'horn', gradient(cone(E, spurTip, 0.09, 0xffffff, { seg: 6 }), E, spurTip, PAL.horn, PAL.hornTip));
		R.rigid(`wingFore${s}`, 'scales', ellipsoid(E, [0.19, 0.17, 0.19], PAL.scaleTop));

		// membrane panels between consecutive fingers + the inner panel to the body
		const panelColor = (uu, v) => {
			const e = Math.sin(Math.PI * v);
			memColor.copy(PAL.memDark).lerp(PAL.memLight, smooth(0.15 + 0.9 * e * (0.35 + 0.65 * uu)));
			if (uu > 0.9) memColor.lerp(PAL.memDark, (uu - 0.9) * 6);
			return jitter(memColor, 0.06);
		};
		const panels = [];
		for (let i = 0; i < 3; i++) {
			const A = fingerCurves[i], Bc = fingerCurves[i + 1];
			panels.push(ruledPanel((u) => A.getPointAt(u), (u) => Bc.getPointAt(u), {
				nu: 16, nv: 10, scallop: i === 0 ? 0.1 : 0.14, color: panelColor,
			}));
		}
		const arm = new THREE.CatmullRomCurve3([S, E, W]);
		const f4 = fingerCurves[3];
		const tmpA = new THREE.Vector3(), tmpB = new THREE.Vector3();
		panels.push(ruledPanel(
			(u) => tmpA.copy(S).lerp(B, u).clone(),
			(u) => f4.getPointAt(u),
			{
				nu: 16, nv: 16, scallop: 0.12, color: (uu, v) => panelColor(uu, 1 - v * 0.8),
				extra: (u, v) => arm.getPointAt(v).sub(tmpB.copy(S).lerp(W, v)).multiplyScalar((1 - u) * (1 - u)),
			},
		));
		const segs = [
			{ bone: R.bi(`wingUpper${s}`), a: S, b: E },
			{ bone: R.bi(`wingFore${s}`), a: E, b: W },
			{ bone: R.bi('spine2'), a: S, b: S.clone().lerp(B, 0.2) },
			{ bone: R.bi('spine1'), a: S.clone().lerp(B, 0.2), b: S.clone().lerp(B, 0.55) },
			{ bone: R.bi('hips'), a: S.clone().lerp(B, 0.55), b: B },
		];
		WING.fingers.forEach((f, i) => {
			segs.push({ bone: R.bi(`finger${i + 1}a${s}`), a: W, b: M(f.j) });
			segs.push({ bone: R.bi(`finger${i + 1}b${s}`), a: M(f.j), b: M(f.t) });
		});
		for (const p of panels) R.skin('membrane', skinBySegments(p, segs));
	}
}

// ---------------------------------------------------------------------------
// Head, horns, jaw, eyes and the fire breath rig
// ---------------------------------------------------------------------------
function buildHead(R) {
	const headColor = () => {
		const c = new THREE.Color();
		return (u, th) => {
			const s = Math.sin(th);
			c.copy(PAL.scaleSide).lerp(PAL.scaleTop, smooth((s + 0.2) / 0.9));
			if (s < -0.55) c.lerp(PAL.belly, smooth((-s - 0.55) / 0.3) * 0.8);
			return jitter(c, 0.12);
		};
	};
	R.rigid('head', 'scales', ellipsoid(h(0, 0.1, 0.25), [0.42, 0.36, 0.55], (p) => jitter(PAL.scaleSide.clone().lerp(PAL.scaleTop, smooth((p.y - H[1]) / 0.4)), 0.12)));
	// upper jaw / snout
	R.rigid('head', 'scales', loft([h(0, 0.05, 0.3), h(0, -0.02, 0.8), h(0, -0.08, 1.3), h(0, -0.13, 1.7), h(0, -0.15, 1.9)], {
		radii: [[0.36, 0.27], [0.3, 0.21], [0.24, 0.17], [0.18, 0.13], [0.07, 0.065]], square: 2.6, up: [0, 1, 0],
		perSeg: 6, radial: 22, color: headColor(), capStart: false,
	}));
	// brows (angry, sloping forward/down)
	for (const sx of [1, -1]) {
		R.rigid('head', 'scales', ellipsoid(h(0.25 * sx, 0.33, 0.6), [0.12, 0.075, 0.32], PAL.scaleTop, { rot: [0.32, -0.28 * sx, 0.12 * sx] }));
		R.rigid('head', 'eye', ellipsoid(h(0.27 * sx, 0.215, 0.68), [0.075, 0.068, 0.085], 0xffffff));
		const pd = V(0.85 * sx, 0.05, 0.52).normalize().multiplyScalar(0.07);
		R.rigid('head', 'horn', ellipsoid(vec(h(0.27 * sx, 0.215, 0.68)).add(pd), [0.014, 0.05, 0.014], PAL.pupil));
		// nostrils
		R.rigid('head', 'horn', ellipsoid(h(0.075 * sx, -0.075, 1.86), [0.035, 0.025, 0.03], PAL.pupil));
		// main horns sweeping back
		const hornPts = [h(0.22 * sx, 0.36, 0.05), h(0.44 * sx, 0.7, -0.45), h(0.56 * sx, 0.9, -1.05), h(0.6 * sx, 1.05, -1.6), h(0.66 * sx, 1.38, -2.0)];
		R.rigid('head', 'horn', gradient(loft(hornPts, {
			radii: (u) => [0.15 * (1 - u) + 0.004, 0.15 * (1 - u) + 0.004], radial: 12, perSeg: 6,
		}), hornPts[0], hornPts[4], PAL.horn, PAL.hornTip, 1.5));
		const horn2 = [h(0.32 * sx, 0.18, -0.02), h(0.62 * sx, 0.2, -0.45), h(0.82 * sx, 0.14, -0.85), h(0.94 * sx, 0.26, -1.18)];
		R.rigid('head', 'horn', gradient(loft(horn2, {
			radii: (u) => [0.085 * (1 - u) + 0.003, 0.085 * (1 - u) + 0.003], radial: 10, perSeg: 5,
		}), horn2[0], horn2[3], PAL.horn, PAL.hornTip, 1.5));
		// cheek frills
		[[0.0, 0.15, 1.0], [-0.12, 0.3, 0.75], [0.12, 0.02, 0.85]].forEach(([y, z, k]) => {
			const base = vec(h(0.36 * sx, y, z));
			const tip = base.clone().add(V(0.28 * sx * k, -0.04, -0.5 * k));
			R.rigid('head', 'horn', gradient(cone(base, tip, 0.07, 0xffffff, { seg: 6, sz: 0.5 }), base, tip, PAL.spikeBase, PAL.spikeTip, 1.4));
		});
		// upper teeth + fangs
		for (let k = 0; k < 7; k++) {
			const f = k / 6;
			const base = vec(h(lerp(0.22, 0.12, f) * sx, -0.2, lerp(0.62, 1.72, f)));
			R.rigid('head', 'horn', cone(base, base.clone().add(V(0, -0.11 - 0.03 * Math.sin(f * 3), 0.01)), 0.035, PAL.tooth, { seg: 6 }));
		}
		const fang = vec(h(0.195 * sx, -0.19, 1.44));
		R.rigid('head', 'horn', cone(fang, fang.clone().add(V(0.01 * sx, -0.22, 0.03)), 0.045, PAL.tooth, { seg: 8 }));
	}
	// nose horn + head crest
	R.rigid('head', 'horn', gradient(cone(h(0, -0.03, 1.42), h(0, 0.24, 1.6), 0.07, 0xffffff, { seg: 8 }), h(0, -0.03, 1.42), h(0, 0.24, 1.6), PAL.horn, PAL.hornTip));
	[[0.43, 0.45, 0.16], [0.44, 0.2, 0.2], [0.4, -0.06, 0.18]].forEach(([y, z, hh]) => {
		const base = vec(h(0, y, z));
		const tip = base.clone().add(V(0, hh, -hh * 0.7));
		R.rigid('head', 'horn', gradient(cone(base, tip, hh * 0.45, 0xffffff, { seg: 6, sx: 0.35 }), base, tip, PAL.spikeBase, PAL.spikeTip, 1.5));
	});

	// lower jaw
	R.rigid('jaw', 'scales', loft([h(0, -0.23, 0.05), h(0, -0.29, 0.6), h(0, -0.31, 1.2), h(0, -0.31, 1.65), h(0, -0.29, 1.8)], {
		radii: [[0.33, 0.14], [0.27, 0.11], [0.21, 0.09], [0.15, 0.07], [0.07, 0.045]], square: 2.4,
		perSeg: 6, radial: 20, color: headColor(),
	}));
	R.rigid('jaw', 'skin', ellipsoid(h(0, -0.215, 0.95), [0.13, 0.035, 0.55], PAL.tongue));
	for (const sx of [1, -1]) {
		for (let k = 0; k < 6; k++) {
			const f = k / 5;
			const base = vec(h(lerp(0.2, 0.1, f) * sx, -0.21 - 0.02 * f, lerp(0.7, 1.6, f)));
			R.rigid('jaw', 'horn', cone(base, base.clone().add(V(0, 0.1, 0.01)), 0.03, PAL.tooth, { seg: 6 }));
		}
	}

	// fire breath: scaled to ~0 except while attacking
	const mouth = h(0, -0.2, 1.75);
	const fire = R.add('Fire', 'head', mouth, false);
	fire.scale.setScalar(0.001);
	const flame = (phase, amp = 0.18) => (u, th) => 1 + amp * Math.sin(th * 5 + u * 17 + phase) * Math.sin(u * Math.PI);
	const fireC = new THREE.Color();
	const fireRamp = (z) => {
		const k = Math.min(1, Math.max(0, z / 6.2));
		return k < 0.45 ? fireC.copy(PAL.fireHot).lerp(PAL.fireMid, k / 0.45) : fireC.copy(PAL.fireMid).lerp(PAL.fireEnd, (k - 0.45) / 0.55);
	};
	const mz = mouth[2];
	// glowing core (emissive, blooms) wrapped in an unlit flame whose colour runs yellow -> orange -> dark red
	R.rigid('Fire', 'fireCore', loft(zs([0.02, 0.9, 2.0, 3.1, 3.7]), {
		radii: [[0.05, 0.05], [0.24, 0.22], [0.36, 0.33], [0.24, 0.22], [0.04, 0.04]], radial: 14, perSeg: 6,
		noise: flame(0.5), color: 0xffffff,
	}));
	R.rigid('Fire', 'fireOuter', loft(zs([0.05, 1.4, 3.2, 5.0, 6.2]), {
		radii: [[0.1, 0.1], [0.6, 0.55], [1.05, 0.95], [0.85, 0.8], [0.12, 0.12]], radial: 22, perSeg: 7,
		noise: flame(2.0, 0.24), color: (u, th, d, i, p) => fireRamp(p.z - mz),
	}));
	// flame tongues licking out of the main jet
	for (let k = 0; k < 7; k++) {
		const a = k * 2.4, r = 0.35 + 0.25 * rand();
		const start = 0.8 + rand() * 1.8, len = 1.6 + rand() * 1.8;
		const pts = [0, 0.4, 0.8, 1].map((f) => add3(mouth, [Math.cos(a) * r * (0.6 + f * 1.4) + 0.2 * Math.sin(f * 5 + k), Math.sin(a) * r * (0.6 + f * 1.4), start + f * len]));
		R.rigid('Fire', 'fireOuter', loft(pts, {
			radii: (u) => [0.28 * Math.sin(Math.PI * Math.min(1, u * 1.4)) + 0.01, 0.22 * Math.sin(Math.PI * Math.min(1, u * 1.4)) + 0.01],
			radial: 10, perSeg: 4, color: (u, th, d, i, p) => fireRamp(p.z - mz + 0.8),
		}));
	}
	for (let i = 0; i < 8; i++) {
		const name = `Fireball_${i}`;
		const p = add3(mouth, [0, 0, 0.5 + i * 0.7]);
		R.add(name, 'Fire', p, false);
		R.rigid(name, 'fireOuter', icosphere(p, 0.42, (q) => fireRamp(3.2 + (q.y - p[1]) * 3), 2));
	}
	function zs(list) { return list.map((z) => add3(mouth, [0, 0, z])); }
}

function buildTailBlade(R) {
	const sh = new THREE.Shape();
	sh.moveTo(0, -0.05);
	sh.lineTo(0.42, 0.32);
	sh.lineTo(0.14, 0.3);
	sh.lineTo(0, 1.0);
	sh.lineTo(-0.14, 0.3);
	sh.lineTo(-0.42, 0.32);
	sh.closePath();
	const g = extrudeShape(sh, 0.05, 0xffffff, 0.02);
	g.rotateX(-Math.PI / 2);
	const end = vec(TAIL_END);
	g.translate(end.x, end.y - 0.025, end.z + 0.15);
	gradient(g, end, end.clone().add(V(0, 0, -1)), PAL.spikeBase, PAL.spikeTip, 1.4);
	R.rigid('tail10', 'horn', g);
}

// ---------------------------------------------------------------------------
// Saddle and the Link-style rider
// ---------------------------------------------------------------------------
function frameAtZ(body, z) {
	let best = null;
	for (const f of body.userData.frames) {
		if (f.u < 0.5 || f.u > 0.8) continue;
		if (!best || Math.abs(f.c.z - z) < Math.abs(best.c.z - z)) best = f;
	}
	return best;
}

// A patch that hugs the body surface (for saddle blanket and girth strap).
function bodyShell(body, z0, z1, th0, th1, offset, color, nu = 10, nv = 18) {
	const pos = [], idx = [];
	for (let i = 0; i <= nu; i++) {
		const f = frameAtZ(body, lerp(z0, z1, i / nu));
		for (let j = 0; j <= nv; j++) {
			const th = lerp(th0, th1, j / nv);
			const p = f.c.clone().addScaledVector(f.side, Math.cos(th) * (f.rx + offset)).addScaledVector(f.n, Math.sin(th) * (f.ry * 1.03 + offset));
			pos.push(p.x, p.y, p.z);
		}
	}
	for (let i = 0; i < nu; i++) {
		for (let j = 0; j < nv; j++) {
			const a = i * (nv + 1) + j, b = a + 1, c = a + nv + 1, d = c + 1;
			idx.push(a, b, c, b, d, c);
		}
	}
	const g = new THREE.BufferGeometry();
	g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
	g.setIndex(idx);
	g.computeVertexNormals();
	return finish(g, color);
}

function buildRider(R, body) {
	const Z0 = 2.0;
	const seatF = frameAtZ(body, Z0);
	const top = seatF.c.y + seatF.ry;
	const surfY = (x, z) => {
		const f = frameAtZ(body, z);
		return f.c.y + f.ry * Math.sqrt(Math.max(0, 1 - (x / f.rx) ** 2));
	};

	// --- saddle (rigid on chest) ---
	const trimC = new THREE.Color();
	R.rigid('chest', 'cloth', bodyShell(body, Z0 - 0.55, Z0 + 0.55, Math.PI / 2 - 1.05, Math.PI / 2 + 1.05, 0.035, (p) => {
		const edge = Math.abs(p.x) > 0.8 || Math.abs(p.z - Z0) > 0.47;
		return trimC.copy(edge ? PAL.trim : PAL.blanket);
	}));
	R.rigid('chest', 'cloth', bodyShell(body, Z0 - 0.08, Z0 + 0.08, 0, Math.PI * 2, 0.045, PAL.leather, 3, 40));
	R.rigid('chest', 'cloth', ellipsoid([0, top + 0.07, Z0], [0.38, 0.1, 0.42], PAL.leather));
	R.rigid('chest', 'cloth', ellipsoid([0, top + 0.12, Z0 - 0.36], [0.3, 0.13, 0.08], PAL.leather));
	R.rigid('chest', 'cloth', cylinder([0, top + 0.05, Z0 + 0.42], [0, top + 0.32, Z0 + 0.5], 0.055, 0.04, PAL.leather));
	R.rigid('chest', 'metal', ellipsoid([0, top + 0.34, Z0 + 0.5], [0.06, 0.04, 0.06], PAL.gold));

	// --- rider rig ---
	// The rider is designed at 1:1 around the seat point P0 and then scaled up
	// slightly (stylised hero proportions) so he reads well next to the dragon.
	const K = 1.22;
	const P0 = [0, top + 0.15, Z0];
	const P0v = vec(P0);
	const scaleM = new THREE.Matrix4().makeTranslation(P0v.x, P0v.y, P0v.z)
		.multiply(new THREE.Matrix4().makeScale(K, K, K))
		.multiply(new THREE.Matrix4().makeTranslation(-P0v.x, -P0v.y, -P0v.z));
	const design = {};
	const rig = (name, parent, p) => { design[name] = vec(p); return R.add(name, parent, vec(p).applyMatrix4(scaleM), false); };
	const put = (node, mat, geo) => R.rigid(node, mat, geo.applyMatrix4(scaleM));
	const toDesign = (p) => vec(p).sub(P0v).divideScalar(K).add(P0v).toArray();
	const L = (x, y, z) => [P0[0] + x, P0[1] + y, P0[2] + z];
	rig('Link_Root', 'chest', P0);
	rig('Link_Spine', 'Link_Root', L(0, 0.14, 0));
	rig('Link_Head', 'Link_Spine', L(0, 0.65, 0.035));
	const hc = vec(L(0, 0.81, 0.05));
	const hd = (x, y, z) => hc.clone().add(V(x, y, z));
	rig('Link_Hat2', 'Link_Head', hd(0, 0.2, -0.07));
	rig('Link_Hat3', 'Link_Hat2', hd(0, 0.22, -0.36));
	rig('Link_Shoulder_L', 'Link_Spine', L(0.2, 0.53, 0.03));
	rig('Link_Elbow_L', 'Link_Shoulder_L', L(0.3, 0.3, 0.13));
	rig('Link_Hand_L', 'Link_Elbow_L', L(0.28, 0.3, 0.41));
	rig('Link_Shoulder_R', 'Link_Spine', L(-0.2, 0.53, 0.03));
	rig('Link_Elbow_R', 'Link_Shoulder_R', L(-0.31, 0.31, 0.1));

	const tunicC = new THREE.Color();
	// legs straddling the dragon (tights + boots)
	for (const sx of [1, -1]) {
		const hip = L(0.12 * sx, 0.04, 0.0);
		const knee = toDesign([0.5 * sx, surfY(0.5, Z0 + 0.32) + 0.11, Z0 + 0.32]);
		const mid = toDesign([0.73 * sx, surfY(0.73, Z0 + 0.28) + 0.1, Z0 + 0.28]);
		const ankle = toDesign([0.88 * sx, surfY(0.88, Z0 + 0.24) + 0.09, Z0 + 0.24]);
		put('Link_Root', 'cloth', loft([hip, knee, mid, ankle], {
			radii: [[0.09, 0.09], [0.075, 0.075], [0.075, 0.075], [0.068, 0.068]], perSeg: 6, radial: 12, up: [0, 0, 1],
			color: (u) => (u > 0.5 ? PAL.boot : PAL.cream),
		}));
		put('Link_Root', 'cloth', loft([lerpArr(knee, mid, 0.55), lerpArr(knee, mid, 0.9)], {
			radii: [[0.088, 0.088], [0.085, 0.085]], radial: 12, perSeg: 2, color: PAL.boot,
		}));
		put('Link_Root', 'cloth', ellipsoid(add3(ankle, [0.02 * sx, -0.03, 0.1]), [0.065, 0.06, 0.15], PAL.boot, { rot: [0, 0, -0.9 * sx] }));
	}
	// pelvis, tunic skirt, belt
	put('Link_Root', 'cloth', ellipsoid(L(0, 0.06, 0), [0.17, 0.1, 0.13], PAL.cream));
	put('Link_Root', 'cloth', loft([L(0, 0.2, 0), L(0, 0.04, 0.01), L(0, -0.06, 0.02)], {
		radii: [[0.16, 0.12], [0.235, 0.19], [0.27, 0.22]], perSeg: 4, radial: 20, up: [0, 0, 1],
		color: (u) => tunicC.copy(PAL.tunic).lerp(PAL.tunicDark, u),
	}));
	put('Link_Spine', 'cloth', ellipsoid(L(0, 0.17, 0.0), [0.168, 0.035, 0.128], PAL.belt));
	put('Link_Spine', 'metal', ellipsoid(L(0, 0.17, 0.125), [0.045, 0.035, 0.015], PAL.gold));
	// torso
	put('Link_Spine', 'cloth', loft([L(0, 0.12, 0), L(0, 0.3, 0.01), L(0, 0.5, 0.03), L(0, 0.62, 0.035)], {
		radii: [[0.15, 0.115], [0.165, 0.12], [0.2, 0.125], [0.085, 0.075]], perSeg: 5, radial: 20, up: [0, 0, 1],
		color: (u, th, dir) => (u > 0.82 && dir.z > 0.55 ? PAL.cream : tunicC.copy(PAL.tunic).lerp(PAL.tunicDark, 0.3 - 0.3 * u)),
	}));
	// diagonal sword strap
	put('Link_Spine', 'cloth', loft([L(0.16, 0.52, 0.1), L(0.02, 0.38, 0.135), L(-0.13, 0.22, 0.115)], {
		radii: [[0.03, 0.012], [0.03, 0.012], [0.03, 0.012]], perSeg: 4, radial: 8, up: [0, 0, 1], color: PAL.belt,
	}));
	put('Link_Spine', 'skin', cylinder(L(0, 0.58, 0.035), L(0, 0.72, 0.04), 0.055, 0.05, PAL.skin));

	// head
	put('Link_Head', 'skin', ellipsoid(hc, [0.145, 0.16, 0.15], PAL.skin));
	put('Link_Head', 'skin', cone(hd(0, -0.02, 0.13), hd(0, -0.045, 0.19), 0.024, PAL.skin, { seg: 8 }));
	for (const sx of [1, -1]) {
		put('Link_Head', 'skin', ellipsoid(hd(0.055 * sx, 0.0, 0.132), [0.03, 0.034, 0.012], PAL.white));
		put('Link_Head', 'skin', ellipsoid(hd(0.055 * sx, -0.003, 0.14), [0.019, 0.026, 0.01], PAL.eyeBlue));
		put('Link_Head', 'skin', ellipsoid(hd(0.058 * sx, 0.048, 0.137), [0.032, 0.008, 0.012], PAL.brow, { rot: [0, 0, 0.25 * sx] }));
		put('Link_Head', 'skin', cone(hd(0.125 * sx, 0.0, -0.01), hd(0.33 * sx, 0.075, -0.08), 0.042, PAL.skin, { seg: 8, sz: 0.45 }));
		put('Link_Head', 'cloth', ellipsoid(hd(0.123 * sx, -0.03, 0.065), [0.026, 0.085, 0.035], PAL.hair, { rot: [0.15, 0, 0.08 * sx] }));
	}
	put('Link_Head', 'skin', ellipsoid(hd(0, -0.078, 0.133), [0.026, 0.006, 0.008], hex(0x9a4a3a)));
	put('Link_Head', 'cloth', ellipsoid(hd(0, 0.05, -0.04), [0.157, 0.148, 0.15], PAL.hair));
	[-0.085, -0.03, 0.03, 0.085].forEach((x) => {
		put('Link_Head', 'cloth', cone(hd(x, 0.125, 0.085), hd(x * 1.25, 0.03, 0.15), 0.04, PAL.hair, { seg: 7 }));
	});
	// hat (three segments so the tip can flap)
	put('Link_Head', 'cloth', loft([hd(0, 0.085, -0.01), hd(0, 0.2, -0.07)], {
		radii: [[0.16, 0.16], [0.12, 0.12]], perSeg: 3, radial: 18, color: PAL.tunic, up: [0, 0, 1],
	}));
	put('Link_Hat2', 'cloth', ellipsoid(hd(0, 0.2, -0.07), [0.12, 0.12, 0.12], PAL.tunic));
	put('Link_Hat2', 'cloth', loft([hd(0, 0.2, -0.07), hd(0, 0.25, -0.22), hd(0, 0.22, -0.36)], {
		radii: [[0.12, 0.12], [0.085, 0.085], [0.06, 0.06]], perSeg: 4, radial: 16, color: PAL.tunic, up: [0, 1, 0],
	}));
	put('Link_Hat3', 'cloth', ellipsoid(hd(0, 0.22, -0.36), [0.06, 0.06, 0.06], PAL.tunic));
	put('Link_Hat3', 'cloth', loft([hd(0, 0.22, -0.36), hd(0, 0.16, -0.5), hd(0, 0.05, -0.6)], {
		radii: [[0.06, 0.06], [0.038, 0.038], [0.006, 0.006]], perSeg: 4, radial: 12, color: PAL.tunicDark, up: [0, 1, 0],
	}));

	// arms
	for (const sx of [1, -1]) {
		const s = sx > 0 ? '_L' : '_R';
		const sh = design[`Link_Shoulder${s}`].toArray();
		const el = design[`Link_Elbow${s}`].toArray();
		const wr = sx > 0 ? L(0.28, 0.3, 0.4) : L(-0.33, 0.29, 0.34);
		put(`Link_Shoulder${s}`, 'cloth', ellipsoid(sh, [0.072, 0.072, 0.072], PAL.tunic));
		put(`Link_Shoulder${s}`, 'cloth', loft([sh, lerpArr(sh, el, 0.5), el], {
			radii: [[0.066, 0.066], [0.058, 0.058], [0.052, 0.052]], perSeg: 4, radial: 12, up: [0, 0, 1],
			color: (u) => (u < 0.45 ? PAL.tunic : PAL.cream),
		}));
		put(`Link_Elbow${s}`, 'cloth', ellipsoid(el, [0.053, 0.053, 0.053], PAL.cream));
		put(`Link_Elbow${s}`, 'cloth', loft([el, lerpArr(el, wr, 0.5), wr], {
			radii: [[0.05, 0.05], [0.047, 0.047], [0.046, 0.046]], perSeg: 4, radial: 12, up: [0, 1, 0],
			color: (u) => (u < 0.55 ? PAL.cream : PAL.glove),
		}));
		put(`Link_Elbow${s}`, 'cloth', loft([lerpArr(el, wr, 0.6), lerpArr(el, wr, 0.78)], {
			radii: [[0.058, 0.058], [0.055, 0.055]], perSeg: 2, radial: 12, color: PAL.glove,
		}));
	}
	// left hand + sword (classic left-handed hero)
	const fist = vec(L(0.28, 0.3, 0.44));
	put('Link_Hand_L', 'cloth', ellipsoid(fist, [0.05, 0.056, 0.062], PAL.glove));
	const d = V(0.05, 0.8, 0.6).normalize();
	const w = V(1, 0, 0).addScaledVector(d, -d.x).normalize();
	const at = (k) => fist.clone().addScaledVector(d, k);
	put('Link_Hand_L', 'cloth', cylinder(at(-0.1), at(0.1), 0.022, 0.022, PAL.grip, 10));
	put('Link_Hand_L', 'metal', ellipsoid(at(-0.12), [0.034, 0.034, 0.034], PAL.hilt));
	const guard = at(0.11);
	for (const k of [1, -1]) {
		const tip = guard.clone().addScaledVector(w, 0.15 * k).addScaledVector(d, 0.07);
		put('Link_Hand_L', 'metal', cone(guard, tip, 0.032, PAL.hilt, { seg: 6 }));
	}
	put('Link_Hand_L', 'metal', ellipsoid(guard, [0.05, 0.03, 0.03], PAL.hilt));
	put('Link_Hand_L', 'metal', ellipsoid(guard.clone().add(V(0, 0, 0.022)), [0.016, 0.016, 0.016], PAL.gold));
	const bladeUp = new THREE.Vector3().crossVectors(w, d);
	put('Link_Hand_L', 'metal', loft([at(0.12), at(0.6), at(0.95), at(1.06)], {
		radii: [[0.034, 0.008], [0.032, 0.008], [0.028, 0.007], [0.003, 0.002]], square: 1.3, perSeg: 3, radial: 8,
		up: bladeUp, color: PAL.blade,
	}));
	// right hand + shield
	put('Link_Elbow_R', 'cloth', ellipsoid(L(-0.33, 0.29, 0.38), [0.05, 0.056, 0.06], PAL.glove));
	put('Link_Elbow_R', 'metal', shield(vec(L(-0.43, 0.32, 0.22))));
	put('Link_Elbow_R', 'cloth', shieldFace(vec(L(-0.43, 0.32, 0.22))));
}

const lerpArr = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];

function heater(scale = 1) {
	const s = new THREE.Shape();
	s.moveTo(-0.22 * scale, 0.26 * scale);
	s.quadraticCurveTo(0, 0.31 * scale, 0.22 * scale, 0.26 * scale);
	s.lineTo(0.22 * scale, 0.02 * scale);
	s.quadraticCurveTo(0.2 * scale, -0.2 * scale, 0, -0.32 * scale);
	s.quadraticCurveTo(-0.2 * scale, -0.2 * scale, -0.22 * scale, 0.02 * scale);
	s.closePath();
	return s;
}

function placeShield(g, center) {
	g.rotateY(-Math.PI / 2 + 0.3);
	g.translate(center.x, center.y, center.z);
	return g;
}

// silver rim (sits behind the blue face so it reads as a border)
function shield(center) {
	const g = extrudeShape(heater(1.09), 0.025, PAL.rim, 0.01);
	g.translate(0, 0, -0.012);
	return placeShield(g, center);
}

function shieldFace(center) {
	const face = extrudeShape(heater(1), 0.035, PAL.shield, 0.01);
	const bird = new THREE.Shape();
	bird.moveTo(0, -0.13);
	bird.lineTo(0.17, 0.07);
	bird.lineTo(0.095, 0.08);
	bird.lineTo(0, -0.02);
	bird.lineTo(-0.095, 0.08);
	bird.lineTo(-0.17, 0.07);
	bird.closePath();
	const emblem = extrudeShape(bird, 0.012, PAL.emblem, 0.004);
	emblem.translate(0, -0.02, 0.047);
	const strip = ellipsoid([0, 0.17, 0.05], [0.16, 0.012, 0.006], PAL.rim);
	return placeShield(mergeGeometries([face, emblem, strip]), center);
}

// ---------------------------------------------------------------------------
export function buildDragonRider() {
	const R = new Rig();
	const materials = makeMaterials();
	buildSkeleton(R);
	const body = buildBody(R);
	buildLegs(R);
	buildWings(R);
	buildHead(R);
	buildTailBlade(R);
	buildRider(R, body);

	// Skeleton root and skinned meshes sit directly in the scene (glTF wants skinned mesh nodes at the root).
	const scene = new THREE.Scene();
	scene.name = 'DragonRider';
	R.build(scene, materials);
	const animations = buildAnimations(R.objects);
	return { scene, animations };
}
