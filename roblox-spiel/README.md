# Roblox-Spiel: Material für den Creator Hub

Spielsymbol und Beschreibungen für dein Formen-Spiel (Formen-Clash / Geometrie Battle).

## Spielsymbol

- `spielsymbol/spielsymbol_512.png`: zum Hochladen als Spielsymbol (512 × 512)
- `spielsymbol/spielsymbol_1024.png`: hohe Auflösung, z. B. für Discord oder Werbung
- `spielsymbol/vergleich_alt_neu.png`: neues Symbol neben dem alten, groß und in Handygröße
- `spielsymbol/konzepte/`: die vier Entwürfe (Komet, Held, Schuss, Treffer)
- `spielsymbol/quelle/`: Blender-Szene und Nachbearbeitung zum Neu-Rendern

Das Symbol zeigt den Fusions-Komet aus Kugel und Würfel, der in ein Kreuz kracht; ein Tetraeder flieht. Kein Text und keine geschützten Figuren.

### Neu rendern

Braucht Python 3.13 mit `bpy==5.2.3` (Blender als Python-Modul) in einer eigenen Umgebung sowie Pillow und NumPy im System-Python. Unter Linux ohne Grafikkarte zusätzlich das Paket `libegl1`.

    python3 -m venv bpyenv
    bpyenv/bin/pip install bpy==5.2.3
    BPY="$PWD/bpyenv/bin/python" roblox-spiel/spielsymbol/quelle/build.sh

## Beschreibung

- `creator-hub/beschreibung_de.txt`: deutsche Beschreibung (940 Zeichen)
- `creator-hub/beschreibung_en.txt`: englische Fassung (901 Zeichen), im Creator Hub unter Lokalisierung → Übersetzen → Informationen

Optionale Zeilen:

- Halloween, ganz oben bis zum Ende des Events: `🎃 HALLOWEEN-EVENT LÄUFT – nur für kurze Zeit!` bzw. `🎃 HALLOWEEN EVENT NOW LIVE – limited time only!`
- Sprachhinweis für die englische Fassung: `🌐 In-game text is in German`
