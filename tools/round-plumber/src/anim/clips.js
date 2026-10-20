// All animation clips of the round plumber.
//
// Each clip is a pure function of time returning a pose (see engine.pose()).
// Conventions: degrees; body / head rot [x, y, z] = [lean forward +, turn to
// his left +, tilt top to his right +]; gaze [yaw left +, pitch up +]; all
// positions are body-space metres (rest model coordinates). Loops start and
// end on the same pose. Variants of a group share duration and gameplay
// marker times (checked at build time) so hitboxes, i-frames and damage
// never depend on which variant plays.
import { pose } from './engine.js';
import { key, env, saccade, blinks, EASE } from './keys.js';

const TAU = Math.PI * 2;
const mx = (p) => [-p[0], p[1], p[2]];
const lerp3 = (a, b, f) => a.map((v, i) => v + (b[i] - v) * f);
const add3 = (a, b) => a.map((v, i) => v + b[i]);

// --- shared reference poses (body space) -------------------------------------
const POLE = { L: [1, -0.35, -0.6], R: [-1, -0.35, -0.6] };
const WRIST = {
	idle: [0.4, 0.33, 0.59],
	chest: [0.21, 0.47, 0.62],
	face: [0.24, 0.66, 0.62],
	guard: [0.27, 0.5, 0.66],
	low: [0.47, 0.27, 0.43],
	back: [0.5, 0.28, 0.2],
	cap: [0.33, 0.9, 0.36],
};
const NOZZLE_AIM = { pos: [0.04, 0.29, 0.58], target: [0.04, 0.22, 3] };

function arms(P, l, r, opts = {}) {
	P.arms.L.ik = { target: l, pole: opts.poleL || POLE.L, w: 1, ...(opts.ikL || {}) };
	P.arms.R.ik = { target: r, pole: opts.poleR || POLE.R, w: 1, ...(opts.ikR || {}) };
	if (opts.hp) P.arms.L.hp = P.arms.R.hp = opts.hp;
	if (opts.hpL) P.arms.L.hp = opts.hpL;
	if (opts.hpR) P.arms.R.hp = opts.hpR;
	return P;
}
const sym = (w) => [w, mx(w)];
const breath = (t, period, amp) => amp * Math.sin((TAU * t) / period);

// Holding the vacuum nozzle with both hands at the authored aim frame.
function holdNozzle(P, frame, wR = 1, wL = 1) {
	P.nozzle.aim = 1;
	P.nozzle.frame = frame;
	P.arms.R.ik = { grip: 'nozzle.rear', w: wR, pole: POLE.R, stretch: 1.26 };
	P.arms.L.ik = { grip: 'nozzle.top', w: wL, pole: [0.8, 0.2, -0.7], stretch: 1.26 };
	P.arms.R.hp = { grip: 1 };
	P.arms.L.hp = { grip: 1 };
}

// ============================================================================
// IDLE 1 - fearful trembling (6 s loop)
// ============================================================================
function idleFear(t) {
	const P = pose();
	const nerv = key(t, [[0, 0.45], [1.5, 0.75], [3.8, 0.85], [4.3, 1], [5.2, 0.55], [6, 0.45]]);
	const startle = env(t, 3.85, 3.93, 4.12, 4.75);
	P.tremble = key(t, [[0, 0.25], [1.4, 0.75], [3.8, 0.9], [4.0, 1], [5.0, 0.35], [6, 0.25]]);
	P.squash = 0.05 * nerv + breath(t, 3, 0.012) + key(t, [[0, 0], [3.86, 0], [3.93, -0.12, 'o'], [4.06, 0.15, 'o'], [4.4, 0.04], [6, 0]]);
	P.body.pos = [0, key(t, [[0, 0], [3.86, 0], [3.94, 0.04, 'o'], [4.1, 0], [6, 0]]), 0];
	P.body.rot = [3 * nerv - 4 * startle, key(t, [[0, 0], [1.8, 0], [2.2, 6], [2.6, 6], [2.95, -6], [3.4, -6], [3.8, 0], [6, 0]]), 0];
	P.gaze = saccade(t, [[0, [0, -3]], [1.55, [24, -2]], [2.45, [-26, 0]], [3.3, [0, -4]], [3.87, [0, 7]], [4.5, [9, -4]], [5.3, [0, -3]], [6, [0, -3]]]);
	P.head = [
		key(t, [[0, 2], [3.86, 2], [3.95, -9, 'o'], [4.4, -2], [5.5, 2], [6, 2]]),
		key(t, [[0, 0], [1.68, 0], [2.0, 17], [2.5, 17], [2.75, -19, 'o'], [3.3, -19], [3.62, 0], [4.6, 6], [5.4, 0], [6, 0]]),
		key(t, [[0, 0], [2.0, -4], [2.75, 4], [3.6, 0], [6, 0]]),
	];
	const calm = env(t, 4.5, 5.0, 5.5, 6.0);
	P.face = { afraid: nerv, neutral: 1 - nerv, startled: startle * 2.2, relieved: calm * 0.4 };
	P.faceExtra = { open: key(t, [[0, 0], [4.5, 0], [4.85, 0.18], [5.3, 0], [6, 0]]) }; // shaky exhale
	P.blink = blinks(t, [0.8, 2.25, 3.55, 5.1, 5.55]);
	const [lc, rc] = sym(lerp3(lerp3(WRIST.idle, WRIST.chest, nerv), WRIST.face, startle));
	arms(P, lc, rc, { hp: { claw: nerv * 0.8, relaxed: 1 - nerv, spread: startle * 2 } });
	P.ears = [0, 0, -14 * startle];
	return P;
}

