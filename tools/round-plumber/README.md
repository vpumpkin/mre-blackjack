# Runder Klempner – 3D-Charakter mit Animationen

Ein runder Geisterjäger-Klempner (grüne Mütze, Schnurrbart, Latzhose, große Handschuhe) mit Rucksack-Staubsauger, beweglichem Schlauch und Taschenlampe.

Es gibt ihn in zwei Fassungen mit demselben Rig und denselben 32 Clips:

- **Meshy-Hybrid** (`../../public/round-plumber-meshy.glb`, Standard im Viewer): Kopf, Gesicht, Mütze mit „L“, Schnurrbart, Ohren und Kugelkörper stammen aus dem Meshy-Modell (`meshy/Meshy_AI_Luigi_1021080809_texture_obj.zip`). Dessen kurze Ärmchen liegen fest auf dem Bauch und reichen nicht für Staubsauger, Taschenlampe und Uppercut. Deshalb werden sie flach auf die Kugel gedrückt und mit Hemd und Latzhose übermalt. Arme mit Fingern, Schuhe, bewegliche Augen, Lider, Brauen, Mund und die Ausrüstung kommen aus dem prozeduralen Modell. Die aufgemalten Augen und Brauen sind mit Haut übermalt.
- **Prozedural** (`../../public/round-plumber.glb`): alles mit three.js erzeugt, Roblox-tauglich (je Mesh unter 10.000 Dreiecken).

**Ansehen:** `index.html` im Browser öffnen. Das Modell ist eingebettet, three.js kommt vom CDN (Internet nötig). Links steht die Bühne, rechts der Index aller Animationen. Dazu gibt es eine Zeitleiste mit Gameplay-Markern, Varianten-Auswahl, Mimik-Overlays und Effekte (Sog, Taschenlampen-Blitz, Geist beim Slam, Staub, Kamerawackeln, Hit-Stop).

## Dateien

| Datei | Inhalt |
|-------|--------|
| `../../public/round-plumber-meshy.glb` | Meshy-Hybrid: Meshy-Körper (70.000 Dreiecke, 2048er-Textur) + prozedurale Arme, Schuhe, Gesichtsteile und Ausrüstung, 75 Bones, 32 Clips |
| `../../public/round-plumber.glb` | prozedural: 7 Skinned Meshes (je unter 10.000 Dreiecken), 75 Bones, Paletten-Textur, 32 Clips |
| `meshy/*.zip` | Meshy-Export (OBJ + Textur), Quelle für den Hybrid |
| `exports/fbx/RoundPlumber_Rig.fbx` | prozedurales Rig + Meshes + eingebettete Textur, ohne Animation |
| `exports/fbx/anim/*.fbx` | eine FBX pro Clip (nur Armature), z. B. für den Roblox-Animationseditor |
| `exports/clips.json`, `exports/RoundPlumberClips.luau` | Dauer, Priorität, Marker-Zeiten und Root Motion je Clip |
| `exports/RoundPlumber_*.png` | Farb-, Roughness- und Metalness-Map (512 × 512) |

## Animationen (32)

- **Idle:** ängstliches Zittern, nervöses Umschauen, Mut sammeln, Combat Idle, Laufen
- **Staubsauger:** Ziehen A/B/C, Saugen A/B (Loops), Wegstecken
- **Angriffe:** Aufwärtshieb, Taschenlampen-Blendangriff A/B/C
- **Ultimate:** Einsaugen + zweimal auf den Boden schlagen A/B
- **Ausweichen:** links, rechts, zurück, jeweils als Sprung (A) und Rolle (B)
- **Mimik-Overlays (nur Gesichts-Bones):** neutral, ängstlich, erschrocken, panisch, konzentriert, wütend, erleichtert, stolz, verwirrt

Alle Varianten einer Gruppe haben dieselbe Dauer und dieselben Gameplay-Marker-Zeiten (`HitboxStart`, `Impact`, `Flash`, `Grab`, `Slam01`, `Slam02`, `Release`, `IFrameStart` …). Der Build prüft das. Squash & Stretch und Pupillengröße laufen nur über Bone-Verschiebungen, nicht über Skalierung.

## Neu bauen

```sh
npm install
npm run build                      # prozedurales GLB + Clip-Daten + Texturen
python3 blender/integrate_meshy.py # Meshy-Hybrid (braucht bpy + pillow, z. B. pip install bpy pillow unter Python 3.11)
npm run viewer                     # index.html (Hybrid; node embed.js --glb ../../public/round-plumber.glb für die prozedurale Fassung)
python3 blender/export_fbx.py      # FBX der prozeduralen Fassung
python3 blender/verify_fbx.py      # vergleicht FBX und GLB Bone für Bone
```

`integrate_meshy.py` richtet das Meshy-Modell an Körper und Kopf des Rigs aus (Bounding Box + ICP). Dann drückt es die Ärmchen auf ein angepasstes Ellipsoid und übermalt sie. Die Grenze zwischen Hemd und Latzhose wird dabei rund um den Körper weitergeführt. Danach übermalt es die aufgemalten Augen und Brauen und überträgt die Skin-Gewichte von der prozeduralen Oberfläche. Pro Vertex gilt dabei die nächste Fläche, die in dieselbe Richtung zeigt, anschließend wird geglättet. Zum Schluss setzt es Augen, Brauen und Mund auf das neue Gesicht. Die Clips werden unverändert aus dem prozeduralen GLB übernommen. Der Hybrid hat 70.000 Dreiecke in einem Mesh und ist damit für den Browser gedacht; für Roblox müsste er erst reduziert werden.
