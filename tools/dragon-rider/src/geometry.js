// Small procedural-modelling toolkit used by the dragon builder.
// Everything is built in model (world) space; rigid parts are later re-based
// onto the bone they hang from, skinned parts get per-vertex bone weights.
import * as THREE from 'three';

export const V = (x, y, z) => new THREE.Vector3(x, y, z);
export const vec = (a) => (a.isVector3 ? a.clone() : new THREE.Vector3(a[0], a[1], a[2]));
export const lerp = (a, b, t) => a + (b - a) * t;
export const clamp01 = (x) => Math.min(1, Math.max(0, x));
export const smooth = (x) => { x = clamp01(x); return x * x * (3 - 2 * x); };

// Deterministic PRNG so every build produces the identical model.
export function makeRandom(seed) {
	return () => {
		seed = (seed + 0x6d2b79f5) | 0;
		let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

// Uniform Catmull-Rom interpolation over an array of numbers or number tuples.
export function interp(arr, u) {
	const n = arr.length - 1;
	const s = clamp01(u) * n;
	const i = Math.min(Math.floor(s), n - 1);
	const f = s - i;
	const p0 = arr[Math.max(i - 1, 0)], p1 = arr[i], p2 = arr[i + 1], p3 = arr[Math.min(i + 2, n)];
	const cr = (a, b, c, d) => 0.5 * (2 * b + (-a + c) * f + (2 * a - 5 * b + 4 * c - d) * f * f + (-a + 3 * b - 3 * c + d) * f * f * f);
	if (Array.isArray(p1)) return p1.map((_, k) => cr(p0[k], p1[k], p2[k], p3[k]));
	return cr(p0, p1, p2, p3);
}

const tmpColor = new THREE.Color();

// Normalises a geometry so it can be merged with every other part:
// indexed, no uvs/groups, has normals and a vertex colour attribute.
export function finish(geo, color) {
	if (!geo.index) {
		const n = geo.attributes.position.count;
		const idx = new (n > 65535 ? Uint32Array : Uint16Array)(n);
		for (let i = 0; i < n; i++) idx[i] = i;
		geo.setIndex(new THREE.BufferAttribute(idx, 1));
	}
	for (const name of Object.keys(geo.attributes)) {
		if (!['position', 'normal', 'color', 'skinIndex', 'skinWeight'].includes(name)) geo.deleteAttribute(name);
	}
	geo.clearGroups();
	if (!geo.attributes.normal) geo.computeVertexNormals();
	if (color !== undefined) paint(geo, color);
	return geo;
}

// color: THREE.Color | hex | (position: Vector3, index) => THREE.Color
export function paint(geo, color) {
	const pos = geo.attributes.position;
	const out = new Float32Array(pos.count * 3);
	const p = new THREE.Vector3();
	const fixed = typeof color === 'function' ? null : (color.isColor ? color : tmpColor.set(color)).clone();
	for (let i = 0; i < pos.count; i++) {
		const c = fixed || color(p.fromBufferAttribute(pos, i), i);
		out[i * 3] = c.r; out[i * 3 + 1] = c.g; out[i * 3 + 2] = c.b;
	}
	geo.setAttribute('color', new THREE.BufferAttribute(out, 3));
	return geo;
}

export function transform(geo, { p = [0, 0, 0], r = [0, 0, 0], s = [1, 1, 1], order = 'XYZ' } = {}) {
	const m = new THREE.Matrix4().compose(
		vec(p),
		new THREE.Quaternion().setFromEuler(new THREE.Euler(r[0], r[1], r[2], order)),
		Array.isArray(s) ? vec(s) : V(s, s, s),
	);
	return geo.applyMatrix4(m);
}

export function ellipsoid(c, r, color, { w = 20, h = 14, rot = [0, 0, 0] } = {}) {
	const g = new THREE.SphereGeometry(1, w, h);
	transform(g, { p: c, r: rot, s: r });
	return finish(g, color);
}

export function icosphere(c, r, color, detail = 1) {
	const g = new THREE.IcosahedronGeometry(r, detail);
	g.translate(...vec(c).toArray());
	return finish(g, color);
}

// Stretches a unit-height +Y geometry so it spans from a to b.
function alongY(g, a, b) {
	a = vec(a); b = vec(b);
	const d = b.clone().sub(a);
	const len = d.length();
	g.scale(1, len, 1);
	g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(V(0, 1, 0), d.normalize()));
	g.translate(a.x, a.y, a.z);
	return g;
}

// Cone with its base at a and its tip at b. sx/sz flatten the base.
export function cone(a, b, r, color, { seg = 8, sx = 1, sz = 1 } = {}) {
	const g = new THREE.ConeGeometry(r, 1, seg, 1);
	g.translate(0, 0.5, 0);
	g.scale(sx, 1, sz);
	return finish(alongY(g, a, b), color);
}

export function cylinder(a, b, r0, r1, color, seg = 10) {
	const g = new THREE.CylinderGeometry(r1, r0, 1, seg, 1);
	g.translate(0, 0.5, 0);
	return finish(alongY(g, a, b), color);
}

// Lofts a (super)elliptical cross-section along a Catmull-Rom curve.
//
// opts.radii    [[rx, ry], ...] per control point (interpolated) or (u) => [rx, ry]
// opts.owners   bone index per curve segment -> produces a skinned geometry
// opts.ownerBefore / ownerAfter  bones to blend into at the open ends
// opts.color    (u, theta, dirWorld, ringIndex, pos) => THREE.Color, or a colour
// opts.up       initial "up" hint for the parallel-transported frame
// opts.square   superellipse exponent (2 = ellipse, higher = boxier)
// opts.ridge    adds a dorsal ridge on the +up side
// opts.noise    (u, theta) => radius multiplier
export function loft(points, opts = {}) {
	const pts = points.map(vec);
	const n = pts.length - 1;
	const curve = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', opts.tension ?? 0.5);
	const perSeg = opts.perSeg ?? 6;
	const rings = n * perSeg;
	const radial = opts.radial ?? 16;
	const square = opts.square ?? 2;
	const radiusAt = typeof opts.radii === 'function' ? opts.radii : (u) => interp(opts.radii, u);

	const positions = [];
	const colors = [];
	const skinIndex = [];
	const skinWeight = [];
	const index = [];
	const frames = [];

	let prevN = null;
	const up0 = vec(opts.up ?? [0, 1, 0]);
	const dir = new THREE.Vector3();
	const p = new THREE.Vector3();

	const weightsAt = (u) => {
		if (!opts.owners) return null;
		const s = u * n;
		const j = Math.min(Math.floor(s), n - 1);
		const f = s - j;
		const blend = opts.blend ?? 0.5;
		const w = new Map();
		const add = (b, x) => { if (b === undefined || b === null || x <= 0) return; w.set(b, (w.get(b) || 0) + x); };
		const prev = j > 0 ? opts.owners[j - 1] : opts.ownerBefore;
		const next = j < n - 1 ? opts.owners[j + 1] : opts.ownerAfter;
		let wp = 0, wn = 0;
		if (prev !== undefined && f < blend) wp = 0.5 * (1 - smooth(f / blend));
		if (next !== undefined && f > 1 - blend) wn = 0.5 * (1 - smooth((1 - f) / blend));
		add(opts.owners[j], 1 - wp - wn);
		add(prev, wp);
		add(next, wn);
		return [...w.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
	};

	const pushSkin = (wts) => {
		if (!wts) return;
		const total = wts.reduce((s, e) => s + e[1], 0);
		for (let k = 0; k < 4; k++) {
			skinIndex.push(wts[k] ? wts[k][0] : 0);
			skinWeight.push(wts[k] ? wts[k][1] / total : 0);
		}
	};

	const colorAt = (u, th, d, i, pos) => {
		const c = opts.color;
		if (c === undefined) return tmpColor.set(0xffffff);
		if (typeof c === 'function') return c(u, th, d, i, pos);
		return c.isColor ? c : tmpColor.set(c);
	};

	for (let i = 0; i <= rings; i++) {
		const u = i / rings;
		const c = curve.getPoint(u);
		const t = curve.getTangent(u).normalize();
		const base = prevN || up0;
		const nrm = base.clone().sub(t.clone().multiplyScalar(base.dot(t))).normalize();
		prevN = nrm;
		const side = new THREE.Vector3().crossVectors(t, nrm).normalize();
		const [rx, ry] = radiusAt(u).map((r) => Math.max(r, 0.002));
		frames.push({ u, c: c.clone(), t: t.clone(), n: nrm.clone(), side: side.clone(), rx, ry });
		const wts = weightsAt(u);
		for (let j = 0; j < radial; j++) {
			const th = (j / radial) * Math.PI * 2;
			const cs = Math.cos(th), sn = Math.sin(th);
			let x = Math.sign(cs) * Math.pow(Math.abs(cs), 2 / square);
			let y = Math.sign(sn) * Math.pow(Math.abs(sn), 2 / square);
			let k = 1;
			if (opts.ridge) k *= 1 + opts.ridge * Math.pow(Math.max(0, sn), 10);
			if (opts.noise) k *= opts.noise(u, th);
			dir.copy(side).multiplyScalar(cs).addScaledVector(nrm, sn).normalize();
			p.copy(c).addScaledVector(side, x * rx * k).addScaledVector(nrm, y * ry * k);
			positions.push(p.x, p.y, p.z);
			const col = colorAt(u, th, dir, i, p);
			colors.push(col.r, col.g, col.b);
			pushSkin(wts);
		}
	}

	for (let i = 0; i < rings; i++) {
		for (let j = 0; j < radial; j++) {
			const a = i * radial + j;
			const b = i * radial + ((j + 1) % radial);
			const c = (i + 1) * radial + j;
			const d = (i + 1) * radial + ((j + 1) % radial);
			index.push(a, c, b, b, c, d);
		}
	}

	const addCap = (ring, center, u, atStart) => {
		const ci = positions.length / 3;
		positions.push(center.x, center.y, center.z);
		const col = colorAt(u, -Math.PI / 2, frames[ring].t.clone().multiplyScalar(atStart ? -1 : 1), ring, center);
		colors.push(col.r, col.g, col.b);
		pushSkin(weightsAt(u));
		for (let j = 0; j < radial; j++) {
			const a = ring * radial + j;
			const b = ring * radial + ((j + 1) % radial);
			if (atStart) index.push(ci, a, b); else index.push(ci, b, a);
		}
	};
	if (opts.capStart !== false) addCap(0, frames[0].c, 0, true);
	if (opts.capEnd !== false) addCap(rings, frames[rings].c, 1, false);

	const geo = new THREE.BufferGeometry();
	geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
	geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
	if (opts.owners) {
		geo.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(skinIndex, 4));
		geo.setAttribute('skinWeight', new THREE.Float32BufferAttribute(skinWeight, 4));
	}
	geo.setIndex(index);
	geo.computeVertexNormals();
	geo.userData.frames = frames;
	geo.userData.curve = curve;
	return geo;
}

// Gives a rigid geometry full weight on one bone so it can join a skinned mesh.
export function skinRigid(geo, bone) {
	const n = geo.attributes.position.count;
	const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
	for (let i = 0; i < n; i++) { si[i * 4] = bone; sw[i * 4] = 1; }
	geo.setAttribute('skinIndex', new THREE.BufferAttribute(si, 4));
	geo.setAttribute('skinWeight', new THREE.BufferAttribute(sw, 4));
	return geo;
}

// Inverse-distance skin weights against bone segments: [{ bone, a, b }].
export function skinBySegments(geo, segments, { power = 4, eps = 0.04 } = {}) {
	const pos = geo.attributes.position;
	const n = pos.count;
	const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
	const p = new THREE.Vector3(), line = new THREE.Line3(), q = new THREE.Vector3();
	const segs = segments.map((s) => ({ bone: s.bone, a: vec(s.a), b: vec(s.b) }));
	for (let i = 0; i < n; i++) {
		p.fromBufferAttribute(pos, i);
		const per = new Map();
		for (const s of segs) {
			line.set(s.a, s.b);
			line.closestPointToPoint(p, true, q);
			const w = 1 / Math.pow(q.distanceToSquared(p) + eps, power / 2);
			per.set(s.bone, Math.max(per.get(s.bone) || 0, w));
		}
		const top = [...per.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
		const total = top.reduce((s, e) => s + e[1], 0);
		top.forEach(([b, w], k) => { si[i * 4 + k] = b; sw[i * 4 + k] = w / total; });
	}
	geo.setAttribute('skinIndex', new THREE.BufferAttribute(si, 4));
	geo.setAttribute('skinWeight', new THREE.BufferAttribute(sw, 4));
	return geo;
}

// A ruled grid surface: P(u, v) = mix(A(u'), B(u'), v) + extra(u', v) where the
// trailing edge (u = 1) is scalloped inwards by `scallop`.
export function ruledPanel(A, B, { nu = 12, nv = 10, scallop = 0.15, extra, color } = {}) {
	const positions = [], colors = [], index = [];
	const p = new THREE.Vector3();
	for (let i = 0; i <= nu; i++) {
		const u = i / nu;
		for (let j = 0; j <= nv; j++) {
			const v = j / nv;
			const uu = u * (1 - scallop * Math.sin(Math.PI * v));
			p.copy(A(uu)).lerp(B(uu), v);
			if (extra) p.add(extra(uu, v));
			positions.push(p.x, p.y, p.z);
			const c = typeof color === 'function' ? color(uu, v) : tmpColor.set(color ?? 0xffffff);
			colors.push(c.r, c.g, c.b);
		}
	}
	for (let i = 0; i < nu; i++) {
		for (let j = 0; j < nv; j++) {
			const a = i * (nv + 1) + j, b = a + 1, c = a + nv + 1, d = c + 1;
			index.push(a, b, c, b, d, c);
		}
	}
	const geo = new THREE.BufferGeometry();
	geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
	geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
	geo.setIndex(index);
	geo.computeVertexNormals();
	return geo;
}

export function extrudeShape(shape, depth, color, bevel = 0.01) {
	const g = new THREE.ExtrudeGeometry(shape, {
		depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 2, curveSegments: 16,
	});
	return finish(g, color);
}
