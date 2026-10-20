# Runder Klempner – 3D-Charakter mit Animationen

Ein runder, eiförmiger Geisterjäger-Klempner (grüne Mütze mit Schraubenschlüssel-Emblem, Schnurrbart, Latzhose, große Handschuhe) mit Rucksack-Staubsauger, beweglichem Schlauch und Taschenlampe. Alles wird prozedural mit three.js erzeugt.

**Ansehen:** `index.html` im Browser öffnen. Das Modell ist eingebettet, three.js kommt vom CDN (Internet nötig). Links steht die Bühne, rechts der Index aller Animationen. Dazu gibt es eine Zeitleiste mit Gameplay-Markern, Varianten-Auswahl, Mimik-Overlays und Effekte (Sog, Taschenlampen-Blitz, Geist beim Slam, Staub, Kamerawackeln, Hit-Stop).

## Dateien

| Datei | Inhalt |
|-------|--------|
| `../../public/round-plumber.glb` | glTF 2.0: 6 Skinned Meshes (je unter 10.000 Dreiecken), 75 Bones, Paletten-Textur, 32 Clips |
| `exports/fbx/RoundPlumber_Rig.fbx` | Rig + Meshes + eingebettete Textur, ohne Animation |
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
npm run build                      # GLB + Clip-Daten + Texturen
npm run viewer                     # index.html
python3 blender/export_fbx.py      # FBX (braucht das bpy-Modul, z. B. pip install bpy unter Python 3.11)
python3 blender/verify_fbx.py      # vergleicht FBX und GLB Bone für Bone
```
