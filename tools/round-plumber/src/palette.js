// Colour palette texture. Every part of the model samples the centre of one
// swatch, so a single 512x512 texture (plus matching roughness / metalness
// maps) colours the whole character. This keeps the asset to one material,
// which imports cleanly into Roblox (SurfaceAppearance) and any glTF viewer.
import zlib from 'node:zlib';

export const GRID = 16;
export const SIZE = 512;

// name: [hex colour, roughness, metalness]
const SWATCHES = {
	skin: ['#febd9a', 0.55, 0], skinShade: ['#e89d78', 0.6, 0], ear: ['#f8b38f', 0.6, 0],
	lips: ['#b5544c', 0.5, 0], mouth: ['#5a1a1e', 0.7, 0], tongue: ['#d0626a', 0.45, 0], teeth: ['#fbf7ef', 0.3, 0],
	cap: ['#38a135', 0.82, 0], capDark: ['#287a26', 0.85, 0], shirt: ['#339c36', 0.86, 0], shirtDark: ['#267a29', 0.88, 0],
	emblem: ['#f5f1e6', 0.6, 0], emblemSymbol: ['#2fa43c', 0.7, 0],
	overalls: ['#0e3063', 0.9, 0], overallsDark: ['#0a2550', 0.92, 0], stitch: ['#6f8fe0', 0.8, 0],
	button: ['#f2c623', 0.35, 0.35], star: ['#f0c419', 0.55, 0.1],
	glove: ['#f9f8fa', 0.65, 0], gloveLine: ['#c9c9c4', 0.7, 0],
	shoe: ['#6a3b1e', 0.55, 0], sole: ['#3b2010', 0.7, 0],
	hair: ['#8b340b', 0.75, 0], mustache: ['#300b09', 0.6, 0], brow: ['#2e0b09', 0.65, 0],
	sclera: ['#fafaf7', 0.2, 0], iris: ['#1783c8', 0.25, 0], irisRing: ['#0c4a86', 0.3, 0], pupil: ['#0a0c14', 0.15, 0],
	highlight: ['#ffffff', 0.1, 0],
	tank: ['#2d6f73', 0.45, 0.55], tankDark: ['#1e4c50', 0.5, 0.5], copper: ['#c27a3a', 0.35, 0.9],
	steel: ['#b8c0c6', 0.3, 0.95], rubber: ['#24262a', 0.8, 0], hose: ['#3a4048', 0.6, 0.1], hoseRib: ['#2a2f36', 0.65, 0.1],
	gaugeFace: ['#f3eedf', 0.4, 0], needle: ['#d42a1e', 0.4, 0], strap: ['#4b3a2c', 0.8, 0], buckle: ['#c8ccd0', 0.3, 0.9],
	flashBody: ['#f2b71c', 0.45, 0.05], flashHead: ['#c3c9cf', 0.25, 0.95],
	glowCyan: ['#5ff7ff', 0.3, 0], glowWarm: ['#fff3c4', 0.2, 0], glowGreen: ['#7dff8a', 0.3, 0],
};

export const SWATCH_INDEX = Object.fromEntries(Object.keys(SWATCHES).map((k, i) => [k, i]));

// UV at the centre of a swatch (glTF convention: v grows downwards).
export function swatchUV(name) {
	const i = SWATCH_INDEX[name];
	if (i === undefined) throw new Error(`unknown swatch ${name}`);
	return [((i % GRID) + 0.5) / GRID, (Math.floor(i / GRID) + 0.5) / GRID];
}

const hexRGB = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));

function crc32(buf) {
	let c, crc = 0xffffffff;
	for (let n = 0; n < buf.length; n++) {
		c = (crc ^ buf[n]) & 0xff;
		for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
		crc = (crc >>> 8) ^ c;
	}
	return (crc ^ 0xffffffff) >>> 0;
}

function png(width, height, rgb) {
	const raw = Buffer.alloc((width * 3 + 1) * height);
	for (let y = 0; y < height; y++) {
		raw[y * (width * 3 + 1)] = 0;
		rgb.copy(raw, y * (width * 3 + 1) + 1, y * width * 3, (y + 1) * width * 3);
	}
	const chunk = (type, data) => {
		const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
		const td = Buffer.concat([Buffer.from(type), data]);
		const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
		return Buffer.concat([len, td, crc]);
	};
	const ihdr = Buffer.alloc(13);
	ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4);
	ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
	return Buffer.concat([
		Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
		chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0)),
	]);
}

// kind: 'color' | 'orm' (glTF occlusion/roughness/metalness) | 'roughness' | 'metalness'
export function paletteImage(kind) {
	const cell = SIZE / GRID;
	const rgb = Buffer.alloc(SIZE * SIZE * 3);
	const entries = Object.values(SWATCHES);
	for (let y = 0; y < SIZE; y++) {
		for (let x = 0; x < SIZE; x++) {
			const i = Math.floor(y / cell) * GRID + Math.floor(x / cell);
			const [hex, rough, metal] = entries[i] || ['#808080', 0.8, 0];
			let px;
			if (kind === 'color') px = hexRGB(hex);
			else if (kind === 'orm') px = [255, Math.round(rough * 255), Math.round(metal * 255)];
			else if (kind === 'roughness') px = [rough, rough, rough].map((v) => Math.round(v * 255));
			else px = [metal, metal, metal].map((v) => Math.round(v * 255));
			rgb.set(px, (y * SIZE + x) * 3);
		}
	}
	return png(SIZE, SIZE, rgb);
}

// Linear-space colour of a swatch (used for preview vertex tinting in tests).
export function swatchHex(name) { return SWATCHES[name][0]; }
