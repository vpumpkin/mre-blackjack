// Pose engine: turns an authored pose description into bone transforms.
//
// Clips describe *intent* (lean, squash, expression, IK targets, which hand
// holds what); the engine resolves it in this order every frame:
//   FK body / head / face / fingers -> equipment (nozzle) -> arm IK -> flashlight
//   attach -> (sampler pass 2) hose curve + secondary springs.
// All positions in poses are given in *body space*: rest model coordinates that
// move with the Body bone, so a leaning body carries its hand targets along.
import * as THREE from 'three';
import { evalFace } from './face.js';
import { pupilOffset, hoseCurve } from '../character.js';

const D2R = Math.PI / 180;
const V = (x, y, z) => new THREE.Vector3(x, y, z);
const vec = (a) => (a.isVector3 ? a.clone() : V(a[0], a[1], a[2]));
export const qE = (deg) => new THREE.Quaternion().setFromEuler(new THREE.Euler(deg[0] * D2R, deg[1] * D2R, deg[2] * D2R, 'YXZ'));
const qAxis = (axis, rad) => new THREE.Quaternion().setFromAxisAngle(axis, rad);
const mirror = (d) => [d[0], -d[1], -d[2]];
const basisQ = (x, y, z) => new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
const SIDES = [['L', 1], ['R', -1]];

export const FACE_BONES = [
	'Eye_L', 'Eye_R', 'Pupil_L', 'Pupil_R', 'LidUpper_L', 'LidUpper_R', 'LidLower_L', 'LidLower_R',
	'BrowIn_L', 'BrowIn_R', 'BrowOut_L', 'BrowOut_R', 'Cheek_L', 'Cheek_R', 'Nose', 'Mustache_L', 'Mustache_R',
	'MouthUpper', 'MouthLower', 'MouthCorner_L', 'MouthCorner_R',
];

// Finger curl presets: [joint1, joint2] radians, thumb [j1, j2], spread.
const HAND_POSES = {
	relaxed: { f: [0.35, 0.45], t: [0.15, 0.25], spread: 0.02 },
	open: { f: [0.02, 0.04], t: [-0.05, 0.05], spread: 0.09 },
	spread: { f: [-0.12, -0.06], t: [-0.25, -0.1], spread: 0.22 },
	fist: { f: [1.45, 1.6], t: [0.75, 0.95], spread: -0.02 },
	grip: { f: [1.12, 1.25], t: [0.55, 0.65], spread: -0.01 },
	press: { f: [-0.22, -0.1], t: [-0.1, 0], spread: 0.12 },
	point: { f: [1.4, 1.55], t: [0.6, 0.8], spread: 0, index: [0.05, 0.05] },
	claw: { f: [0.75, 0.95], t: [0.35, 0.5], spread: 0.18 },
};

export function pose() {
	const arm = () => ({ upper: [0, 0, 0], lower: [0, 0, 0], hand: [0, 0, 0], ik: null, hp: { relaxed: 1 } });
	return {
		body: { pos: [0, 0, 0], rot: [0, 0, 0] },
		squash: 0,
		head: [0, 0, 0],
		gaze: [0, 0],
		face: { neutral: 1 },
		faceExtra: {},
		blink: 0,
		arms: { L: arm(), R: arm() },
		feet: { L: { pos: [0, 0, 0], rot: [0, 0, 0] }, R: { pos: [0, 0, 0], rot: [0, 0, 0] } },
		nozzle: { aim: 0, frame: null, via: null, grab: 0, grabTarget: null },
		flash: { attach: 0 },
		cap: [0, 0, 0],
		ears: [0, 0, 0],
		tremble: 0,
	};
}

