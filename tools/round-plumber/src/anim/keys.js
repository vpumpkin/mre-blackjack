// Keyframe helpers used by the clip authoring code.
//
// key(t, [[time, value, ease], ...]) interpolates numbers or arrays. The ease
// of a key describes how the motion *arrives* at that key:
//   'io' ease-in-out (default)  'o' ease-out (snappy)  'i' ease-in (accelerate)
//   'b'  overshoot (back)       'l' linear             'h' hold (step)
export const EASE = {
	l: (x) => x,
	io: (x) => x * x * (3 - 2 * x),
	o: (x) => 1 - (1 - x) ** 3,
	i: (x) => x * x * x,
	b: (x) => { const c = 1.9; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2; },
	h: () => 0,
};

export function key(t, keys) {
	if (t <= keys[0][0]) return keys[0][1];
	for (let i = 1; i < keys.length; i++) {
		const [t1, v1, ease = 'io'] = keys[i];
		if (t <= t1) {
			const [t0, v0] = keys[i - 1];
			const f = EASE[ease]((t - t0) / Math.max(1e-6, t1 - t0));
			return mix(v0, v1, f);
		}
	}
	return keys[keys.length - 1][1];
}

function mix(a, b, f) {
	if (typeof a === 'number') return a + (b - a) * f;
	if (Array.isArray(a)) return a.map((v, i) => v + (b[i] - v) * f);
	// objects of weights (expressions, hand poses)
	const out = {};
	for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) out[k] = (a[k] || 0) + ((b[k] || 0) - (a[k] || 0)) * f;
	return out;
}

// 0 -> 1 -> 0 envelope: rises over [a, b], holds, falls over [c, d]
export function env(t, a, b, c, d) {
	if (t <= a || t >= d) return 0;
	if (t < b) return EASE.io((t - a) / (b - a));
	if (t <= c) return 1;
	return 1 - EASE.io((t - c) / (d - c));
}

// Loop-safe organic noise: a few sines whose frequencies are whole multiples
// of 1/D, so the signal repeats exactly every D seconds.
export function makeNoise(D) {
	return (t, seed = 0, hz = 1, amp = 1) => {
		let v = 0;
		for (let k = 0; k < 3; k++) {
			const f = Math.max(1, Math.round((hz * (1 + 0.37 * k + 0.13 * ((seed * 7 + k * 3) % 5))) * D)) / D;
			v += Math.sin(2 * Math.PI * f * t + seed * 1.7 + k * 2.1) / (k + 1);
		}
		return (v / 1.83) * amp;
	};
}

// Snappy saccade-like steps between gaze targets: [[time, [yaw, pitch]], ...]
export function saccade(t, keys, dur = 0.07) {
	let cur = keys[0][1];
	for (let i = 1; i < keys.length; i++) {
		const [ti, vi] = keys[i];
		if (t >= ti + dur) cur = vi;
		else if (t > ti) { const f = EASE.o((t - ti) / dur); return cur.map((v, k) => v + (vi[k] - v) * f); }
		else break;
	}
	return cur;
}

// Quick blink: 0 -> 1 -> 0 around each listed time.
export function blinks(t, times, close = 0.06, open = 0.1) {
	let b = 0;
	for (const bt of times) {
		if (t >= bt - close && t <= bt) b = Math.max(b, EASE.io((t - (bt - close)) / close));
		else if (t > bt && t <= bt + open) b = Math.max(b, 1 - EASE.io((t - bt) / open));
	}
	return b;
}