// ============================================================================
// IDLE 2 - nervous look around (6 s loop). Eyes lead, then head, then body.
// ============================================================================
function idleLookAround(t) {
	const P = pose();
	P.squash = breath(t, 3, 0.014);
	P.gaze = saccade(t, [[0, [0, -2]], [1.1, [30, 0]], [2.5, [-32, 2]], [3.3, [0, 26]], [3.85, [6, 12]], [4.6, [0, -4]], [5.4, [0, -2]], [6, [0, -2]]]);
	P.head = [
		key(t, [[0, 2], [3.4, 2], [3.75, -20, 'o'], [4.2, -14], [4.75, 4], [5.6, 2], [6, 2]]),
		key(t, [[0, 0], [1.22, 0], [1.6, 36, 'o'], [2.5, 36], [2.62, 36], [2.95, -40, 'o'], [3.35, -38], [3.75, 0], [6, 0]]),
		key(t, [[0, 0], [1.6, -8], [2.5, -8], [2.95, 8], [3.4, 0], [3.9, 9], [4.4, 9], [4.9, 0], [6, 0]]),
	];
	P.body.rot = [
		key(t, [[0, 0], [3.5, 0], [3.9, -6], [4.5, -2], [4.9, 3], [5.6, 0], [6, 0]]),
		key(t, [[0, 0], [1.42, 0], [1.9, 14], [2.6, 14], [3.15, -17], [3.6, -14], [4.0, 0], [6, 0]]),
		0,
	];
	P.feet.L.rot = [0, key(t, [[0, 0], [1.6, 8], [2.6, 8], [3.1, -6], [3.8, 0], [6, 0]]), 0];
	P.feet.R.rot = [0, key(t, [[0, 0], [1.6, -6], [2.6, -6], [3.1, 8], [3.8, 0], [6, 0]]), 0];
	const worry = env(t, 1.0, 1.3, 3.3, 3.6), confused = env(t, 3.75, 3.95, 4.3, 4.55), relief = env(t, 4.5, 4.75, 5.4, 5.9);
	P.face = { neutral: Math.max(0.05, 1 - worry - confused - relief), afraid: worry, confused, relieved: relief };
	P.faceExtra = { open: relief * 0.15 * Math.sin(Math.PI * Math.min(1, Math.max(0, (t - 4.5) / 0.6))) };
	P.blink = blinks(t, [0.6, 2.3, 3.62, 5.1]);
	P.ears = [0, 0, key(t, [[0, 0], [0.95, 0], [1.02, -18, 'o'], [1.3, 0], [6, 0]])];
	// relief: tug the cap back into place with the right hand
	const tug = env(t, 4.6, 4.9, 5.25, 5.65);
	const [li, ri] = sym(lerp3(WRIST.idle, WRIST.chest, worry * 0.6));
	arms(P, li, lerp3(ri, mx(WRIST.cap), tug), { hpL: { relaxed: 1 - worry, claw: worry }, hpR: { relaxed: 1 - tug, grip: tug } });
	P.cap = [key(t, [[0, 0], [4.9, 0], [5.05, -6], [5.2, 4], [5.4, 0], [6, 0]]), 0, key(t, [[0, 0], [4.9, 0], [5.05, 5], [5.3, -2], [5.5, 0], [6, 0]])];
	P.body.rot[2] = -4 * tug;
	P.head[2] += -8 * tug;
	return P;
}

// ============================================================================
// IDLE 3 - gathering courage (6 s loop)
// ============================================================================
function idleCourage(t) {
	const P = pose();
	const nerv = key(t, [[0, 0.6], [0.8, 0.6], [1.2, 0.2], [1.8, 0], [3.05, 0], [3.15, 1, 'o'], [3.5, 0.5], [4.8, 0.45], [5.6, 0.6], [6, 0.6]]);
	const inhale = env(t, 0.8, 1.35, 1.55, 1.8), brave = env(t, 1.75, 1.85, 3.05, 3.12), startle = env(t, 3.08, 3.15, 3.35, 3.7), pretend = env(t, 3.5, 3.75, 4.7, 5.4);
	P.tremble = 0.3 * nerv + 0.25 * pretend;
	P.squash = -0.09 * inhale + key(t, [[0, 0.03], [1.78, 0.03], [1.86, 0.08, 'o'], [2.05, -0.03, 'o'], [3.05, -0.02], [3.12, 0.12, 'o'], [3.5, 0.04], [6, 0.03]]);
	P.body.rot = [-4 * inhale - 3 * brave + 2 * startle, key(t, [[0, 0], [3.6, 0], [4.0, -5], [4.45, 5], [4.9, 0], [6, 0]]), key(t, [[0, 0], [3.6, 0], [4.0, 3], [4.45, -3], [4.9, 0], [6, 0]])];
	P.body.pos = [0, 0.02 * brave * Math.max(0, Math.sin((t - 1.85) * TAU * 1.2)), 0];
	P.head = [key(t, [[0, 3], [0.8, 3], [1.4, -7], [1.8, -3], [1.9, 6, 'o'], [2.05, -2], [3.05, -3], [3.15, -8, 'o'], [3.6, 0], [6, 3]]), key(t, [[0, 0], [3.6, 0], [3.9, 6], [4.3, -6], [4.7, 0], [6, 0]]), 0];
	P.face = { afraid: nerv * (1 - startle), eyesClosed: inhale, determined: brave * 0.75, proud: brave * 0.5, startled: startle * 1.5, neutral: 0.05 };
	if (pretend > 0) Object.assign(P.face, { proud: pretend * 0.55, afraid: pretend * 0.55 });
	P.faceExtra = { wide: -0.6 * pretend, open: 0.12 * pretend + 0.1 * inhale };
	P.gaze = saccade(t, [[0, [0, -3]], [1.8, [0, 2]], [3.12, [0, 4]], [3.6, [26, 0]], [3.95, [-26, 0]], [4.3, [22, 3]], [4.65, [-14, 0]], [5.2, [0, -3]], [6, [0, -3]]], 0.05);
	P.blink = blinks(t, [0.45, 2.6, 5.5]);
	const [lc, rc] = sym(lerp3(lerp3(WRIST.idle, WRIST.chest, nerv * 0.7), WRIST.guard, brave));
	const [lf, rf] = sym(WRIST.chest);
	arms(P, lerp3(lc, lf, startle), lerp3(rc, rf, startle), {
		hp: { fist: brave, relaxed: (1 - brave) * (1 - startle) * 0.6, claw: nerv * 0.4, spread: startle * 2 },
	});
	if (pretend > 0) { P.arms.L.ik.target = lerp3(P.arms.L.ik.target, WRIST.back, pretend); P.arms.R.ik.target = lerp3(P.arms.R.ik.target, mx(WRIST.back), pretend); }
	P.ears = [0, 0, -12 * startle];
	return P;
}

// ============================================================================
// COMBAT IDLE (2 s loop) - ready, a bit nervous, bouncing on his toes
// ============================================================================
function combatPose(P, t, D = 2) {
	const bounce = Math.sin((TAU * t * 2) / D);
	P.squash = 0.04 + 0.035 * bounce;
	P.body.pos = [0, 0.012 * (1 - bounce), 0];
	P.body.rot = [6 + 1.5 * bounce, 4 * Math.sin((TAU * t) / D), 1.5 * Math.sin((TAU * t) / D + 1)];
	P.head = [-4 - 1.5 * bounce, -3 * Math.sin((TAU * t) / D), 0];
	P.feet.L.pos = [0.03, 0, 0.02]; P.feet.R.pos = [-0.03, 0, -0.03];
	P.feet.L.rot = [0, 10, 0]; P.feet.R.rot = [0, 10, 0];
	P.face = { determined: 0.7, afraid: 0.3 };
	P.tremble = 0.12;
	arms(P, add3(WRIST.guard, [0, 0.015 * bounce, 0]), add3(mx(WRIST.guard), [0.03, -0.03 + 0.015 * bounce, 0.02]), { hp: { fist: 1 } });
	return P;
}
function combatIdle(t) {
	const P = combatPose(pose(), t);
	P.gaze = saccade(t, [[0, [0, 0]], [0.7, [8, 0]], [1.3, [-6, 1]], [1.9, [0, 0]]], 0.05);
	P.blink = blinks(t, [1.05]);
	return P;
}