export class Engine {
	constructor(rig) {
		this.rig = rig;
		this.b = rig.byName;
		this.meta = rig.meta;
		this.restPos = Object.fromEntries(rig.bones.map((b) => [b.name, b.position.clone()]));
		this.bodyRestInv = new THREE.Matrix4().makeTranslation(-rig.rest.Body.x, -rig.rest.Body.y, -rig.rest.Body.z);
		const rotOnly = (m) => new THREE.Matrix4().extractRotation(m);
		this.nozzleRot = rotOnly(this.meta.nozzle.rest);
		this.flashRot = rotOnly(this.meta.flashlight.rest);
		this.nozzleAxisLocal = V(0, 0, 1).applyMatrix4(this.nozzleRot);
		this.arms = {};
		for (const [s, sx] of SIDES) {
			const S = rig.rest[`UpperArm_${s}`], E = rig.rest[`LowerArm_${s}`], W = rig.rest[`Hand_${s}`];
			const a = E.distanceTo(S), bl = W.distanceTo(E);
			const sw = W.clone().sub(S).normalize();
			const p0 = E.clone().sub(S).addScaledVector(sw, -E.clone().sub(S).dot(sw)).normalize();
			this.arms[s] = { sx, a, b: bl, u0: E.clone().sub(S).normalize(), v0: W.clone().sub(E).normalize(), p0, hf: this.meta[`hand_${s}`] };
		}
		// flashlight held in the left hand: constant transform relative to Hand_L
		const hf = this.meta.hand_L, g = this.meta.flashlight.grips.main;
		const itemQ = this.gripItemQuat(hf, g, new THREE.Quaternion());
		const palmGrip = rig.rest.Hand_L.clone().add(hf.gripOffset.clone().addScaledVector(hf.n0, g.r));
		const inHand = new THREE.Matrix4().compose(palmGrip.clone().sub(g.c.clone().applyQuaternion(itemQ)), itemQ, V(1, 1, 1));
		this.flashInHand = new THREE.Matrix4().makeTranslation(-rig.rest.Hand_L.x, -rig.rest.Hand_L.y, -rig.rest.Hand_L.z).multiply(inHand);
		// rest hose frames
		this.hoseRestFrames = this.hoseFrames(this.meta.hose.curve, this.meta.hose.outDir, V(1, 0, 0));
	}

	reset() {
		for (const bone of this.rig.bones) {
			bone.position.copy(this.restPos[bone.name]);
			bone.quaternion.identity();
		}
	}

	update() { this.b.Root.updateMatrixWorld(true); }

	bodyPoint(p) { return vec(p).applyMatrix4(this.bodyRestInv).applyMatrix4(this.b.Body.matrixWorld); }
	bodyDir(d) { return vec(d).applyQuaternion(this.b.Body.getWorldQuaternion(new THREE.Quaternion())).normalize(); }

	setWorld(bone, worldMatrix) {
		const local = bone.parent.matrixWorld.clone().invert().multiply(worldMatrix);
		local.decompose(bone.position, bone.quaternion, new THREE.Vector3());
	}

	// rotation taking the item's grip basis onto a hand basis (rest, or rotated by handQ)
	gripItemQuat(hf, g, handQ) {
		const axis = g.axis.clone().multiplyScalar(g.thumb);
		const nrm = g.normal.clone().addScaledVector(g.axis, -g.normal.dot(g.axis)).normalize();
		const item = basisQ(axis, nrm, new THREE.Vector3().crossVectors(axis, nrm));
		const s0 = hf.s0.clone().applyQuaternion(handQ), n0 = hf.n0.clone().negate().applyQuaternion(handQ);
		const hand = basisQ(s0, n0, new THREE.Vector3().crossVectors(s0, n0));
		return hand.multiply(item.invert());
	}

	// Wrist position + hand world rotation for holding an item (canonical world frame F).
	gripTarget(side, F, g) {
		const hf = this.arms[side].hf;
		const pos = new THREE.Vector3(), q = new THREE.Quaternion();
		F.decompose(pos, q, new THREE.Vector3());
		const s_t = g.axis.clone().multiplyScalar(g.thumb).applyQuaternion(q);
		const nrm = g.normal.clone().addScaledVector(g.axis, -g.normal.dot(g.axis)).normalize();
		const n_t = nrm.applyQuaternion(q).negate();
		const f_t = new THREE.Vector3().crossVectors(n_t, s_t).multiplyScalar(hf.sigma);
		// the hand basis can be left-handed (sigma = -1), so compose as matrices
		const M = new THREE.Matrix4().makeBasis(f_t, n_t, s_t).multiply(new THREE.Matrix4().makeBasis(hf.f0, hf.n0, hf.s0).transpose());
		const R = new THREE.Quaternion().setFromRotationMatrix(M);
		const c = g.c.clone().applyMatrix4(F);
		const wrist = c.sub(hf.gripOffset.clone().addScaledVector(hf.n0, g.r).applyQuaternion(R));
		return { wrist, rot: R };
	}

