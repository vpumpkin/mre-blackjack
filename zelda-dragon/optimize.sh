#!/usr/bin/env bash
# Shrinks the raw Meshy GLB for the web: WebP textures at 2048px and quantized
# vertex data, both decodable by three.js GLTFLoader without extra decoders.
set -euo pipefail
cd "$(dirname "$0")"
npx --yes @gltf-transform/cli@4.1.1 optimize assets/dragon_raw.glb assets/dragon.glb \
  --compress quantize --texture-compress webp --texture-size 2048 \
  --simplify false --instance false --join false
ls -lh assets/dragon.glb
# same bytes as a JSON data file, for hosts that only serve web data types
python3 -c "import base64, json; json.dump({'format': 'glb-base64', 'glb': base64.b64encode(open('assets/dragon.glb', 'rb').read()).decode()}, open('assets/dragon.json', 'w'))"
ls -lh assets/dragon.json
