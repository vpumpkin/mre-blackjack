// Samples every clip through the pose engine and bakes keyframe tracks.
//
// Pass 1 evaluates the authored pose per frame and records world motion of
// the head, body and nozzle. From that, damped springs produce secondary
// motion (cap / ear / mustache follow-through, belly bounce, hose lag), which
// pass 2 layers on before the final local bone transforms are read out.
// No track ever scales a bone (Roblox only animates position + rotation).
import * as THREE from 'three';
import { Engine, FACE_BONES } from './anim/engine.js';
import { makeNoise } from './anim/keys.js';
import { CLIPS } from './anim/clips.js';

const FPS = 30;
// Markers that drive gameplay. Variants of one group must agree on these.
export const GAMEPLAY_MARKERS = new Set([
	'VacuumStart', 'SuctionActive', 'VacuumStop', 'HitboxStart', 'Impact', 'HitboxEnd', 'Flash', 'Grab',
	'Slam01', 'Slam02', 'Release', 'Recovery', 'IFrameStart', 'IFrameEnd', 'Land',
]);

function checkVariants(clips) {
	const groups = {};
	for (const c of clips) (groups[c.group] ??= []).push(c);
	for (const [g, list] of Object.entries(groups)) {
		const sig = (c) => JSON.stringify([c.duration, (c.markers || []).filter((m) => GAMEPLAY_MARKERS.has(m[0]))]);
		const first = sig(list[0]);
		for (const c of list) if (sig(c) !== first) throw new Error(`variant ${c.name} breaks the gameplay timing of group ${g}`);
	}
}

// damped spring over a target series (vectors or numbers); loops are run
// three times so the recorded cycle starts in its steady state
function springSeries(targets, dt, hz, zeta, loop, clamp) {
	const isNum = typeof targets[0] === 'number';
	const w = 2 * Math.PI * hz;
	let x = isNum ? 0 : new THREE.Vector3(), v = isNum ? 0 : new THREE.Vector3();
	const out = new Array(targets.length);
	const cycles = loop ? 3 : 1;
	for (let c = 0; c < cycles; c++) {
		for (let i = 0; i < targets.length; i++) {
			const tg = targets[i];
			if (isNum) {
				v += (-w * w * (x - tg) - 2 * zeta * w * v) * dt; x += v * dt;
				if (clamp) x = THREE.MathUtils.clamp(x, -clamp, clamp);
				out[i] = x;
			} else {
				const acc = x.clone().sub(tg).multiplyScalar(-w * w).addScaledVector(v, -2 * zeta * w);
				v.addScaledVector(acc, dt); x.addScaledVector(v, dt);
				if (clamp && x.length() > clamp) x.setLength(clamp);
				out[i] = x.clone();
			}
		}
	}
	return out;
}

function angularVelocity(qs, i, dt, loop) {
	const n = qs.length - 1;
	const ia = loop ? (i - 1 + n) % n : Math.max(0, i - 1);
	const ib = loop ? (i + 1) % n : Math.min(n, i + 1);
	const dq = qs[ib].clone().multiply(qs[ia].clone().invert());
	if (dq.w < 0) dq.set(-dq.x, -dq.y, -dq.z, -dq.w);
	const angle = 2 * Math.acos(Math.min(1, dq.w));
	const s = Math.sqrt(1 - Math.min(1, dq.w * dq.w));
	if (angle < 1e-6 || s < 1e-6) return new THREE.Vector3();
	return new THREE.Vector3(dq.x / s, dq.y / s, dq.z / s).multiplyScalar(angle / ((ib - ia + (ib < ia ? n : 0)) * dt || dt));
}