	nozzleFrame() { return this.b.Nozzle.matrixWorld.clone().multiply(this.nozzleRot); }
	flashFrame() { return this.b.Flashlight.matrixWorld.clone().multiply(this.flashRot); }
	holsterFrame(rest) { return this.b.Body.matrixWorld.clone().multiply(this.bodyRestInv).multiply(rest); }

	apply(P, ctx) {
		const { b } = this;
		this.reset();
		this.ikError = { L: 0, R: 0 };
		const noise = ctx.noise, t = ctx.t, tr = P.tremble || 0;

		// body, squash & stretch (translation bones only: Roblox cannot animate bone scale)
		b.Body.position.add(vec(P.body.pos));
		const bodyRot = [...P.body.rot];
		if (tr) { bodyRot[0] += noise(t, 1, 11, 0.9 * tr); bodyRot[2] += noise(t, 2, 13, 0.9 * tr); }
		b.Body.quaternion.copy(qE(bodyRot));
		const sq = P.squash;
		b.BodyUpper.position.y -= sq * 0.085;
		b.BodySide_L.position.x += sq * 0.045;
		b.BodySide_R.position.x -= sq * 0.045;
		b.BodyLower.position.y += sq * 0.012;
		b.BodyLower.position.z += sq * 0.02;
		for (const [s, sx] of SIDES) {
			b[`UpperArm_${s}`].position.y -= sq * 0.04;
			b[`UpperArm_${s}`].position.x += sx * sq * 0.022;
		}
		b.Backpack.position.y -= sq * 0.03;

		const head = [...P.head];
		if (tr) { head[0] += noise(t, 3, 9, 1.4 * tr); head[1] += noise(t, 4, 12, 1.6 * tr); head[2] += noise(t, 5, 10, 1.2 * tr); }
		b.Head.quaternion.copy(qE(head));
		b.Cap.quaternion.copy(qE(P.cap));

		// face
		const extra = { ...P.faceExtra };
		if (tr) {
			extra.browIn = (extra.browIn || 0) + noise(t, 6, 14, 0.0025 * tr);
			extra.cheek = (extra.cheek || 0) + noise(t, 7, 15, 0.12 * tr);
			extra.wide = (extra.wide || 0) + noise(t, 8, 16, 0.12 * tr);
		}
		const F = evalFace(P.face, extra);
		const gaze = P.gaze;
		for (const [s, sx] of SIDES) {
			const g = P[`gaze${s}`] || gaze;
			const lidFollow = -g[1] * D2R * 0.35;
			const up = F[`lidUp_${s}`] + lidFollow, low = F[`lidLow_${s}`] - lidFollow * 0.3;
			b[`LidUpper_${s}`].quaternion.copy(qAxis(V(1, 0, 0), up + (0.98 - up) * P.blink));
			b[`LidLower_${s}`].quaternion.copy(qAxis(V(1, 0, 0), low + (0.22 - low) * P.blink));
			b[`Eye_${s}`].quaternion.copy(qE([-g[1], g[0], 0]));
			const eye = this.meta[`eye_${s}`];
			b[`Pupil_${s}`].position.addScaledVector(eye.axis, pupilOffset(0.022 * Math.max(0.3, F.pupil)) - eye.pupilRest);
			b[`BrowIn_${s}`].position.y += Math.min(0.03, F[`browIn_${s}`] * 1.8);
			b[`BrowIn_${s}`].position.x -= sx * F[`browSq_${s}`] * 1.5;
			b[`BrowIn_${s}`].position.z += Math.max(0, -F[`browIn_${s}`]) * 0.4;
			b[`BrowOut_${s}`].position.y += Math.min(0.03, F[`browOut_${s}`] * 1.8);
			b[`Cheek_${s}`].position.y += F[`cheek_${s}`] * 0.018;
			b[`Cheek_${s}`].position.z += F[`cheek_${s}`] * 0.006;
			const corner = b[`MouthCorner_${s}`].position;
			corner.y += F[`smile_${s}`] * 0.022 - F.open * 0.02;
			corner.x += sx * (F.wide * 0.018 - F.open * 0.012) + F.shift;
			corner.z -= Math.abs(F.wide) * 0.004;
			b[`Mustache_${s}`].quaternion.copy(qAxis(V(0, 0, 1), sx * (F.stache * 0.22 + F[`smile_${s}`] * 0.06)));
			b[`Mustache_${s}`].position.y += F.stache * 0.006 + F[`cheek_${s}`] * 0.004;
			b[`Ear_${s}`].quaternion.copy(qE(sx > 0 ? P.ears : mirror(P.ears)));
		}
		b.MouthLower.position.y -= F.open * 0.085;
		b.MouthLower.position.z += F.open * 0.01;
		b.MouthLower.position.x += F.shift;
		b.MouthUpper.position.y += F.open * 0.006 + Math.max(0, F.wide) * 0.002;
		b.MouthUpper.position.x += F.shift;
		b.Nose.position.y += F.nose * 0.008;

		// fingers, feet, FK arms
		for (const [s, sx] of SIDES) {
			this.applyHand(s, P.arms[s].hp, tr ? noise(t, 9 + sx, 17, 0.08 * tr) : 0);
			b[`Foot_${s}`].position.add(vec(P.feet[s].pos));
			b[`Foot_${s}`].quaternion.copy(qE(sx > 0 ? P.feet[s].rot : mirror(P.feet[s].rot)));
			const A = P.arms[s];
			const m = (d) => (sx > 0 ? d : mirror(d));
			b[`UpperArm_${s}`].quaternion.copy(qE(m(A.upper)));
			b[`LowerArm_${s}`].quaternion.copy(qE(m(A.lower)));
			const hand = [...A.hand];
			if (tr) { hand[0] += noise(t, 20 + sx, 18, 4 * tr); hand[2] += noise(t, 22 + sx, 19, 4 * tr); }
			b[`Hand_${s}`].quaternion.copy(qE(m(hand)));
		}
		this.update();

		// feet can ride along with the body (rolls, jumps) instead of staying planted
		if (P.feetFollow > 0) {
			for (const [s] of SIDES) {
				const foot = b[`Foot_${s}`];
				const planted = foot.matrixWorld.clone();
				const carried = b.Body.matrixWorld.clone().multiply(this.bodyRestInv).multiply(new THREE.Matrix4().makeTranslation(this.rig.rest[`Foot_${s}`]))
					.multiply(new THREE.Matrix4().makeRotationFromQuaternion(foot.quaternion));
				const p1 = new THREE.Vector3(), q1 = new THREE.Quaternion(), p2 = new THREE.Vector3(), q2 = new THREE.Quaternion();
				planted.decompose(p1, q1, new THREE.Vector3());
				carried.decompose(p2, q2, new THREE.Vector3());
				const f = Math.min(1, P.feetFollow);
				this.setWorld(foot, new THREE.Matrix4().compose(p1.lerp(p2, f), q1.slerp(q2, f), V(1, 1, 1)));
			}
			this.update();
		}

		// nozzle: holster <-> authored aim frame
		const nz = P.nozzle;
		if (nz.aim > 0 && nz.frame) {
			const H = this.holsterFrame(this.meta.nozzle.rest);
			const A = this.aimFrame(nz.frame);
			const w = Math.min(1, nz.aim);
			const hp = new THREE.Vector3(), hq = new THREE.Quaternion(), ap = new THREE.Vector3(), aq = new THREE.Quaternion();
			H.decompose(hp, hq, new THREE.Vector3());
			A.decompose(ap, aq, new THREE.Vector3());
			let p;
			if (nz.via) {
				const v = this.bodyPoint(nz.via);
				p = hp.clone().multiplyScalar((1 - w) ** 2).addScaledVector(v, 2 * (1 - w) * w).addScaledVector(ap, w * w);
			} else p = hp.clone().lerp(ap, w);
			const Fm = new THREE.Matrix4().compose(p, hq.clone().slerp(aq, w), V(1, 1, 1));
			this.setWorld(b.Nozzle, Fm.multiply(this.nozzleRot.clone().invert()));
		}
		this.update();
		let grab = nz.grab || 0;
		if (nz.grabTarget) {
			const tip = b.NozzleTip.getWorldPosition(new THREE.Vector3());
			const axis = V(0, 0, 1).applyMatrix4(new THREE.Matrix4().extractRotation(this.nozzleFrame()));
			grab = Math.max(0, this.bodyPoint(nz.grabTarget).sub(tip).dot(axis));
		}
		b.GrabPoint.position.copy(this.restPos.GrabPoint).addScaledVector(this.nozzleAxisLocal, grab);

		// arm IK (grips on the nozzle / holstered flashlight, or free targets)
		for (const [s] of SIDES) this.solveArm(s, P.arms[s]);
		this.update();

		// flashlight: holster <-> left hand
		const fa = Math.min(1, P.flash.attach || 0);
		if (fa > 0) {
			const H = this.holsterFrame(this.meta.flashlight.rest);
			const Hn = b.Hand_L.matrixWorld.clone().multiply(this.flashInHand);
			const hp = new THREE.Vector3(), hq = new THREE.Quaternion(), ap = new THREE.Vector3(), aq = new THREE.Quaternion();
			H.decompose(hp, hq, new THREE.Vector3());
			Hn.decompose(ap, aq, new THREE.Vector3());
			const Fm = new THREE.Matrix4().compose(hp.lerp(ap, fa), hq.slerp(aq, fa), V(1, 1, 1));
			this.setWorld(b.Flashlight, Fm.multiply(this.flashRot.clone().invert()));
			this.update();
		}
	}

