// Procedural-modelling toolkit (palette-textured variant of the one used for
// the dragon rider). Every geometry carries position / normal / uv, where the
// uv points at a palette swatch; skinned parts additionally carry skinIndex /
// skinWeight. Everything is authored in model space at the rest pose.
import * as THREE from 'three';
import { swatchUV } from './palette.js';

export const V = (x, y, z) => new THREE.Vector3(x, y, z);
export const vec = (a) => (a.isVector3 ? a.clone() : new THREE.Vector3(a[0], a[1], a[2]));
export const lerp = (a, b, t) => a + (b - a) * t;
export const clamp01 = (x) => Math.min(1, Math.max(0, x));
export const smooth = (x) => { x = clamp01(x); return x * x * (3 - 2 * x); };

export function makeRandom(seed) {
	return () => {
		seed = (seed + 0x6d2b79f5) | 0;
		let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

export function interp(arr, u) {
	if (arr.length === 1) return arr[0];
	const n = arr.length - 1;
	const s = clamp01(u) * n;
	const i = Math.min(Math.floor(s), n - 1);
	const f = s - i;
	const p0 = arr[Math.max(i - 1, 0)], p1 = arr[i], p2 = arr[i + 1], p3 = arr[Math.min(i + 2, n)];
	const cr = (a, b, c, d) => 0.5 * (2 * b + (-a + c) * f + (2 * a - 5 * b + 4 * c - d) * f * f + (-a + 3 * b - 3 * c + d) * f * f * f);
	if (Array.isArray(p1)) return p1.map((_, k) => cr(p0[k], p1[k], p2[k], p3[k]));
	return cr(p0, p1, p2, p3);
}

const KEEP = ['position', 'normal', 'uv', 'skinIndex', 'skinWeight'];

// Normalises a geometry for merging and assigns palette uvs.
// swatch: name | (position: Vector3, index) => name
export function finish(geo, swatch) {
	if (!geo.index) {
		const n = geo.attributes.position.count;
		geo.setIndex([...Array(n).keys()]);
	}
	for (const name of Object.keys(geo.attributes)) if (!KEEP.includes(name)) geo.deleteAttribute(name);
	geo.clearGroups();
	if (!geo.attributes.normal) geo.computeVertexNormals();
	if (swatch !== undefined) setSwatch(geo, swatch);
	return geo;
}

export function setSwatch(geo, swatch) {
	const pos = geo.attributes.position;
	const uv = new Float32Array(pos.count * 2);
	const p = new THREE.Vector3();
	for (let i = 0; i < pos.count; i++) {
		const name = typeof swatch === 'function' ? swatch(p.fromBufferAttribute(pos, i), i) : swatch;
		const [u, v] = swatchUV(name);
		uv[i * 2] = u; uv[i * 2 + 1] = v;
	}
	geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
	return geo;
}

export function transform(geo, { p = [0, 0, 0], r = [0, 0, 0], s = [1, 1, 1], order = 'XYZ', q } = {}) {
	const m = new THREE.Matrix4().compose(
		vec(p),
		q || new THREE.Quaternion().setFromEuler(new THREE.Euler(r[0], r[1], r[2], order)),
		Array.isArray(s) ? vec(s) : V(s, s, s),
	);
	return geo.applyMatrix4(m);
}

export function ellipsoid(c, r, swatch, { w = 18, h = 12, rot = [0, 0, 0], q } = {}) {
	const g = new THREE.SphereGeometry(1, w, h);
	transform(g, { p: c, r: rot, s: r, q });
	return finish(g, swatch);
}

// Unit-height +Y geometry stretched to span a -> b.
function alongY(g, a, b) {
	a = vec(a); b = vec(b);
	const d = b.clone().sub(a);
	g.scale(1, d.length(), 1);
	g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(V(0, 1, 0), d.normalize()));
	g.translate(a.x, a.y, a.z);
	return g;
}

export function cone(a, b, r, swatch, { seg = 10, sx = 1, sz = 1 } = {}) {
	const g = new THREE.ConeGeometry(r, 1, seg, 1);
	g.translate(0, 0.5, 0);
	g.scale(sx, 1, sz);
	return finish(alongY(g, a, b), swatch);
}

export function cylinder(a, b, r0, r1, swatch, seg = 14, open = false) {
	const g = new THREE.CylinderGeometry(r1, r0, 1, seg, 1, open);
	g.translate(0, 0.5, 0);
	return finish(alongY(g, a, b), swatch);
}

export function torus(c, R, r, axis, swatch, { seg = 28, tube = 8, arc = Math.PI * 2 } = {}) {
	const g = new THREE.TorusGeometry(R, r, tube, seg, arc);
	g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(V(0, 0, 1), vec(axis).normalize()));
	g.translate(...vec(c).toArray());
	return finish(g, swatch);
}

