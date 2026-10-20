// Builds the dragon rider model and writes it as a binary glTF (.glb).
//   node build.js [output.glb]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { buildDragonRider } from './src/dragon.js';

// GLTFExporter relies on the browser FileReader to assemble the binary chunk.
if (typeof globalThis.FileReader === 'undefined') {
	globalThis.FileReader = class {
		readAsArrayBuffer(blob) {
			blob.arrayBuffer().then((buf) => { this.result = buf; this.onloadend?.(); });
		}

		readAsDataURL(blob) {
			blob.arrayBuffer().then((buf) => {
				this.result = `data:${blob.type || 'application/octet-stream'};base64,${Buffer.from(buf).toString('base64')}`;
				this.onloadend?.();
			});
		}
	};
}

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, '../../public/dragon-rider.glb'));

const { scene, animations } = buildDragonRider();
const glb = await new GLTFExporter().parseAsync(scene, { binary: true, animations });
fs.writeFileSync(out, Buffer.from(glb));

let tris = 0;
scene.traverse((o) => { if (o.isMesh) tris += o.geometry.index.count / 3; });
console.log(`wrote ${path.relative(process.cwd(), out)} (${(glb.byteLength / 1024).toFixed(0)} KiB, ${tris} triangles, ` +
	`clips: ${animations.map((a) => `${a.name} ${a.duration}s`).join(', ')})`);