	aimFrame(f) {
		const pos = this.bodyPoint(f.pos);
		const dir = f.target ? this.bodyPoint(f.target).sub(pos).normalize() : this.bodyDir(f.dir);
		let up = this.bodyDir([0, 1, 0]);
		if (Math.abs(up.dot(dir)) > 0.97) up = this.bodyDir([0, 0, -1]);
		const x = new THREE.Vector3().crossVectors(up, dir).normalize();
		const y = new THREE.Vector3().crossVectors(dir, x).normalize();
		const q = basisQ(x, y, dir).premultiply(qAxis(dir, (f.roll || 0) * D2R));
		return new THREE.Matrix4().compose(pos, q, V(1, 1, 1));
	}

	applyHand(s, weights, jitter) {
		const hf = this.arms[s].hf;
		let total = 0;
		const acc = { f: [0, 0], t: [0, 0], spread: 0, index: null };
		for (const [name, w] of Object.entries(weights)) {
			if (w <= 0) continue;
			const p = HAND_POSES[name];
			if (!p) throw new Error(`unknown hand pose ${name}`);
			total += w;
			acc.f[0] += p.f[0] * w; acc.f[1] += p.f[1] * w; acc.t[0] += p.t[0] * w; acc.t[1] += p.t[1] * w; acc.spread += p.spread * w;
			if (p.index) acc.index = acc.index || [0, 0], acc.index[0] += (p.index[0] - p.f[0]) * w, acc.index[1] += (p.index[1] - p.f[1]) * w;
		}
		if (total <= 0) return;
		const f = acc.f.map((v) => v / total + jitter), th = acc.t.map((v) => v / total), spread = acc.spread / total;
		hf.fingers.forEach((fd, i) => {
			let c1 = f[0] * (1 + i * 0.06), c2 = f[1] * (1 + i * 0.05);
			if (acc.index && fd.name === 'Index') { c1 += acc.index[0] / total; c2 += acc.index[1] / total; }
			const fan = qAxis(hf.n0, spread * (fd.off / 0.035) * (this.arms[s].sx));
			this.b[`${fd.name}1_${s}`].quaternion.copy(fan.multiply(qAxis(fd.axis, c1)));
			this.b[`${fd.name}2_${s}`].quaternion.copy(qAxis(fd.axis, c2));
		});
		this.b[`Thumb1_${s}`].quaternion.copy(qAxis(hf.thumb.axis, th[0]));
		this.b[`Thumb2_${s}`].quaternion.copy(qAxis(hf.thumb.axis, th[1]));
	}

