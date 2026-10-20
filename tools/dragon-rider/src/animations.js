// Keyframed animation clips: "Idle", "Angriff" (attack with fire breath) and
// "Flug" (flight). Poses are authored as functions of time and sampled at
// FPS; every clip loops seamlessly and carries a track for every animated
// node so switching clips never leaves a node in a stale pose.
import * as THREE from 'three';
import { smooth } from './geometry.js';

const FPS = 30;
const TAU = Math.PI * 2;
const SIDES = [[1, '_L'], [-1, '_R']];

class Pose {
	constructor() { this.r = {}; this.p = {}; this.s = {}; }

	rot(name, x = 0, y = 0, z = 0) {
		const a = this.r[name] || (this.r[name] = [0, 0, 0]);
		a[0] += x; a[1] += y; a[2] += z;
		return this;
	}

	// Mirrored rotation for left/right limbs (sx = +1 left, -1 right).
	rotS(base, sx, x = 0, y = 0, z = 0) {
		return this.rot(base + (sx > 0 ? '_L' : '_R'), x, sx * y, sx * z);
	}

	pos(name, x = 0, y = 0, z = 0) {
		const a = this.p[name] || (this.p[name] = [0, 0, 0]);
		a[0] += x; a[1] += y; a[2] += z;
		return this;
	}

	scale(name, x, y = x, z = x) { this.s[name] = [x, y, z]; return this; }

	// this += other * w   (scales are blended, not added)
	addWeighted(other, w) {
		for (const [k, v] of Object.entries(other.r)) this.rot(k, v[0] * w, v[1] * w, v[2] * w);
		for (const [k, v] of Object.entries(other.p)) this.pos(k, v[0] * w, v[1] * w, v[2] * w);
		for (const [k, v] of Object.entries(other.s)) {
			const a = this.s[k] || (this.s[k] = [0, 0, 0]);
			a[0] += v[0] * w; a[1] += v[1] * w; a[2] += v[2] * w;
		}
		return this;
	}
}

// Eased blend through a list of [time, poseBuilder] keys.
function keyed(t, keys) {
	let i = 0;
	while (i < keys.length - 2 && t > keys[i + 1][0]) i++;
	const [t0, a] = keys[i];
	const [t1, b] = keys[i + 1];
	const f = smooth((t - t0) / (t1 - t0));
	const out = new Pose();
	out.addWeighted(a(), 1 - f).addWeighted(b(), f);
	return out;
}

// ---------------------------------------------------------------------------
// Shared poses
// ---------------------------------------------------------------------------
function wingsFolded(P, k = 1) {
	for (const [sx] of SIDES) {
		P.rotS('wingUpper', sx, -0.1 * k, 0.4 * k, 0.6 * k);
		P.rotS('wingFore', sx, 0.1 * k, -1.05 * k, -0.2 * k);
		for (let i = 1; i <= 4; i++) {
			P.rotS(`finger${i}a`, sx, 0.0, (0.62 + 0.06 * i) * k, -0.18 * k);
			P.rotS(`finger${i}b`, sx, 0, 0.12 * k, -0.06 * k);
		}
	}
	return P;
}

function wingsSpread(P, raise = 0.35, sweep = -0.1) {
	for (const [sx] of SIDES) {
		P.rotS('wingUpper', sx, 0, sweep, raise);
		P.rotS('wingFore', sx, 0, 0.0, -0.08);
		for (let i = 1; i <= 4; i++) P.rotS(`finger${i}a`, sx, 0, -0.04 * i, -0.04);
	}
	return P;
}

function standBase() {
	const P = new Pose();
	wingsFolded(P);
	P.rot('neck1', 0.04).rot('neck2', 0.02).rot('neck4', -0.03).rot('head', 0.12);
	for (let k = 1; k <= 10; k++) P.rot(`tail${k}`, 0, 0.055, 0);
	P.scale('Fire', 0.001);
	return P;
}

