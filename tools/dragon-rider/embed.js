// Writes a self-contained copy of viewer.html with the .glb inlined as base64,
// so it opens straight from disk (no local web server needed).
//   node embed.js [out.html] [--fragment]
// --fragment drops the <html>/<head>/<body> wrapper (for hosts that add their own).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const fragment = args.includes('--fragment');
const out = path.resolve(args.find((a) => !a.startsWith('--')) || path.join(here, 'dragon-rider-viewer.html'));
const glb = fs.readFileSync(path.join(here, '../../public/dragon-rider.glb'));

let html = fs.readFileSync(path.join(here, 'viewer.html'), 'utf8')
	.replace('<!--GLB-->', `<script type="application/octet-stream" id="glb-data">${glb.toString('base64')}</script>`);
if (fragment) {
	const wrapper = /^(<!doctype html>|<html[^>]*>|<\/?head>|<\/?body>|<\/html>|<meta charset[^>]*>|<meta name="viewport"[^>]*>)\s*$/i;
	html = html.split('\n').filter((line) => !wrapper.test(line.trim())).join('\n');
}
fs.writeFileSync(out, html);
console.log(`wrote ${path.relative(process.cwd(), out)} (${(html.length / 1048576).toFixed(1)} MB)`);