function sampleClip(eng, clip) {
	const n = Math.max(2, Math.round(clip.duration * FPS));
	const dt = clip.duration / n;
	const noise = makeNoise(clip.duration);
	const poses = [], headQ = [], bodyP = [], rearP = [];
	for (let i = 0; i <= n; i++) {
		const t = i * dt;
		const P = clip.fn(t, { D: clip.duration, noise });
		poses.push(P);
		eng.apply(P, { t, noise });
		headQ.push(eng.b.Head.getWorldQuaternion(new THREE.Quaternion()));
		bodyP.push(eng.b.Body.getWorldPosition(new THREE.Vector3()));
		rearP.push(new THREE.Vector3().setFromMatrixPosition(eng.nozzleFrame()));
	}
	const loop = !!clip.loop;
	const idx = (i) => (loop ? ((i % n) + n) % n : THREE.MathUtils.clamp(i, 0, n));
	const omega = poses.map((_, i) => angularVelocity(headQ, i, dt, loop));
	const accY = poses.map((_, i) => (bodyP[idx(i + 1)].y - 2 * bodyP[i].y + bodyP[idx(i - 1)].y) / (dt * dt));
	const vel = poses.map((_, i) => rearP[idx(i + 1)].clone().sub(rearP[idx(i - 1)]).divideScalar(2 * dt));
	const cap = springSeries(omega.map((w) => w.clone().multiplyScalar(-0.035)), dt, 3.2, 0.32, loop, 0.2);
	const ears = springSeries(omega.map((w) => w.clone().multiplyScalar(-0.05)), dt, 4.5, 0.28, loop, 0.35);
	const stache = springSeries(omega.map((w) => w.clone().multiplyScalar(-0.02)), dt, 5.5, 0.35, loop, 0.12);
	const belly = springSeries(accY.map((a) => THREE.MathUtils.clamp(-a * 0.0025, -0.03, 0.03)), dt, 4, 0.3, loop, 0.03);
	const hoseLag = springSeries(vel.map((v) => v.clone().multiplyScalar(-0.07)), dt, 2.8, 0.45, loop, 0.3);

	const names = clip.faceOnly ? FACE_BONES : eng.rig.bones.filter((b) => b.name !== 'Root').map((b) => b.name);
	const frames = [];
	for (let i = 0; i <= n; i++) {
		const t = i * dt;
		eng.apply(poses[i], { t, noise });
		if (!clip.faceOnly) eng.applySecondary({ cap: cap[i], ears: ears[i], stache: stache[i], belly: belly[i], hoseLag: hoseLag[i] });
		const f = {};
		for (const name of names) {
			const bone = eng.b[name];
			f[name] = { q: bone.quaternion.clone(), p: bone.position.clone() };
		}
		frames.push(f);
	}
	const times = frames.map((_, i) => i * dt);
	return { names, frames, times };
}

export function buildAnimations(rig) {
	checkVariants(CLIPS);
	const eng = new Engine(rig);
	const sampled = CLIPS.map((c) => ({ clip: c, ...sampleClip(eng, c) }));

	// position tracks only for bones that ever translate
	const moving = new Set();
	for (const s of sampled) {
		for (const name of s.names) {
			const rest = eng.restPos[name];
			if (s.frames.some((f) => f[name].p.distanceToSquared(rest) > 1e-10)) moving.add(name);
		}
	}

	const clips = sampled.map(({ clip, names, frames, times }) => {
		const tracks = [];
		const push = (Type, name, prop, values, size) => {
			const constant = values.every((v, i) => Math.abs(v - values[i % size]) < 1e-6);
			tracks.push(constant
				? new Type(`${name}.${prop}`, [0, clip.duration], [...values.slice(0, size), ...values.slice(0, size)])
				: new Type(`${name}.${prop}`, times, values));
		};
		for (const name of names) {
			const qv = [];
			let prev = null;
			for (const f of frames) {
				const q = f[name].q.clone();
				if (Math.abs(q.length() - 1) > 1e-3) throw new Error(`non-unit quaternion on ${name} in ${clip.name}`);
				if (prev && q.dot(prev) < 0) q.set(-q.x, -q.y, -q.z, -q.w);
				prev = q;
				qv.push(q.x, q.y, q.z, q.w);
			}
			push(THREE.QuaternionKeyframeTrack, name, 'quaternion', qv, 4);
			if (moving.has(name)) push(THREE.VectorKeyframeTrack, name, 'position', frames.flatMap((f) => f[name].p.toArray()), 3);
		}
		return new THREE.AnimationClip(clip.name, clip.duration, tracks);
	});
	eng.reset();
	eng.update();

	const info = CLIPS.map((c) => ({
		name: c.name, group: c.group, variant: c.variant || null, duration: c.duration, loop: !!c.loop,
		priority: c.priority, faceOnly: !!c.faceOnly, label: c.label,
		markers: (c.markers || []).map(([name, time]) => ({ name, time })),
		rootMotion: c.rootMotion ? sampleRootMotion(c) : null,
	}));
	return { clips, info };
}

// root motion is applied by the game / viewer (the clips themselves are in place)
function sampleRootMotion(c) {
	const out = [];
	const n = Math.round(c.duration * 20);
	for (let i = 0; i <= n; i++) {
		const t = (i / n) * c.duration;
		out.push([+t.toFixed(3), ...c.rootMotion(t).map((v) => +v.toFixed(4))]);
	}
	return out;
}