function fireballs(P, t, active) {
	for (let i = 0; i < 8; i++) {
		const name = `Fireball_${i}`;
		if (!active) { P.scale(name, 1); continue; }
		const ph = ((t / 0.5) + i / 8) % 1;
		// rest position is 0.5 + 0.7 i along +Z (fire-local)
		P.pos(name, 0.28 * Math.sin(i * 2.3) * ph, -0.6 * ph * ph, 0.3 + ph * 6.2 - (0.5 + i * 0.7));
		P.scale(name, (0.3 + 1.5 * ph) * Math.pow(Math.sin(Math.PI * ph), 0.6));
	}
}

// ---------------------------------------------------------------------------
// Idle — 4 s breathing loop with a curious look-around
// ---------------------------------------------------------------------------
function idle(t) {
	const D = 4, w = TAU / D;
	const P = standBase();
	const br = Math.sin(w * t);
	P.rot('spine2', 0.01 * br).rot('chest', -0.012 * br);
	for (let k = 1; k <= 5; k++) P.rot(`neck${k}`, 0.025 * Math.sin(w * t - k * 0.45), 0.045 * Math.sin(w * t + 0.5 + k * 0.3));
	P.rot('head', 0.05 * Math.sin(2 * w * t), 0.2 * Math.sin(w * t + 0.8), 0.05 * Math.sin(w * t));
	P.rot('jaw', 0.05 + 0.07 * (0.5 - 0.5 * Math.cos(2 * w * t)));
	for (let k = 1; k <= 10; k++) P.rot(`tail${k}`, 0.018 * Math.sin(2 * w * t - k * 0.5), 0.045 * Math.sin(w * t - k * 0.55));
	for (const [sx] of SIDES) {
		P.rotS('wingUpper', sx, 0, 0.02 * br, 0.04 * br);
		P.rotS('wingFore', sx, 0, -0.03 * br, 0);
		for (let i = 1; i <= 4; i++) P.rotS(`finger${i}b`, sx, 0, 0, 0.03 * Math.sin(w * t - i * 0.4));
	}
	P.rot('Link_Spine', 0.025 * br);
	P.rot('Link_Head', 0.05 * Math.sin(2 * w * t), 0.4 * Math.sin(w * t + 2), 0.04 * Math.sin(w * t + 1));
	P.rot('Link_Hat2', 0.08 * Math.sin(w * t - 0.5), -0.12 * Math.sin(w * t + 1.4));
	P.rot('Link_Hat3', 0.14 * Math.sin(w * t - 1.0), -0.18 * Math.sin(w * t + 1.0));
	P.rot('Link_Shoulder_L', 0.04 * br);
	P.rot('Link_Shoulder_R', -0.03 * br);
	fireballs(P, t, false);
	return P;
}

// ---------------------------------------------------------------------------
// Angriff — 3 s: rear up, lunge, breathe fire with a sweep, recover
// ---------------------------------------------------------------------------
function attackWindup() {
	const P = new Pose();
	wingsSpread(P, 0.55, -0.12);
	P.rot('spine1', -0.03).rot('spine2', -0.05).rot('chest', -0.04);
	P.rot('neck1', -0.14).rot('neck2', -0.2).rot('neck3', -0.2).rot('neck4', -0.06).rot('neck5', 0.08).rot('head', 0.3);
	P.rot('jaw', 0.15);
	for (let k = 1; k <= 10; k++) P.rot(`tail${k}`, k < 5 ? 0.05 : 0.02, -0.06);
	for (const [sx] of SIDES) P.rotS('upperArm', sx, 0.12, 0, 0).rotS('foreArm', sx, -0.15, 0, 0);
	P.rot('Link_Spine', -0.12).rot('Link_Head', -0.12);
	P.rot('Link_Shoulder_L', -2.5, 0, 0.2).rot('Link_Elbow_L', -0.35);
	P.rot('Link_Shoulder_R', -0.2, 0, -0.2);
	P.rot('Link_Hat2', 0.25).rot('Link_Hat3', 0.3);
	P.scale('Fire', 0.001);
	return P;
}

