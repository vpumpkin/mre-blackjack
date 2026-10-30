#!/usr/bin/env bash
# Rendert das Spielsymbol neu:
#   faces.py -> tex/ (Gesichter), scene.py -> render_1024.png (Blender/Cycles),
#   post.py -> icon_1024.png (Hintergrund, Plasma, Effekte), dann ../spielsymbol_1024.png und ../spielsymbol_512.png
set -euo pipefail
cd "$(dirname "$0")"
BPY="${BPY:?BPY auf den Python-Interpreter mit bpy 5.2.3 setzen}"
SIZE="${SIZE:-1024}"
SAMPLES="${SAMPLES:-200}"
python3 -I faces.py tex
"$BPY" scene.py render_1024.png "$SIZE" "$SAMPLES"
python3 -I post.py render_1024.png icon_1024.png
cp icon_1024.png ../spielsymbol_1024.png
python3 -I -c "from PIL import Image; Image.open('icon_1024.png').convert('RGB').resize((512, 512), Image.LANCZOS).save('../spielsymbol_512.png')"
echo "fertig: spielsymbol_1024.png und spielsymbol_512.png"