// ============================================================================
// RUN (0.6 s loop) - quick waddle on small feet, arms pumping
// ============================================================================
function run(t) {
	const P = pose();
	const w = TAU / 0.6, s = Math.sin(w * t), c = Math.cos(w * t);
	P.body.rot = [15 + 2 * Math.cos(2 * w * t), 7 * s, -5 * s];
	P.body.pos = [0, 0.035 * Math.abs(Math.cos(w * t)), 0.02];
	P.squash = 0.06 * Math.cos(2 * w * t) - 0.01;
	P.head = [-10 - 2 * Math.cos(2 * w * t), -5 * s, 3 * s];
	P.feet.L.pos = [0, 0.07 * Math.max(0, c), 0.11 * s];
	P.feet.R.pos = [0, 0.07 * Math.max(0, -c), -0.11 * s];
	P.feet.L.rot = [-25 * s, 0, 0]; P.feet.R.rot = [25 * s, 0, 0];
	P.face = { afraid: 0.55, strain: 0.25, determined: 0.2 };
	P.faceExtra = { open: 0.25 };
	P.gaze = [0, -6];
	arms(P, add3(WRIST.guard, [0.05, -0.04 - 0.05 * s, -0.12 * s]), add3(mx(WRIST.guard), [-0.05, -0.04 + 0.05 * s, 0.12 * s]), { hp: { fist: 0.7, relaxed: 0.3 } });
	return P;
}

// ============================================================================
// VACUUM START A/B/C (1.6 s): notice -> grab -> draw -> power on
// markers: VacuumStart 1.05, SuctionActive 1.25
// ============================================================================
const VAC_MARKERS = [['VacuumStart', 1.05], ['SuctionActive', 1.25]];

function vacuumStartBase(t, v) {
	const P = pose();
	const notice = env(t, 0, 0.12, 0.3, 0.42);
	const reachR = key(t, [[0, 0], [0.4, 0], [0.62, 1, 'o']]);
	const draw = key(t, [[0, 0], [0.62, 0], [v.drawEnd, 1, v.drawEase]]);
	const reachL = key(t, [[0, 0], [0.84, 0], [1.0, 1, 'o']]);
	const recoil = env(t, 1.03, 1.08, 1.12, 1.3);
	const suck = key(t, [[0, 0], [1.2, 0], [1.45, 1]]);
	P.squash = key(t, [[0, 0], [0.62, 0.02], [0.68, v.pullSquash, 'o'], [0.84, -0.05], [1.0, 0.05], [1.06, -0.05, 'o'], [1.3, 0.04], [1.6, 0.03]]);
	P.body.rot = [
		-5 * notice + key(t, [[0, 0], [0.9, 0], [1.0, 5], [1.12, -7, 'o'], [1.6, -10]]),
		key(t, v.yaw),
		key(t, [[0, 0], [0.45, 0], [0.62, -6], [0.9, 3], [1.1, 0]]),
	];
	P.body.pos = [0, key(t, v.hop || [[0, 0], [1.6, 0]]), key(t, [[0, 0], [1.08, 0], [1.14, -0.02, 'o'], [1.6, -0.01]])];
	P.head = [key(t, [[0, 0], [0.15, -6], [0.45, 2], [0.62, 10], [0.9, 0], [1.6, -2]]), key(t, [[0, 0], [0.45, 0], [0.62, -22], [0.95, 0]]), 0];
	P.gaze = saccade(t, [[0, [0, 2]], [0.08, [0, 8]], [0.44, [-30, -22]], [0.85, [0, -4]], [1.6, [0, -4]]]);
	P.face = {
		surprised: notice * 1.4, determined: key(t, [[0, 0], [0.3, 0], [0.42, 1, 'o'], [1.0, 1], [1.2, 0.2]]),
		strain: recoil + suck * 0.6, focused: suck * 0.4, neutral: 0.02, ...(v.face ? v.face(t) : {}),
	};
	P.blink = blinks(t, [0.47]);
	// right hand: reach for the holstered nozzle, then ride on its grip
	P.nozzle.frame = v.frame ? v.frame(t) : NOZZLE_AIM;
	P.nozzle.aim = draw;
	P.nozzle.via = v.via;
	P.arms.R.ik = { grip: 'nozzle.rear', target: mx(WRIST.idle), mix: 1 - reachR, w: 1, pole: POLE.R, stretch: 1.26 };
	P.arms.R.hp = { relaxed: 1 - reachR, grip: reachR };
	P.arms.L.ik = { grip: 'nozzle.top', target: lerp3(WRIST.idle, WRIST.chest, draw), mix: 1 - reachL, w: 1, pole: [0.8, 0.2, -0.7], stretch: 1.26 };
	P.arms.L.hp = { relaxed: 1 - reachL, grip: reachL };
	P.feet.L.pos = [0, 0, key(t, [[0, 0], [1.1, 0], [1.3, 0.04], [1.6, 0.04]])];
	P.feet.R.pos = [0, 0, key(t, [[0, 0], [1.15, 0], [1.35, -0.05], [1.6, -0.05]])];
	return P;
}

const vacStartA = (t) => vacuumStartBase(t, {
	drawEnd: 0.95, drawEase: 'o', pullSquash: 0.08, via: [-0.72, 0.72, 0.4],
	yaw: [[0, 0], [0.45, 0], [0.62, -15], [0.86, 8, 'o'], [1.05, 0]],
});
const vacStartB = (t) => vacuumStartBase(t, { // quick-draw with a hop and a spin of the wrist
	drawEnd: 0.9, drawEase: 'b', pullSquash: 0.12, via: [-0.5, 1.15, 0.25],
	yaw: [[0, 0], [0.42, 0], [0.6, -28, 'o'], [0.8, 22, 'o'], [1.0, -4], [1.15, 0]],
	hop: [[0, 0], [0.66, 0], [0.76, 0.07, 'o'], [0.9, 0, 'i'], [1.6, 0]],
	face: (t) => ({ proud: env(t, 0.75, 0.85, 0.98, 1.1) * 0.8 }),
	frame: (t) => ({ ...NOZZLE_AIM, roll: key(t, [[0, 0], [0.62, 0], [0.8, -70], [0.95, 8, 'o'], [1.1, 0]]) }),
});
const vacStartC = (t) => vacuumStartBase(t, { // fumble, nearly drops it, catches it
	drawEnd: 1.0, drawEase: 'io', pullSquash: 0.06, via: [-0.6, 0.9, 0.55],
	yaw: [[0, 0], [0.45, 0], [0.62, -12], [0.85, 6], [1.05, 0]],
	face: (t) => ({ panic: env(t, 0.72, 0.78, 0.9, 0.98) * 2, relieved: env(t, 0.95, 1.0, 1.02, 1.08) }),
	frame: (t) => {
		const f = env(t, 0.7, 0.75, 0.9, 1.0);
		return {
			pos: add3(NOZZLE_AIM.pos, [0.05 * Math.sin(t * 60) * f, 0.06 * Math.sin(t * 45 + 1) * f, 0]),
			target: add3(NOZZLE_AIM.target, [1.6 * Math.sin(t * 38) * f, 1.4 * Math.sin(t * 31) * f, 0]),
			roll: 35 * Math.sin(t * 40) * f,
		};
	},
});