function attackLunge() {
	const P = new Pose();
	wingsSpread(P, 0.22, -0.3);
	P.rot('spine2', 0.03).rot('chest', 0.03);
	P.rot('neck1', 0.16).rot('neck2', 0.22).rot('neck3', 0.18).rot('neck4', 0.1).rot('neck5', 0.0).rot('head', -0.42);
	P.rot('jaw', 0.75);
	for (let k = 1; k <= 10; k++) P.rot(`tail${k}`, k < 5 ? 0.02 : 0.0, 0.09);
	P.rot('Link_Spine', 0.2).rot('Link_Head', -0.18);
	P.rot('Link_Shoulder_L', -1.45, 0, 0.05).rot('Link_Elbow_L', -0.05);
	P.rot('Link_Shoulder_R', -0.35, 0, -0.15);
	P.rot('Link_Hat2', -0.25).rot('Link_Hat3', -0.3);
	P.scale('Fire', 1);
	return P;
}

function attack(t) {
	const D = 3;
	const recover = () => { const P = standBase(); P.rot('jaw', 0.2); return P; };
	const P = keyed(t, [
		[0, standBase], [0.85, attackWindup], [1.1, attackLunge], [2.2, attackLunge], [2.6, recover], [D, standBase],
	]);
	// fire is controlled separately from the pose blend so it pops in/out sharply
	const fire = smooth((t - 0.95) / 0.2) * (1 - smooth((t - 2.2) / 0.3));
	const flick = 20 * TAU / D;
	P.scale('Fire', Math.max(0.001, fire * (1 + 0.08 * Math.sin(flick * t))), Math.max(0.001, fire * (1 + 0.08 * Math.sin(flick * t + 1.3))), Math.max(0.001, fire));
	// sweeping the flames left/right while breathing
	const env = smooth((t - 1.1) / 0.2) * (1 - smooth((t - 2.0) / 0.3));
	const sweep = Math.sin(TAU * (t - 1.1) / 1.1) * env;
	P.rot('neck2', 0, 0.12 * sweep).rot('neck3', 0, 0.16 * sweep).rot('head', 0.04 * Math.sin(flick * t) * env, 0.1 * sweep);
	P.rot('jaw', 0.05 * Math.sin(flick * 0.5 * t) * env);
	// tail lash
	for (let k = 1; k <= 10; k++) P.rot(`tail${k}`, 0, 0.06 * Math.sin(TAU * t / 1.5 - k * 0.5));
	fireballs(P, t, fire > 0.05);
	return P;
}

// ---------------------------------------------------------------------------
// Flug — 3.2 s loop with two powerful wing beats
// ---------------------------------------------------------------------------
function fly(t) {
	const D = 3.2, w = TAU / 1.6, slow = TAU / D;
	const c = Math.cos(w * t), s = Math.sin(w * t);
	const fold = Math.max(0, -s);
	const P = new Pose();
	P.pos('root', 0, 5.2 - 0.3 * c, 0);
	P.rot('root', -0.05 + 0.035 * s, 0.04 * Math.sin(slow * t), 0.05 * Math.sin(slow * t + 0.5));
	for (const [sx] of SIDES) {
		P.rotS('wingUpper', sx, 0.12 * s, 0.22 * fold - 0.05, 0.12 + 0.82 * c);
		P.rotS('wingFore', sx, 0, 0.35 * fold, 0.32 * Math.cos(w * t - 0.7) - 0.05);
		for (let i = 1; i <= 4; i++) {
			P.rotS(`finger${i}a`, sx, 0, (0.3 + 0.08 * i) * fold, 0.12 * Math.cos(w * t - 1.0));
			P.rotS(`finger${i}b`, sx, 0, 0.1 * fold, 0.16 * Math.cos(w * t - 1.5));
		}
		// legs tucked
		P.rotS('thigh', sx, 1.1, 0, -0.06).rotS('shin', sx, 0.35, 0, 0).rotS('foot', sx, 1.2, 0, 0);
		P.rotS('upperArm', sx, -1.1, 0, -0.05).rotS('foreArm', sx, 2.3, 0, 0).rotS('hand', sx, 0.9, 0, 0);
	}
	P.rot('spine1', 0.02 * c).rot('spine2', -0.02 * c);
	const neckBase = [0.2, 0.3, 0.27, 0.14, 0.04];
	neckBase.forEach((b, i) => P.rot(`neck${i + 1}`, b + 0.035 * Math.cos(w * t - 0.6 - i * 0.3), 0.04 * Math.sin(slow * t - i * 0.4)));
	P.rot('head', -0.62 - 0.04 * Math.cos(w * t - 1.8), -0.08 * Math.sin(slow * t - 2));
	P.rot('jaw', 0.1 + 0.04 * Math.sin(slow * t * 2));
	for (let k = 1; k <= 10; k++) {
		P.rot(`tail${k}`, (k < 7 ? 0.07 : 0.02) + 0.03 * Math.sin(w * t - k * 0.55), 0.06 * Math.sin(slow * t - k * 0.5));
	}
	P.rot('Link_Root', 0.15 + 0.03 * c);
	P.rot('Link_Spine', 0.12);
	P.rot('Link_Head', -0.3 + 0.03 * Math.sin(w * t), 0.15 * Math.sin(slow * t));
	P.rot('Link_Hat2', 0.25 + 0.1 * Math.sin(4 * w * t), 0.1 * Math.sin(3 * w * t));
	P.rot('Link_Hat3', 0.3 + 0.2 * Math.sin(4 * w * t - 1), 0.18 * Math.sin(3 * w * t - 1));
	P.rot('Link_Shoulder_L', -0.9 + 0.05 * c, 0, 0.1).rot('Link_Elbow_L', -0.25);
	P.rot('Link_Shoulder_R', -0.5, 0, -0.1);
	P.scale('Fire', 0.001);
	fireballs(P, t, false);
	return P;
}