// Sphere cap around +Y (thetaLength measured from the pole), oriented by q.
export function sphereCap(c, r, thetaLength, swatch, { q, w = 22, h = 8, bottom = false } = {}) {
	const g = new THREE.SphereGeometry(r, w, h, 0, Math.PI * 2, bottom ? Math.PI - thetaLength : 0, thetaLength);
	if (q) g.applyQuaternion(q);
	g.translate(...vec(c).toArray());
	return finish(g, swatch);
}

export function extrudeShape(shape, depth, swatch, bevel = 0.004, curveSegments = 12) {
	const g = new THREE.ExtrudeGeometry(shape, {
		depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 2, curveSegments,
	});
	return finish(g, swatch);
}

// Lofts a (super)elliptical cross-section along a Catmull-Rom curve.
// opts: radii [[rx,ry]...] | (u)=>[rx,ry]; owners (bone per segment) -> skinned;
// swatch name | (u, theta, dir, ring) => name; up hint; square exponent.
export function loft(points, opts = {}) {
	const pts = points.map(vec);
	const n = pts.length - 1;
	const curve = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', opts.tension ?? 0.5);
	const perSeg = opts.perSeg ?? 6;
	const rings = n * perSeg;
	const radial = opts.radial ?? 12;
	const square = opts.square ?? 2;
	const radiusAt = typeof opts.radii === 'function' ? opts.radii : (u) => interp(opts.radii, u);
	const positions = [], uvs = [], skinIndex = [], skinWeight = [], index = [], frames = [];
	let prevN = null;
	const up0 = vec(opts.up ?? [0, 1, 0]);
	const p = new THREE.Vector3(), dir = new THREE.Vector3();

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
		add(opts.owners[j], 1 - wp - wn); add(prev, wp); add(next, wn);
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
	const swatchAt = (u, th, d, ring) => {
		const s = opts.swatch ?? 'steel';
		return typeof s === 'function' ? s(u, th, d, ring) : s;
	};

	for (let i = 0; i <= rings; i++) {
		const u = i / rings;
		const c = curve.getPoint(u);
		const t = curve.getTangent(u).normalize();
		const base = prevN || up0;
		const nrm = base.clone().sub(t.clone().multiplyScalar(base.dot(t))).normalize();
		prevN = nrm;
		const side = new THREE.Vector3().crossVectors(t, nrm).normalize();
		const [rx, ry] = radiusAt(u).map((r) => Math.max(r, 0.0015));
		frames.push({ u, c: c.clone(), t: t.clone(), n: nrm.clone(), side: side.clone(), rx, ry });
		const wts = weightsAt(u);
		for (let j = 0; j < radial; j++) {
			const th = (j / radial) * Math.PI * 2;
			const cs = Math.cos(th), sn = Math.sin(th);
			const x = Math.sign(cs) * Math.pow(Math.abs(cs), 2 / square);
			const y = Math.sign(sn) * Math.pow(Math.abs(sn), 2 / square);
			const k = opts.noise ? opts.noise(u, th) : 1;
			dir.copy(side).multiplyScalar(cs).addScaledVector(nrm, sn).normalize();
			p.copy(c).addScaledVector(side, x * rx * k).addScaledVector(nrm, y * ry * k);
			positions.push(p.x, p.y, p.z);
			uvs.push(...swatchUV(swatchAt(u, th, dir, i)));
			pushSkin(wts);
		}
	}
	for (let i = 0; i < rings; i++) {
		for (let j = 0; j < radial; j++) {
			const a = i * radial + j, b = i * radial + ((j + 1) % radial);
			const c = (i + 1) * radial + j, d = (i + 1) * radial + ((j + 1) % radial);
			index.push(a, c, b, b, c, d);
		}
	}
	const addCap = (ring, u, atStart) => {
		const ci = positions.length / 3;
		const c = frames[ring].c;
		positions.push(c.x, c.y, c.z);
		uvs.push(...swatchUV(swatchAt(u, -Math.PI / 2, frames[ring].t, ring)));
		pushSkin(weightsAt(u));
		for (let j = 0; j < radial; j++) {
			const a = ring * radial + j, b = ring * radial + ((j + 1) % radial);
			if (atStart) index.push(ci, a, b); else index.push(ci, b, a);
		}
	};
	if (opts.capStart !== false) addCap(0, 0, true);
	if (opts.capEnd !== false) addCap(rings, 1, false);

	const geo = new THREE.BufferGeometry();
	geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
	geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
	if (opts.owners) {
		geo.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(skinIndex, 4));
		geo.setAttribute('skinWeight', new THREE.Float32BufferAttribute(skinWeight, 4));
	}
	geo.setIndex(index);
	geo.computeVertexNormals();
	geo.userData.frames = frames;
	return geo;
}