// ============================================================================
// VACUUM SUCK A/B (2.4 s loops) - fighting the pull of his own vacuum
// ============================================================================
function vacuumSuck(t, v, ctx) {
	const P = pose();
	const D = 2.4, w = TAU / D;
	const jolt = env(t, v.jolt, v.jolt + 0.08, v.jolt + 0.18, v.jolt + 0.45);
	P.body.rot = [-10 + 2 * Math.sin(2 * w * t) + 14 * jolt, v.yaw(t, w), v.roll(t, w)];
	P.body.pos = [0, 0, -0.01 + 0.04 * jolt];
	P.squash = 0.03 + 0.03 * Math.sin(2 * w * t + 0.5) - 0.06 * jolt;
	P.tremble = 0.35;
	holdNozzle(P, { pos: NOZZLE_AIM.pos, target: v.target(t, w) });
	P.gaze = [v.target(t, w)[0] * 6, -3];
	P.head = [-3 + 5 * jolt, v.target(t, w)[0] * 5, 0];
	P.face = { ...v.face, surprised: jolt * 1.5 };
	P.blink = blinks(t, v.blinks);
	P.feet.L.pos = [0, 0, 0.04 + 0.05 * jolt + ctx.noise(t, 31, 2, 0.008)];
	P.feet.R.pos = [0, 0, -0.05 + 0.04 * jolt + (v.shuffle ? 0.04 * Math.max(0, Math.sin(w * t * 2)) : 0)];
	P.feet.R.pos[1] = v.shuffle ? 0.04 * Math.max(0, Math.sin(w * t * 2)) : 0;
	return P;
}
const vacSuckA = (t, ctx) => vacuumSuck(t, {
	jolt: 1.6, blinks: [0.9], face: { strain: 0.6, focused: 0.4 },
	target: (t, w) => [0.7 * Math.sin(w * t), 0.28 + 0.12 * Math.sin(2 * w * t), 3],
	yaw: (t, w) => 9 * Math.sin(w * t), roll: (t, w) => -3 * Math.sin(w * t),
}, ctx);
const vacSuckB = (t, ctx) => vacuumSuck(t, {
	jolt: 0.8, blinks: [1.7], face: { strain: 0.5, afraid: 0.5 }, shuffle: true,
	target: (t, w) => [0.8 * Math.sin(w * t), 0.3 + 0.35 * Math.sin(2 * w * t), 3],
	yaw: (t, w) => 11 * Math.sin(w * t), roll: (t, w) => 5 * Math.sin(2 * w * t),
}, ctx);

// ============================================================================
// VACUUM STOP (0.8 s) - power off, put the nozzle back
// ============================================================================
function vacuumStop(t) {
	const P = pose();
	const back = key(t, [[0, 1], [0.18, 1], [0.6, 0, 'io']]);
	const relL = key(t, [[0, 0], [0.18, 0], [0.34, 1]]);
	const relR = key(t, [[0, 0], [0.6, 0], [0.78, 1]]);
	holdNozzle(P, NOZZLE_AIM);
	P.nozzle.aim = back;
	P.nozzle.via = [-0.72, 0.72, 0.4];
	P.arms.L.ik = { grip: 'nozzle.top', target: WRIST.idle, mix: relL, w: 1, pole: [0.8, 0.2, -0.7] };
	P.arms.R.ik = { grip: 'nozzle.rear', target: mx(WRIST.idle), mix: relR, w: 1, pole: POLE.R };
	P.arms.L.hp = { grip: 1 - relL, relaxed: relL };
	P.arms.R.hp = { grip: 1 - relR, relaxed: relR };
	P.body.rot = [key(t, [[0, -10], [0.08, -10], [0.22, 6, 'o'], [0.5, -2], [0.8, 0]]), key(t, [[0, 0], [0.25, 0], [0.5, -12], [0.8, 0]]), 0];
	P.squash = key(t, [[0, 0.03], [0.12, 0.06], [0.3, -0.03], [0.55, 0.05], [0.8, 0]]);
	P.face = { strain: key(t, [[0, 1], [0.15, 0]]), relieved: key(t, [[0, 0], [0.15, 1], [0.7, 1], [0.8, 0.3]]), neutral: key(t, [[0, 0], [0.6, 0], [0.8, 0.7]]) };
	P.faceExtra = { open: env(t, 0.1, 0.25, 0.4, 0.6) * 0.2 };
	P.gaze = saccade(t, [[0, [0, -3]], [0.3, [-28, -20]], [0.62, [0, -2]]]);
	P.head = [0, key(t, [[0, 0], [0.3, 0], [0.45, -14], [0.7, 0]]), 0];
	P.feet.L.pos = [0, 0, key(t, [[0, 0.04], [0.5, 0]])];
	P.feet.R.pos = [0, 0, key(t, [[0, -0.05], [0.5, 0]])];
	return P;
}

