// Writes index.html: viewer.html with the .glb inlined as base64, so the page
// opens straight from disk (three.js still loads from the jsDelivr CDN).
//   node embed.js [out.html] [--fragment] [--glb file.glb]
// --fragment drops the <html>/<head>/<body> wrapper (for hosts that add their own).
// --glb picks the model (default: the Meshy hybrid, public/round-plumber-meshy.glb;
// public/round-plumber.glb is the fully procedural one).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const fragment = args.includes('--fragment');
const glbAt = args.indexOf('--glb');
const glbPath = glbAt >= 0 ? path.resolve(args.splice(glbAt, 2)[1]) : path.join(here, '../../public/round-plumber-meshy.glb');
const out = path.resolve(args.find((a) => !a.startsWith('--')) || path.join(here, 'index.html'));
const glb = fs.readFileSync(glbPath);

let html = fs.readFileSync(path.join(here, 'viewer.html'), 'utf8')
	.replace('<!--GLB-->', `<script type="application/octet-stream" id="glb-data">${glb.toString('base64')}</script>`);
if (fragment) {
	const wrapper = /^(<!doctype html>|<html[^>]*>|<\/?head>|<\/?body>|<\/html>|<meta charset[^>]*>|<meta name="viewport"[^>]*>)\s*$/i;
	html = html.split('\n').filter((line) => !wrapper.test(line.trim())).join('\n');
}
fs.writeFileSync(out, html);
console.log(`wrote ${path.relative(process.cwd(), out)} (${(html.length / 1048576).toFixed(1)} MB)`);
