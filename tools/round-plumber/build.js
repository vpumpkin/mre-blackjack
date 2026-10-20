// Builds the round plumber: rig + meshes + animation clips, written as
//   ../../public/round-plumber.glb   (textured, skinned, all clips)
//   exports/                          palette textures + clip/marker data (JSON + Luau)
//   node build.js [--no-anim]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { buildCharacter } from './src/character.js';
import { paletteImage } from './src/palette.js';
import { injectTextures } from './src/glb.js';

if (typeof globalThis.FileReader === 'undefined') {
	globalThis.FileReader = class {
		readAsArrayBuffer(blob) { blob.arrayBuffer().then((buf) => { this.result = buf; this.onloadend?.(); }); }
	};
}

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const out = path.resolve(args.find((a) => !a.startsWith('--')) || path.join(here, '../../public/round-plumber.glb'));
const exportsDir = path.join(here, 'exports');
fs.mkdirSync(exportsDir, { recursive: true });

const { scene, rig, meshes } = buildCharacter();
let animations = [], clipInfo = [];
if (!args.includes('--no-anim')) {
	const { buildAnimations } = await import('./src/animations.js');
	({ clips: animations, info: clipInfo } = buildAnimations(rig));
}
scene.userData.clips = clipInfo;

const textures = {
	color: paletteImage('color'), orm: paletteImage('orm'),
	roughness: paletteImage('roughness'), metalness: paletteImage('metalness'),
};
const raw = await new GLTFExporter().parseAsync(scene, { binary: true, animations });
const glb = injectTextures(raw, [
	{ name: 'PlumberPalette', png: textures.color },
	{ name: 'PlumberPaletteORM', png: textures.orm },
], (mat, tex) => {
	mat.pbrMetallicRoughness = {
		baseColorTexture: { index: tex.PlumberPalette },
		metallicRoughnessTexture: { index: tex.PlumberPaletteORM },
		metallicFactor: 1, roughnessFactor: 1,
	};
	if (mat.name === 'Plumber_Glow') {
		mat.pbrMetallicRoughness = { baseColorTexture: { index: tex.PlumberPalette }, metallicFactor: 0, roughnessFactor: 0.3 };
		mat.emissiveTexture = { index: tex.PlumberPalette };
		mat.emissiveFactor = [1, 1, 1];
		mat.extensions = { KHR_materials_emissive_strength: { emissiveStrength: 2.2 } };
	}
});
fs.writeFileSync(out, glb);
for (const [k, png] of Object.entries(textures)) if (k !== 'orm') fs.writeFileSync(path.join(exportsDir, `RoundPlumber_${k}.png`), png);

const tris = Object.values(meshes).map((m) => `${m.name} ${m.geometry.index.count / 3}`).join(', ');
console.log(`wrote ${path.relative(process.cwd(), out)} (${(glb.length / 1048576).toFixed(2)} MB) bones ${rig.bones.length}; ${tris}; clips ${animations.length}`);
if (clipInfo.length) {
	const { writeClipData } = await import('./src/clipdata.js');
	writeClipData(clipInfo, here);
}