// ============================================================================
// ATTACK - rising uppercut (0.95 s)
// markers: HitboxStart 0.2, Impact 0.26, HitboxEnd 0.34, Land 0.62
// ============================================================================
function uppercut(t) {
	const P = combatPose(pose(), 0);
	const air = key(t, [[0, 0], [0.18, 0], [0.3, 0.3, 'o'], [0.4, 0.36], [0.62, 0, 'i'], [0.95, 0]]);
	P.body.pos = [0, air + key(t, [[0, 0], [0.16, -0.03], [0.24, 0], [0.62, 0], [0.68, -0.02], [0.95, 0]]), key(t, [[0, 0], [0.3, 0.05], [0.95, 0]])];
	P.feetFollow = env(t, 0.2, 0.26, 0.56, 0.62) * 0.92;
	P.squash = key(t, [[0, 0.04], [0.16, 0.17, 'o'], [0.26, -0.22, 'o'], [0.42, -0.08], [0.6, -0.04], [0.66, 0.22, 'o'], [0.8, -0.03], [0.95, 0.04]]);
	P.body.rot = [
		key(t, [[0, 6], [0.16, 12], [0.26, -10, 'o'], [0.5, -4], [0.66, 9], [0.95, 6]]),
		key(t, [[0, 0], [0.16, 18], [0.3, -26, 'o'], [0.55, -8], [0.95, 0]]),
		key(t, [[0, 0], [0.16, -4], [0.3, 7, 'o'], [0.6, 0]]),
	];
	P.head = [key(t, [[0, -4], [0.16, 2], [0.26, -14, 'o'], [0.6, -6], [0.95, -4]]), key(t, [[0, 0], [0.16, -10], [0.3, 10], [0.6, 0]]), 0];
	P.gaze = saccade(t, [[0, [0, 0]], [0.08, [-4, 10]], [0.22, [0, 22]], [0.62, [0, 2]]], 0.05);
	P.face = {
		determined: key(t, [[0, 0.7], [0.15, 0.3], [0.5, 0.7], [0.95, 0.7]]), focused: key(t, [[0, 0], [0.15, 1], [0.22, 0]]),
		shout: env(t, 0.2, 0.25, 0.32, 0.5) * 2, afraid: key(t, [[0, 0.3], [0.1, 0], [0.7, 0], [0.95, 0.3]]),
	};
	const R = key(t, [[0, add3(mx(WRIST.guard), [0.03, -0.03, 0.02])], [0.16, [-0.42, 0.22, 0.28], 'io'], [0.27, [-0.13, 1.02, 0.44], 'o'], [0.48, [-0.15, 0.98, 0.42]], [0.72, [-0.3, 0.55, 0.62]], [0.95, add3(mx(WRIST.guard), [0.03, -0.03, 0.02])]]);
	const Lw = key(t, [[0, WRIST.guard], [0.16, [0.4, 0.34, 0.5]], [0.3, [0.52, 0.27, 0.18], 'o'], [0.6, [0.46, 0.32, 0.4]], [0.95, WRIST.guard]]);
	arms(P, Lw, R, { hp: { fist: 1 }, ikR: { stretch: 1.3, pole: [-1, -0.2, -0.4] } });
	P.arms.R.hand = [key(t, [[0, 0], [0.27, -25], [0.6, -10], [0.95, 0]]), 0, 0];
	P.blink = 0;
	P.cap = [key(t, [[0, 0], [0.26, -6], [0.5, 4], [0.7, 0]]), 0, 0];
	return P;
}

// ============================================================================
// FLASHLIGHT BLIND A/B/C (1.3 s): draw, aim, anticipation, FLASH, recoil, holster
// markers: Flash 0.62, HitboxStart 0.62, HitboxEnd 0.74
// ============================================================================
const FLASH_MARKERS = [['Flash', 0.62], ['HitboxStart', 0.62], ['HitboxEnd', 0.74]];

function flashBase(t, v) {
	const P = combatPose(pose(), 0);
	const reach = key(t, [[0, 0], [0.13, 1, 'o']]);
	const attach = key(t, [[0, 0], [0.13, 0], [0.17, 1], [1.17, 1], [1.21, 0]]);
	const out = key(t, [[0, 0], [0.15, 0], [0.42, 1, 'o'], [1.0, 1], [1.17, 0, 'io']]);
	const toIdle = key(t, [[0, 0], [1.21, 0], [1.3, 1]]);
	const flash = env(t, 0.6, 0.62, 0.66, 0.8);
	const antic = env(t, 0.44, 0.56, 0.6, 0.63);
	const recoil = env(t, 0.62, 0.66, 0.72, 0.92);
	P.flash.attach = attach;
	const aimW = add3(v.wrist, [0, 0.05 * recoil - 0.01 * antic, -0.06 * antic - 0.07 * recoil + 0.03 * flash]);
	const holsterBlend = t < 1.21 ? out : 1 - toIdle;
	P.arms.L.ik = {
		grip: 'flashHolster.main', target: t < 1.21 ? aimW : WRIST.guard, mix: t < 1.21 ? out : toIdle,
		aim: v.aim, w: 1, stretch: 1.3, pole: [0.9, -0.5, -0.3],
	};
	P.arms.L.hp = { relaxed: 1 - reach, grip: reach * attach + (1 - attach) * reach, fist: toIdle };
	if (t >= 1.21) P.arms.L.hp = { grip: 1 - toIdle, fist: toIdle };
	P.body.rot = [
		key(t, [[0, 6], [0.4, 2], [0.56, 6], [0.66, -5, 'o'], [0.9, 2], [1.3, 6]]) + (v.lean || 0) * out,
		key(t, [[0, 0], [0.12, 8], [0.42, v.yaw, 'o'], [1.0, v.yaw], [1.3, 0]]),
		key(t, [[0, 0], [0.42, -4], [1.0, -4], [1.3, 0]]),
	];
	P.squash = 0.04 + 0.06 * antic - 0.08 * recoil;
	P.head = [key(t, [[0, -4], [0.42, v.headPitch], [1.0, v.headPitch], [1.3, -4]]), key(t, [[0, 0], [0.42, -v.yaw * 0.6], [1.0, -v.yaw * 0.6], [1.3, 0]]), 0];
	P.gaze = saccade(t, [[0, [0, 0]], [0.04, [20, -25]], [0.2, v.gaze], [1.05, [20, -20]], [1.25, [0, 0]]]);
	P.face = { determined: 0.4, focused: env(t, 0.3, 0.45, 0.66, 0.8) * 1.5, proud: env(t, 0.8, 0.95, 1.05, 1.25), afraid: 0.15 };
	P.faceExtra = { lidUp: 0.25 * flash, lidLow: 0.12 * flash };
	P.blink = 0;
	if (v.extra) v.extra(P, t);
	return P;
}
const flashA = (t) => flashBase(t, { wrist: [0.22, 0.6, 0.76], aim: [1.4, 0.75, 3.8], yaw: -18, headPitch: -4, gaze: [14, 0] });
const flashB = (t) => flashBase(t, { wrist: [0.2, 0.76, 0.7], aim: [0.2, 2.6, 2.8], yaw: -10, lean: -8, headPitch: -16, gaze: [6, 24] });
const flashC = (t) => flashBase(t, {
	wrist: [0.24, 0.54, 0.74], aim: [1.0, 0.45, 3.8], yaw: -24, headPitch: 0, gaze: [16, -4],
	extra: (P, t) => { // side-hop into the flash
		const hop = key(t, [[0, 0], [0.06, -0.02], [0.18, 0.07, 'o'], [0.3, 0, 'i'], [1.3, 0]]);
		P.body.pos = [key(t, [[0, 0], [0.3, -0.1, 'o'], [1.0, -0.1], [1.3, 0]]), hop, 0];
		P.body.rot[2] += key(t, [[0, 0], [0.18, 10], [0.32, -3], [0.5, 0]]);
		P.squash += key(t, [[0, 0], [0.05, 0.12, 'o'], [0.16, -0.12], [0.32, 0.12, 'o'], [0.45, 0.03], [1.3, 0]]);
		P.feetFollow = env(t, 0.08, 0.13, 0.25, 0.3);
	},
});