// Grid surface from a parametric function f(u, v) -> { p, n? }; offset pushes
// along the normal. swatch: name | (u, v, p) => name.
export function patch(f, { nu = 16, nv = 16, offset = 0, swatch = 'steel', wrapV = false, flip = false } = {}) {
	const positions = [], uvs = [], normals = [], index = [];
	const cols = wrapV ? nv : nv + 1;
	const eps = 1e-3;
	for (let i = 0; i <= nu; i++) {
		const u = i / nu;
		for (let j = 0; j < cols; j++) {
			const v = j / nv;
			const s = f(u, v);
			let n = s.n;
			if (!n) {
				const pu = f(Math.min(1, u + eps), v).p.clone().sub(f(Math.max(0, u - eps), v).p);
				const pv = f(u, Math.min(1, v + eps)).p.clone().sub(f(u, Math.max(0, v - eps)).p);
				n = new THREE.Vector3().crossVectors(pu, pv).normalize();
				if (flip) n.negate();
			}
			const p = s.p.clone().addScaledVector(n, offset);
			positions.push(p.x, p.y, p.z);
			normals.push(n.x, n.y, n.z);
			uvs.push(...swatchUV(typeof swatch === 'function' ? swatch(u, v, p) : swatch));
		}
	}
	for (let i = 0; i < nu; i++) {
		for (let j = 0; j < nv; j++) {
			const a = i * cols + j, b = i * cols + ((j + 1) % cols);
			const c = (i + 1) * cols + j, d = (i + 1) * cols + ((j + 1) % cols);
			// (a, c, b) winds along du x dv, which is the computed normal
			if (flip) index.push(a, b, c, b, d, c); else index.push(a, c, b, b, c, d);
		}
	}
	const geo = new THREE.BufferGeometry();
	geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
	geo.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
	geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
	geo.setIndex(index);
	return geo;
}

// --- skinning helpers -------------------------------------------------------
export function skinRigid(geo, bone) {
	const n = geo.attributes.position.count;
	const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
	for (let i = 0; i < n; i++) { si[i * 4] = bone; sw[i * 4] = 1; }
	geo.setAttribute('skinIndex', new THREE.BufferAttribute(si, 4));
	geo.setAttribute('skinWeight', new THREE.BufferAttribute(sw, 4));
	return geo;
}

// weightFn(p, n) -> [[bone, weight], ...] (normalised and trimmed to 4 here)
export function skinBy(geo, weightFn) {
	const pos = geo.attributes.position, nor = geo.attributes.normal;
	const n = pos.count;
	const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
	const p = new THREE.Vector3(), q = new THREE.Vector3();
	for (let i = 0; i < n; i++) {
		p.fromBufferAttribute(pos, i);
		q.fromBufferAttribute(nor, i);
		const merged = new Map();
		for (const [b, w] of weightFn(p, q)) if (w > 1e-4) merged.set(b, (merged.get(b) || 0) + w);
		const top = [...merged.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
		const total = top.reduce((s, e) => s + e[1], 0) || 1;
		top.forEach(([b, w], k) => { si[i * 4 + k] = b; sw[i * 4 + k] = w / total; });
	}
	geo.setAttribute('skinIndex', new THREE.BufferAttribute(si, 4));
	geo.setAttribute('skinWeight', new THREE.BufferAttribute(sw, 4));
	return geo;
}