	solveArm(s, A) {
		const ik = A.ik;
		if (!ik || !(ik.w > 0)) return;
		const { b } = this;
		const arm = this.arms[s];
		const upper = b[`UpperArm_${s}`], lower = b[`LowerArm_${s}`], hand = b[`Hand_${s}`];
		let wrist, handRot = null;
		const mix = ik.grip && ik.target ? THREE.MathUtils.clamp(ik.mix ?? 0, 0, 1) : (ik.target ? 1 : 0);
		if (ik.grip) {
			const [item, point] = ik.grip.split('.');
			const F = item === 'nozzle' ? this.nozzleFrame()
				: item === 'flashHolster' ? this.holsterFrame(this.meta.flashlight.rest) : this.flashFrame();
			const g = this.meta[item === 'nozzle' ? 'nozzle' : 'flashlight'].grips[point];
			({ wrist, rot: handRot } = this.gripTarget(s, F, g));
			// grip -> free target blend (picking up / putting back without pops)
			if (ik.target && mix > 0) wrist.lerp(this.bodyPoint(ik.target), mix);
		} else wrist = this.bodyPoint(ik.target);
		if (ik.offset) wrist.add(this.bodyDir(ik.offset).multiplyScalar(vec(ik.offset).length()));
		const S = upper.getWorldPosition(new THREE.Vector3());
		const poleHint = this.bodyDir(ik.pole || [arm.sx, -0.6, -0.5]);
		const d = wrist.clone().sub(S);
		// cartoon stretch: lengthen the arm (bone translation) when the target is out of reach
		const maxStretch = ik.stretch ?? 1.18;
		const kFull = THREE.MathUtils.clamp(d.length() / ((arm.a + arm.b) * 0.97), 1, maxStretch);
		const k = 1 + (kFull - 1) * Math.min(1, ik.w);
		lower.position.copy(this.restPos[lower.name]).multiplyScalar(k);
		hand.position.copy(this.restPos[hand.name]).multiplyScalar(k);
		const a = arm.a * k, bl = arm.b * k;
		const dist = THREE.MathUtils.clamp(d.length(), 0.05, (a + bl) * 0.999);
		const dn = d.normalize();
		const cosA = THREE.MathUtils.clamp((a ** 2 + dist ** 2 - bl ** 2) / (2 * a * dist), -1, 1);
		const sinA = Math.sqrt(1 - cosA * cosA);
		let pole = poleHint.clone().addScaledVector(dn, -poleHint.dot(dn));
		if (pole.lengthSq() < 1e-6) pole = this.bodyDir([0, -1, 0]).addScaledVector(dn, -this.bodyDir([0, -1, 0]).dot(dn));
		pole.normalize();
		const E = S.clone().addScaledVector(dn, cosA * a).addScaledVector(pole, sinA * a);
		const W = S.clone().addScaledVector(dn, dist);
		const u = E.clone().sub(S).normalize(), v = W.clone().sub(E).normalize();
		const frame = (dir, p) => { const pp = p.clone().addScaledVector(dir, -p.dot(dir)).normalize(); return basisQ(dir, pp, new THREE.Vector3().crossVectors(dir, pp)); };
		const Ru = frame(u, pole).multiply(frame(arm.u0, arm.p0).invert());
		const Rl = frame(v, pole).multiply(frame(arm.v0, arm.p0).invert());
		const lowerFK = lower.getWorldQuaternion(new THREE.Quaternion());
		const handFK = hand.getWorldQuaternion(new THREE.Quaternion());
		const upperFK = upper.getWorldQuaternion(new THREE.Quaternion());
		const RhFree = Rl.clone().multiply(lowerFK.clone().invert().multiply(handFK));
		let Rh = handRot ? handRot.clone().slerp(RhFree, mix) : RhFree;
		if (ik.aim && mix > 0) {
			// turn the hand so its thumb axis (the held flashlight's beam) points at the aim point
			const beam = arm.hf.s0.clone().applyQuaternion(Rh);
			const want = this.bodyPoint(ik.aim).sub(W).normalize();
			const aimed = new THREE.Quaternion().setFromUnitVectors(beam, want).multiply(Rh);
			Rh = Rh.slerp(aimed, mix);
		}
		const w = Math.min(1, ik.w);
		const RuW = upperFK.slerp(Ru, w), RlW = lowerFK.slerp(Rl, w), RhW = handFK.slerp(Rh, w);
		const parentQ = upper.parent.getWorldQuaternion(new THREE.Quaternion());
		upper.quaternion.copy(parentQ.invert().multiply(RuW));
		lower.quaternion.copy(RuW.clone().invert().multiply(RlW));
		hand.quaternion.copy(RlW.clone().invert().multiply(RhW));
		this.ikError[s] = W.distanceTo(wrist) * w; // > 0 when the target was out of reach
	}