// ============================================================================
// ULTIMATE: SLAM COMBO A/B (4.8 s) - suck in, grab, slam twice, release
// markers: VacuumStart 0.55, SuctionActive 0.7, Grab 1.55, Slam01 2.55,
//          Slam02 3.5, Release 3.75, Recovery 4.3
// ============================================================================
const SLAM_MARKERS = [['VacuumStart', 0.55], ['SuctionActive', 0.7], ['Grab', 1.55], ['Slam01', 2.55], ['Slam02', 3.5], ['Release', 3.75], ['Recovery', 4.3]];
const arc = (deg, r, c = [0, 0.75, 0.25], side = 0) => {
	const a = (deg * Math.PI) / 180;
	return [c[0] + side, c[1] + r * Math.sin(a), c[2] + r * Math.cos(a)];
};

function slamBase(t, v, ctx) {
	const P = pose();
	const reachR = key(t, [[0, 0], [0.18, 1, 'o']]);
	const draw = key(t, [[0, 0], [0.18, 0], [0.45, 1, 'o'], [4.3, 1], [4.6, 0]]);
	const reachL = key(t, [[0, 0], [0.38, 0], [0.5, 1, 'o'], [4.3, 1], [4.42, 0]]);
	const relR = key(t, [[0, 0], [4.58, 0], [4.72, 1]]);
	const target = v.target(t); // enemy position (body space)
	const hi = Math.max(0, Math.min(1, (target[1] - 0.6) / 1.1));
	const behind = Math.max(0, Math.min(1, -target[2] / 0.8));
	const pos = add3(NOZZLE_AIM.pos, [0.04 * hi, 0.48 * hi + 0.1 * behind, -0.02 * hi]);
	P.nozzle.frame = { pos, target };
	P.nozzle.aim = draw;
	P.nozzle.via = [-0.72, 0.72, 0.4];
	P.nozzle.grabTarget = t > 1.55 && t < 3.75 ? target : null;
	P.arms.R.ik = { grip: 'nozzle.rear', target: mx(WRIST.idle), mix: t < 1 ? 1 - reachR : relR, w: 1, stretch: 1.35, pole: [-1, -0.2 + 0.6 * hi, -0.5] };
	P.arms.L.ik = { grip: 'nozzle.top', target: WRIST.chest, mix: 1 - reachL, w: 1, stretch: 1.35, pole: [0.8, 0.2 + 0.4 * hi, -0.7] };
	P.arms.R.hp = { grip: Math.max(reachR, 1 - relR) * (t < 4.72 ? 1 : 0), relaxed: t < 1 ? 1 - reachR : relR };
	P.arms.L.hp = { grip: reachL, relaxed: 1 - reachL };

	const s1 = env(t, 2.53, 2.56, 2.62, 2.85), s2 = env(t, 3.48, 3.51, 3.6, 3.85);
	const suck = env(t, 0.7, 0.85, 1.5, 1.6);
	const stumble = env(t, 3.75, 3.9, 4.0, 4.4);
	P.body.rot = [
		key(t, [[0, 0], [0.5, -4], [0.6, -12, 'o'], [1.55, -14], [1.7, -4], [2.25, -16], [2.5, 6, 'i'], [2.6, 17, 'o'], [2.85, 6], [3.15, -14], [3.45, 8, 'i'], [3.55, 20, 'o'], [3.8, 4], [3.95, -10], [4.4, 2], [4.8, 4]])
			+ ctx.noise(t, 41, 3, 2.5) * suck,
		key(t, v.yaw),
		key(t, v.roll || [[0, 0], [4.8, 0]]),
	];
	P.body.pos = [0, key(t, [[0, 0], [2.5, 0], [2.58, -0.03], [2.8, 0], [3.48, 0], [3.54, -0.05], [3.8, 0]]), key(t, [[0, 0], [0.7, -0.02], [1.5, -0.04], [2.58, 0.07, 'o'], [2.85, 0.02], [3.55, 0.1, 'o'], [3.8, 0.04], [4.0, -0.1, 'o'], [4.4, -0.06], [4.8, 0]])];
	P.squash = key(t, [[0, 0], [0.55, -0.04], [0.62, 0.05], [1.5, 0.04], [2.2, -0.06], [2.52, 0.0], [2.58, 0.18, 'o'], [2.85, 0.03], [3.15, -0.08], [3.5, 0], [3.56, 0.24, 'o'], [3.85, 0.04], [4.0, -0.05], [4.4, 0.06], [4.8, 0.03]]) + 0.03 * Math.sin(t * 24) * suck;
	P.tremble = 0.4 * suck + 0.2 * stumble;
	P.head = [key(t, [[0, 0], [1.6, -4], [2.2, -18], [2.55, 10, 'i'], [2.9, 0], [3.2, -16], [3.5, 12, 'i'], [3.9, 0], [4.8, -3]]), key(t, [[0, 0], [2.6, 0], [3.0, 18], [3.3, -10], [3.6, 0], [4.8, 0]]), 0];
	const gz = [Math.atan2(target[0], Math.max(0.2, target[2])) * 50, (target[1] - 0.6) * 20];
	P.gaze = t > 0.5 && t < 3.8 ? gz : saccade(t, [[0, [0, 0]], [0.05, [-25, -20]], [0.3, [0, 0]], [3.85, [0, -6]], [4.3, [-20, -15]], [4.65, [0, 0]]]);
	P.face = {
		determined: key(t, [[0, 0.8], [0.55, 0.4], [1.55, 0], [1.62, 1.4, 'o'], [2.2, 0.6], [4.8, 0.3]]),
		strain: key(t, [[0, 0], [0.6, 1], [1.55, 1], [1.62, 0.2], [2.2, 0.8], [3.75, 0.8], [3.85, 0]]),
		surprised: env(t, 1.52, 1.56, 1.62, 1.75) * 1.5,
		shout: (s1 + s2 * 1.2) * 2,
		exhausted: env(t, 3.85, 4.0, 4.45, 4.7) * 1.4,
		relieved: key(t, [[0, 0], [4.45, 0], [4.7, 1], [4.8, 0.6]]),
	};
	P.faceExtra = { open: env(t, 4.5, 4.62, 4.7, 4.8) * 0.2 };
	P.blink = blinks(t, [1.2, 4.2]);
	// feet brace, slide, stumble back a step
	P.feet.L.pos = [0, key(t, [[0, 0], [3.82, 0], [3.9, 0.05], [4.0, 0], [4.8, 0]]), key(t, [[0, 0], [0.7, 0.05], [1.5, 0.1], [1.6, 0.05], [3.8, 0.05], [3.95, -0.08], [4.8, 0]])];
	P.feet.R.pos = [0, key(t, [[0, 0], [3.92, 0], [4.0, 0.05], [4.1, 0], [4.8, 0]]), key(t, [[0, 0], [0.7, -0.06], [1.5, -0.02], [1.6, -0.06], [3.8, -0.06], [4.05, -0.14], [4.8, 0]])];
	if (v.spin) {
		const sp = v.spin(t);
		P.body.rot[1] += sp;
		P.feetFollow = sp !== 0 ? 1 : 0;
	}
	P.cap = [key(t, [[0, 0], [4.55, 0], [4.65, -6], [4.75, 3], [4.8, 0]]), 0, 0];
	return P;
}

