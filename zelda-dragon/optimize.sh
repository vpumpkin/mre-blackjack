#!/usr/bin/env bash
# Shrinks the raw Meshy GLB for the web: WebP textures at 2048px and quantized
# vertex data, both decodable by three.js GLTFLoader without extra decoders.
set -euo pipefail
cd "$(dirname "$0")"
npx --yes @gltf-transform/cli@4.1.1 optimize assets/dragon_raw.glb assets/dragon.glb \
  --compress quantize --texture-compress webp --texture-size 2048 \
  --simplify false --instance false --join false
ls -lh assets/dragon.glb
