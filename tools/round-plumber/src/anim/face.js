// Facial expressions as bone-channel presets. Every channel is a plain number
// (radians or metres); expressions blend as a weighted average, and clips can
// add per-channel extras on top (blinks, tremble, lip sync style accents).
//
// Channels (per side where it makes sense):
//   lidUp   upper lid rotation, + closes          lidLow  lower lid, + raises
//   browIn / browOut  vertical offset of the brow ends, browSq inward squeeze
//   pupil   visible pupil size multiplier (1 = rest)
//   open    mouth opening 0..1   smile -1..1   wide -1..1 (stretch/pucker)
//   cheek   cheek raise 0..1     nose  nose scrunch 0..1   stache mustache lift
export const CHANNELS = ['lidUp', 'lidLow', 'browIn', 'browOut', 'browSq', 'pupil', 'open', 'smile', 'wide', 'cheek', 'nose', 'stache', 'shift'];
const SIDED = new Set(['lidUp', 'lidLow', 'browIn', 'browOut', 'browSq', 'smile', 'cheek']);

const base = { lidUp: -0.2, lidLow: -0.08, browIn: 0, browOut: 0, browSq: 0, pupil: 1, open: 0, smile: 0.35, wide: 0, cheek: 0.15, nose: 0, stache: 0, shift: 0 };
const P = (o) => ({ ...base, ...o });

export const EXPRESSIONS = {
	neutral: P({}),
	afraid: P({ lidUp: -0.38, lidLow: -0.04, browIn: 0.017, browOut: -0.004, pupil: 0.62, open: 0.12, smile: -0.55, wide: 0.35, cheek: 0 }),
	startled: P({ lidUp: -0.5, lidLow: -0.1, browIn: 0.021, browOut: 0.015, pupil: 0.5, open: 0.6, smile: -0.25, wide: -0.35, cheek: 0, stache: 0.3 }),
	panic: P({ lidUp: -0.52, lidLow: -0.08, browIn: 0.023, browOut: 0.004, pupil: 0.42, open: 0.85, smile: -0.7, wide: 0.55, cheek: 0.1, stache: 0.4 }),
	focused: P({ lidUp: 0.24, lidLow: 0.2, browIn: -0.011, browOut: 0.002, browSq: 0.006, open: 0, smile: -0.1, wide: -0.3, cheek: 0.2 }),
	angry: P({ lidUp: 0.16, lidLow: 0.14, browIn: -0.018, browOut: 0.008, browSq: 0.01, pupil: 0.85, open: 0.22, smile: -0.75, wide: 0.45, cheek: 0.35, nose: 0.6 }),
	relieved: P({ lidUp: 0.3, lidLow: 0.06, browIn: 0.009, browOut: -0.005, pupil: 1.1, open: 0.06, smile: 0.85, wide: 0.2, cheek: 0.45 }),
	proud: P({ lidUp: 0.14, lidLow: 0.12, browIn: -0.003, browOut: 0.011, open: 0, smile: 1, wide: 0.35, cheek: 0.65 }),
	confused: P({
		lidUp_L: -0.3, lidUp_R: 0.12, browIn_L: 0.018, browOut_L: 0.015, browIn_R: -0.008, browOut_R: -0.006,
		open: 0.08, smile: -0.2, wide: -0.15, shift: 0.012, pupil: 0.95,
	}),
	strain: P({ lidUp: 0.5, lidLow: 0.32, browIn: -0.014, browOut: -0.004, browSq: 0.008, open: 0.16, smile: -0.4, wide: 0.7, cheek: 0.75, nose: 0.8 }),
	determined: P({ lidUp: 0.1, lidLow: 0.09, browIn: -0.012, browOut: 0.004, browSq: 0.004, smile: 0.15, wide: -0.1, cheek: 0.25 }),
	exhausted: P({ lidUp: 0.48, lidLow: 0.04, browIn: 0.01, browOut: -0.009, pupil: 1.05, open: 0.38, smile: -0.2, cheek: 0 }),
	surprised: P({ lidUp: -0.46, lidLow: -0.06, browIn: 0.02, browOut: 0.018, pupil: 0.8, open: 0.38, smile: 0, wide: -0.3 }),
	shout: P({ lidUp: 0.05, lidLow: 0.1, browIn: -0.016, browOut: 0.006, browSq: 0.008, open: 1, smile: -0.3, wide: 0.3, cheek: 0.5, nose: 0.5, stache: 0.5 }),
	eyesClosed: P({ lidUp: 0.95, lidLow: 0.22, browIn: 0.004, smile: 0.1, cheek: 0.2 }),
};

const sideVal = (preset, ch, side) => preset[`${ch}${side}`] ?? preset[ch] ?? base[ch];

// weights: { name: w } -> { lidUp_L, lidUp_R, ..., open, ... }
export function evalFace(weights = { neutral: 1 }, extra = {}) {
	const out = {};
	let total = 0;
	for (const w of Object.values(weights)) total += Math.max(0, w);
	if (total <= 1e-6) weights = { neutral: 1 }, total = 1;
	for (const ch of CHANNELS) {
		for (const side of SIDED.has(ch) ? ['_L', '_R'] : ['']) {
			let v = 0;
			for (const [name, w] of Object.entries(weights)) {
				if (w <= 0) continue;
				const preset = EXPRESSIONS[name];
				if (!preset) throw new Error(`unknown expression ${name}`);
				v += sideVal(preset, ch, side) * (w / total);
			}
			out[ch + side] = v + (extra[ch] ?? 0) + (side ? extra[ch + side] ?? 0 : 0);
		}
	}
	return out;
}