const CLIPS = [
	{ name: 'Idle', duration: 4, fn: idle },
	{ name: 'Angriff', duration: 3, fn: attack },
	{ name: 'Flug', duration: 3.2, fn: fly },
];

export function buildAnimations(objects) {
	const sampled = CLIPS.map((clip) => {
		const n = Math.round(clip.duration * FPS);
		const times = [], poses = [];
		for (let i = 0; i <= n; i++) {
			const t = (i / n) * clip.duration;
			times.push(t);
			poses.push(clip.fn(t));
		}
		return { ...clip, times, poses };
	});

	const rotNodes = new Set(), posNodes = new Set(), scaleNodes = new Set();
	for (const c of sampled) {
		for (const p of c.poses) {
			Object.keys(p.r).forEach((k) => rotNodes.add(k));
			Object.keys(p.p).forEach((k) => posNodes.add(k));
			Object.keys(p.s).forEach((k) => scaleNodes.add(k));
		}
	}
	for (const name of [...rotNodes, ...posNodes, ...scaleNodes]) {
		if (!objects[name]) throw new Error(`animation targets unknown node ${name}`);
	}

	const q = new THREE.Quaternion(), prev = new THREE.Quaternion(), e = new THREE.Euler();
	return sampled.map((c) => {
		const tracks = [];
		const push = (Type, name, prop, values, size) => {
			const constant = values.every((v, i) => Math.abs(v - values[i % size]) < 1e-6);
			const times = constant ? [0, c.duration] : c.times;
			const vals = constant ? [...values.slice(0, size), ...values.slice(0, size)] : values;
			tracks.push(new Type(`${name}.${prop}`, times, vals));
		};
		for (const name of rotNodes) {
			const vals = [];
			c.poses.forEach((p, i) => {
				const r = p.r[name] || [0, 0, 0];
				q.setFromEuler(e.set(r[0], r[1], r[2], 'YZX'));
				if (i > 0 && q.dot(prev) < 0) q.set(-q.x, -q.y, -q.z, -q.w);
				prev.copy(q);
				vals.push(q.x, q.y, q.z, q.w);
			});
			push(THREE.QuaternionKeyframeTrack, name, 'quaternion', vals, 4);
		}
		for (const name of posNodes) {
			const rest = objects[name].position;
			const vals = [];
			c.poses.forEach((p) => {
				const d = p.p[name] || [0, 0, 0];
				vals.push(rest.x + d[0], rest.y + d[1], rest.z + d[2]);
			});
			push(THREE.VectorKeyframeTrack, name, 'position', vals, 3);
		}
		for (const name of scaleNodes) {
			const rest = objects[name].scale;
			const vals = [];
			c.poses.forEach((p) => {
				const s = p.s[name] || rest.toArray();
				vals.push(s[0], s[1], s[2]);
			});
			push(THREE.VectorKeyframeTrack, name, 'scale', vals, 3);
		}
		return new THREE.AnimationClip(c.name, c.duration, tracks);
	});
}