// enemy path for A: pulled in, lifted over the head, slammed in front, then a
// wider swing around the left side and over the top into the front-right.
const slamA = (t, ctx) => slamBase(t, {
	target: (t) => key(t, [
		[0, [0, 0.6, 3.6]], [0.7, [0, 0.6, 3.6]], [1.55, [0, 0.55, 1.15], 'i'], [1.7, [0, 0.62, 1.1]],
		[1.95, arc(70, 1.15)], [2.25, arc(145, 1.25), 'o'], [2.4, arc(80, 1.3), 'i'], [2.55, arc(-21, 1.25), 'i'], [2.8, arc(-21, 1.25)],
		[2.98, [0.95, 0.9, 0.85], 'io'], [3.18, [0.75, 1.95, -0.35], 'o'], [3.35, [0.1, 1.9, 0.9], 'i'], [3.5, [-0.6, 0.3, 1.45], 'i'],
		[3.75, [-0.6, 0.3, 1.45]], [3.95, [-0.8, 1.2, 2.6], 'o'], [4.8, [-0.8, 1.2, 2.6]],
	]),
	yaw: [[0, 0], [0.12, -12], [0.45, 0], [2.6, 0], [2.98, 26], [3.18, 34], [3.5, -30, 'i'], [3.8, -18], [4.4, 0], [4.8, 0]],
	roll: [[0, 0], [2.98, -6], [3.3, 4], [3.6, 0], [4.8, 0]],
}, ctx);
// B: first lift sweeps over the left shoulder, then a full 360 hammer spin.
const slamB = (t, ctx) => slamBase(t, {
	target: (t) => key(t, [
		[0, [0, 0.6, 3.6]], [0.7, [0, 0.6, 3.6]], [1.55, [0, 0.55, 1.15], 'i'], [1.7, [0.1, 0.62, 1.1]],
		[2.0, [1.05, 1.2, 0.3]], [2.25, [0.4, 1.95, -0.4], 'o'], [2.4, [0.2, 1.6, 0.7], 'i'], [2.55, [0.55, 0.3, 1.3], 'i'], [2.8, [0.55, 0.3, 1.3]],
		[2.95, [0.4, 0.9, 1.2]], [3.3, [0.3, 1.05, 1.25]], [3.42, [0.1, 1.5, 0.9], 'o'], [3.5, [0, 0.3, 1.4], 'i'],
		[3.75, [0, 0.3, 1.4]], [3.95, [0.2, 1.3, 2.7], 'o'], [4.8, [0.2, 1.3, 2.7]],
	]),
	yaw: [[0, 0], [0.12, -12], [0.45, 0], [1.7, 0], [2.0, 18], [2.3, -6], [2.55, 10], [2.8, 6], [3.5, 0], [4.8, 0]],
	roll: [[0, 0], [1.9, -8], [2.4, 4], [2.6, 0], [4.8, 0]],
	spin: (t) => (t > 2.85 && t < 3.42 ? 360 * EASE.io((t - 2.85) / 0.57) : 0),
}, ctx);

// ============================================================================
// DODGES (0.6 s): A = hop, B = roll.  markers: IFrameStart 0.06, IFrameEnd 0.4
// Root motion is applied by the game (identical for both variants).
// ============================================================================
const DODGE_MARKERS = [['IFrameStart', 0.06], ['IFrameEnd', 0.4], ['Land', 0.42]];
const DIRS = { Left: [1, 0], Right: [-1, 0], Back: [0, -1] };
const dodgeMotion = (dir) => (t) => {
	const f = EASE.o(Math.min(1, t / 0.45));
	return [DIRS[dir][0] * 1.5 * f, 0, DIRS[dir][1] * 1.3 * f];
};

function dodgeHop(t, dir) {
	const P = combatPose(pose(), 0);
	const [dx, dz] = DIRS[dir];
	const air = key(t, [[0, 0], [0.08, 0], [0.22, 0.17, 'o'], [0.38, 0, 'i'], [0.6, 0]]);
	P.body.pos = [0, air, 0];
	P.feetFollow = env(t, 0.08, 0.12, 0.34, 0.38) * 0.9;
	P.squash = key(t, [[0, 0.04], [0.07, 0.15, 'o'], [0.16, -0.12, 'o'], [0.34, -0.04], [0.42, 0.16, 'o'], [0.6, 0.04]]);
	P.body.rot = [
		key(t, [[0, 6], [0.07, 10], [0.22, dz < 0 ? -18 : 4], [0.42, 8], [0.6, 6]]),
		key(t, [[0, 0], [0.22, -dx * 10], [0.6, 0]]),
		key(t, [[0, 0], [0.07, dx * 6], [0.22, -dx * 20, 'o'], [0.42, dx * 6], [0.6, 0]]),
	];
	P.head = [key(t, [[0, -4], [0.2, dz < 0 ? 8 : -8], [0.6, -4]]), key(t, [[0, 0], [0.2, -dx * 12], [0.6, 0]]), key(t, [[0, 0], [0.22, dx * 10], [0.6, 0]])];
	P.face = { startled: env(t, 0, 0.06, 0.2, 0.3) * 2, focused: env(t, 0.2, 0.3, 0.45, 0.6), determined: 0.5 };
	const flail = env(t, 0.08, 0.16, 0.34, 0.45);
	const [lg, rg] = [WRIST.guard, add3(mx(WRIST.guard), [0.03, -0.03, 0.02])];
	arms(P, lerp3(lg, [0.55, 0.6, 0.32], flail), lerp3(rg, [-0.55, 0.62, 0.3], flail), { hp: { fist: 1 - flail, spread: flail * 2 } });
	P.gaze = [dx * -10, 4 * flail];
	return P;
}

function dodgeRoll(t, dir) {
	const P = combatPose(pose(), 0);
	const [dx, dz] = DIRS[dir];
	const roll = 360 * EASE.io(Math.min(1, Math.max(0, (t - 0.08) / 0.34)));
	P.body.pos = [0, Math.sin(Math.PI * Math.min(1, Math.max(0, (t - 0.08) / 0.34))) * 0.1, 0];
	P.feetFollow = env(t, 0.05, 0.1, 0.4, 0.46);
	P.body.rot = [dz < 0 ? 6 - roll : 6 + key(t, [[0, 0], [0.45, 0], [0.5, 6], [0.6, 0]]), 0, dx !== 0 ? -dx * roll : 0];
	P.squash = key(t, [[0, 0.04], [0.07, 0.14, 'o'], [0.15, -0.05], [0.38, -0.04], [0.45, 0.17, 'o'], [0.6, 0.04]]);
	P.face = { strain: env(t, 0.06, 0.12, 0.38, 0.44), eyesClosed: env(t, 0.08, 0.12, 0.36, 0.42), startled: env(t, 0.44, 0.48, 0.52, 0.6), determined: 0.4 };
	const tuck = env(t, 0.06, 0.12, 0.38, 0.46);
	arms(P, lerp3(WRIST.guard, WRIST.chest, tuck), lerp3(add3(mx(WRIST.guard), [0.03, -0.03, 0.02]), mx(WRIST.chest), tuck), { hp: { fist: 1 } });
	P.head = [-4 + 12 * tuck, 0, 0];
	return P;
}

