# Drachenreiter – 3D-Modell

Ein roter Feuerdrache mit einem Link-artigen Reiter (grüne Tunika und Mütze, Elfenohren, Schwert links, Schild rechts), komplett prozedural mit three.js erzeugt und als **glTF 2.0 Binary** exportiert:

**`public/dragon-rider.glb`** (ca. 2,5 MB, 62k Dreiecke, 56 Knochen, keine Texturen, Farben als Vertex-Colors)

## Animationen

| Clip      | Dauer | Inhalt |
|-----------|-------|--------|
| `Idle`    | 4,0 s | Atmen, Kopf schaut sich um, Schwanz pendelt, Flügel halb angelegt, Link schaut umher |
| `Angriff` | 3,0 s | Aufbäumen, Link reißt das Schwert hoch, Vorstoß mit Feueratem (Schwenk links/rechts), Rückkehr |
| `Flug`    | 3,2 s | Zwei kräftige Flügelschläge, Beine angezogen, Körper hebt und senkt sich, Mütze flattert |

Alle Clips loopen nahtlos und enthalten Spuren für jeden animierten Knoten, damit beim Wechsel nichts in einer alten Pose hängen bleibt.
Das Feuer (`Fire`, `Fireball_0..7`) wird über Skalierung ein- und ausgeblendet und ist nur im `Angriff` sichtbar.
Im `Flug` hebt der `root`-Knoten das ganze Modell um ca. 5 m an.

## Aufbau

- **Drache**: ein Skelett (`root`, `hips`, `spine1-2`, `chest`, `neck1-5`, `head`, `jaw`, `tail1-10`, Beine, Flügel mit je 4 Fingern) mit zwei Skinned Meshes (Schuppenkörper, doppelseitige Flughäute). Hörner, Zähne, Krallen und Rückenstacheln hängen starr an ihren Knochen.
- **Reiter**: starre Teile an eigenen Knoten (`Link_Root`, `Link_Spine`, `Link_Head`, `Link_Hat2/3`, `Link_Shoulder_L/R`, `Link_Elbow_L/R`, `Link_Hand_L`), die am `chest`-Knochen des Drachen sitzen.
- Koordinaten nach glTF-Konvention: +Y oben, das Modell schaut nach +Z, Einheit Meter.

Das Modell funktioniert in jedem glTF-fähigen Programm, zum Beispiel Blender (*Import → glTF 2.0*), Unity (glTFast/UnityGLTF), Godot, Babylon.js oder three.js.
Der Khronos glTF Validator meldet 0 Fehler und 0 Warnungen.

## Neu bauen und ansehen

```sh
cd tools/dragon-rider
npm install
npm run build     # schreibt ../../public/dragon-rider.glb
npm run viewer    # schreibt dragon-rider-viewer.html (eigenständig, GLB eingebettet)
```

`dragon-rider-viewer.html` lässt sich direkt im Browser öffnen. Tasten `1` `2` `3` wechseln die Animation, `Leertaste` pausiert, `V` wechselt die Kamera.
`viewer.html` lädt alternativ die GLB-Datei über einen lokalen Webserver (z. B. `npx serve` im Repo-Root, dann `/tools/dragon-rider/viewer.html` öffnen).

| Datei | Zweck |
|-------|-------|
| `src/geometry.js` | Modellier-Werkzeuge: Lofts entlang von Kurven, Skinning-Gewichte, Flughaut-Paneele |
| `src/dragon.js` | Skelett, Drache, Kopf, Feuer, Sattel und Reiter |
| `src/animations.js` | Posen und die drei Clips (mit 30 fps gesampelt) |
| `build.js` | Export als `.glb` (GLTFExporter in Node) |
| `embed.js` | Erzeugt den eigenständigen Viewer mit eingebettetem Modell |

Hinweis: Link und Zelda sind Marken von Nintendo. Dies ist ein Fan-Modell für private, nicht kommerzielle Zwecke.