	// parallel-transport frames at the hose bone parameters
	hoseFrames(curve, startDir, normalHint) {
		const ts = this.meta.hose.ts;
		const frames = [];
		let n = normalHint.clone().addScaledVector(startDir, -normalHint.dot(startDir)).normalize();
		let prevT = startDir.clone().normalize();
		const steps = 60;
		let k = 0;
		for (let i = 0; i <= steps && k < ts.length; i++) {
			const u = i / steps;
			const tan = curve.getTangent(Math.min(1, u)).normalize();
			const q = new THREE.Quaternion().setFromUnitVectors(prevT, tan);
			n.applyQuaternion(q).normalize();
			prevT = tan;
			while (k < ts.length && ts[k] <= u + 1e-9) {
				frames.push({ p: curve.getPoint(ts[k]), q: basisQ(tan, n, new THREE.Vector3().crossVectors(tan, n)) });
				k++;
			}
		}
		return frames;
	}

	// pass-2 extras: hose with lag/sag + secondary rotations
	applySecondary(sec) {
		const { b } = this;
		if (sec.cap) b.Cap.quaternion.premultiply(this.worldToLocalRot(b.Cap, sec.cap));
		for (const s of ['L', 'R']) if (sec.ears) b[`Ear_${s}`].quaternion.premultiply(this.worldToLocalRot(b[`Ear_${s}`], sec.ears));
		for (const s of ['L', 'R']) if (sec.stache) b[`Mustache_${s}`].quaternion.premultiply(this.worldToLocalRot(b[`Mustache_${s}`], sec.stache));
		if (sec.belly) { b.BodyLower.position.y += sec.belly; b.BodySide_L.position.x -= sec.belly * 0.4; b.BodySide_R.position.x += sec.belly * 0.4; }
		this.update();
		// hose
		const hose = this.meta.hose;
		const bp = b.Backpack.matrixWorld;
		const bq = b.Backpack.getWorldQuaternion(new THREE.Quaternion());
		const outlet = hose.tankLocal.clone().applyMatrix4(bp);
		const outDir = hose.outDirLocal.clone().applyQuaternion(bq);
		const NF = this.nozzleFrame();
		const rear = V(0, 0, 0).applyMatrix4(NF);
		const inDir = V(0, 0, 1).applyMatrix4(new THREE.Matrix4().extractRotation(NF));
		const curve = hoseCurve(outlet, outDir, rear, inDir, sec.sag ?? 0.05, sec.hoseLag || V(0, 0, 0));
		const frames = this.hoseFrames(curve, outDir, V(1, 0, 0).applyQuaternion(bq));
		const bodyInv = b.Body.matrixWorld.clone().invert();
		const bodyQInv = b.Body.getWorldQuaternion(new THREE.Quaternion()).invert();
		hose.names.forEach((name, i) => {
			const bone = b[name];
			bone.position.copy(frames[i].p.clone().applyMatrix4(bodyInv));
			bone.quaternion.copy(bodyQInv.clone().multiply(frames[i].q.clone().multiply(this.hoseRestFrames[i].q.clone().invert())));
		});
		this.update();
	}

	worldToLocalRot(bone, rotVec) {
		const angle = rotVec.length();
		if (angle < 1e-6) return new THREE.Quaternion();
		const wq = qAxis(rotVec.clone().normalize(), angle);
		const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
		// local delta d such that parent * d * local == wq * parent * local  =>  d = parent^-1 * wq * parent
		return pq.clone().invert().multiply(wq).multiply(pq);
	}
}