// ============================================================================
// FACE OVERLAYS (2 s loops) - only face bones, for layering on any clip
// ============================================================================
function faceOnly(name, opts = {}) {
	return (t, ctx) => {
		const P = pose();
		P.face = { [name]: 1 };
		P.gaze = [ctx.noise(t, 51, 0.6, opts.dart ? 14 : 4), ctx.noise(t, 52, 0.5, opts.dart ? 6 : 2) + (opts.pitch || 0)];
		if (opts.dart) P.gaze = saccade(t, [[0, [0, 0]], [0.4, [18, 2]], [0.9, [-16, 0]], [1.4, [8, 4]], [1.9, [0, 0]]], 0.05);
		P.blink = opts.noBlink ? 0 : blinks(t, [0.55, 1.6]);
		if (opts.tremble) P.faceExtra = { browIn: ctx.noise(t, 53, 9, 0.002), wide: ctx.noise(t, 54, 11, 0.1) };
		return P;
	};
}

// ============================================================================
const C = (name, group, duration, fn, o = {}) => ({ name, group, duration, fn, ...o });
const FACE_DE = {
	Neutral: 'neutral', Afraid: 'ängstlich', Startled: 'erschrocken', Panic: 'panisch', Focused: 'konzentriert',
	Angry: 'wütend', Relieved: 'erleichtert', Proud: 'stolz', Confused: 'verwirrt',
};
export const CLIPS = [
	C('Idle_Fear', 'Idle_Fear', 6, idleFear, { loop: true, priority: 'Idle', label: 'Idle 1 – ängstliches Zittern' }),
	C('Idle_LookAround', 'Idle_LookAround', 6, idleLookAround, { loop: true, priority: 'Idle', label: 'Idle 2 – nervöses Umschauen' }),
	C('Idle_Courage', 'Idle_Courage', 6, idleCourage, { loop: true, priority: 'Idle', label: 'Idle 3 – Mut sammeln' }),
	C('Combat_Idle', 'Combat_Idle', 2, combatIdle, { loop: true, priority: 'Idle', label: 'Combat Idle' }),
	C('Run', 'Run', 0.6, run, { loop: true, priority: 'Movement', label: 'Laufen' }),
	C('Vacuum_Start_A', 'Vacuum_Start', 1.6, vacStartA, { variant: 'A', priority: 'Action', markers: VAC_MARKERS, label: 'Staubsauger ziehen A' }),
	C('Vacuum_Start_B', 'Vacuum_Start', 1.6, vacStartB, { variant: 'B', priority: 'Action', markers: VAC_MARKERS, label: 'Staubsauger ziehen B (Quick-Draw)' }),
	C('Vacuum_Start_C', 'Vacuum_Start', 1.6, vacStartC, { variant: 'C', priority: 'Action', markers: VAC_MARKERS, label: 'Staubsauger ziehen C (Fummeln)' }),
	C('Vacuum_Suck_A', 'Vacuum_Suck', 2.4, vacSuckA, { variant: 'A', loop: true, priority: 'Action', markers: [['SuctionActive', 0]], label: 'Saugen A' }),
	C('Vacuum_Suck_B', 'Vacuum_Suck', 2.4, vacSuckB, { variant: 'B', loop: true, priority: 'Action', markers: [['SuctionActive', 0]], label: 'Saugen B' }),
	C('Vacuum_Stop', 'Vacuum_Stop', 0.8, vacuumStop, { priority: 'Action', markers: [['VacuumStop', 0.08], ['Recovery', 0.6]], label: 'Staubsauger wegstecken' }),
	C('Attack_Uppercut', 'Attack_Uppercut', 0.95, uppercut, { priority: 'Action2', markers: [['HitboxStart', 0.2], ['Impact', 0.26], ['HitboxEnd', 0.34], ['Land', 0.62], ['Recovery', 0.8]], label: 'Aufwärtshieb' }),
	C('Flash_A', 'Flash', 1.3, flashA, { variant: 'A', priority: 'Action2', markers: FLASH_MARKERS, label: 'Taschenlampe A (horizontal)' }),
	C('Flash_B', 'Flash', 1.3, flashB, { variant: 'B', priority: 'Action2', markers: FLASH_MARKERS, label: 'Taschenlampe B (diagonal)' }),
	C('Flash_C', 'Flash', 1.3, flashC, { variant: 'C', priority: 'Action2', markers: FLASH_MARKERS, label: 'Taschenlampe C (nach Ausweichen)' }),
	C('SlamCombo_A', 'SlamCombo', 4.8, slamA, { variant: 'A', priority: 'Action3', markers: SLAM_MARKERS, label: 'Ultimate A – Einsaugen + 2× Slam' }),
	C('SlamCombo_B', 'SlamCombo', 4.8, slamB, { variant: 'B', priority: 'Action3', markers: SLAM_MARKERS, label: 'Ultimate B – Hammerwurf-Slam' }),
	...['Left', 'Right', 'Back'].flatMap((dir) => [
		C(`Dodge_${dir}_A`, `Dodge_${dir}`, 0.6, (t) => dodgeHop(t, dir), { variant: 'A', priority: 'Action3', markers: DODGE_MARKERS, rootMotion: dodgeMotion(dir), label: `Ausweichen ${({ Left: 'links', Right: 'rechts', Back: 'zurück' })[dir]} A (Sprung)` }),
		C(`Dodge_${dir}_B`, `Dodge_${dir}`, 0.6, (t) => dodgeRoll(t, dir), { variant: 'B', priority: 'Action3', markers: DODGE_MARKERS, rootMotion: dodgeMotion(dir), label: `Ausweichen ${({ Left: 'links', Right: 'rechts', Back: 'zurück' })[dir]} B (Rolle)` }),
	]),
	...[
		['Neutral', 'neutral', {}], ['Afraid', 'afraid', { tremble: true, dart: true }], ['Startled', 'startled', { noBlink: true }],
		['Panic', 'panic', { tremble: true, dart: true }], ['Focused', 'focused', {}], ['Angry', 'angry', {}],
		['Relieved', 'relieved', {}], ['Proud', 'proud', { pitch: 4 }], ['Confused', 'confused', { pitch: 6 }],
	].map(([n, expr, o]) => C(`Face_${n}`, `Face_${n}`, 2, faceOnly(expr, o), { loop: true, faceOnly: true, priority: 'Action4', label: `Mimik: ${FACE_DE[n]}` })),
];
