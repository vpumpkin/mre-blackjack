// Minimal GLB surgery: append PNG images to the binary chunk and wire them up
// as textures on materials (three's GLTFExporter needs a canvas for images,
// which Node does not have).
export function injectTextures(glb, images, patchMaterials) {
	const dv = new DataView(glb);
	const jsonLen = dv.getUint32(12, true);
	const json = JSON.parse(new TextDecoder().decode(new Uint8Array(glb, 20, jsonLen)));
	const binLen = dv.getUint32(20 + jsonLen, true);
	let bin = Buffer.from(new Uint8Array(glb, 28 + jsonLen, binLen));

	json.bufferViews ??= [];
	json.images ??= [];
	json.textures ??= [];
	json.samplers ??= [];
	json.samplers.push({ magFilter: 9729, minFilter: 9729, wrapS: 33071, wrapT: 33071 });
	const sampler = json.samplers.length - 1;
	const textureIndex = {};
	for (const img of images) {
		const pad = (4 - (bin.length % 4)) % 4;
		bin = Buffer.concat([bin, Buffer.alloc(pad)]);
		json.bufferViews.push({ buffer: 0, byteOffset: bin.length, byteLength: img.png.length });
		bin = Buffer.concat([bin, img.png]);
		json.images.push({ name: img.name, mimeType: 'image/png', bufferView: json.bufferViews.length - 1 });
		json.textures.push({ sampler, source: json.images.length - 1 });
		textureIndex[img.name] = json.textures.length - 1;
	}
	bin = Buffer.concat([bin, Buffer.alloc((4 - (bin.length % 4)) % 4)]);
	json.buffers[0].byteLength = bin.length;
	for (const mat of json.materials || []) patchMaterials(mat, textureIndex, json);

	let jsonBuf = Buffer.from(JSON.stringify(json));
	jsonBuf = Buffer.concat([jsonBuf, Buffer.alloc((4 - (jsonBuf.length % 4)) % 4, 0x20)]);
	const header = Buffer.alloc(12);
	header.writeUInt32LE(0x46546c67, 0);
	header.writeUInt32LE(2, 4);
	header.writeUInt32LE(12 + 8 + jsonBuf.length + 8 + bin.length, 8);
	const chunk = (buf, type) => { const h = Buffer.alloc(8); h.writeUInt32LE(buf.length, 0); h.writeUInt32LE(type, 4); return Buffer.concat([h, buf]); };
	return Buffer.concat([header, chunk(jsonBuf, 0x4e4f534a), chunk(bin, 0x004e4942)]);
}
