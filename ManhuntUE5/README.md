# MANHUNT: OPEN WORLD (3 vs. 8) – UE5-Plugin `ManhuntCore`

C++-Grundgerüst für das asymmetrische Multiplayer-Stealth-Spiel aus dem Master-Prompt
(Schritt 1–3: Klassenarchitektur, die 3 Hunter-Klassen, der Pfand-Kreislauf), dazu Matchflow,
Fahrzeuge, Türen und Anti-Cheat. Alles ist **asset-agnostisch**: Fab-Meshes, Sounds und
Animationen kommen in Blueprint-Childs. Die Spiellogik musst du dafür nicht anfassen.

> **Status:** Der Code wurde in einer Cloud-Umgebung ohne Unreal Engine geschrieben und dort
> **nicht kompiliert und nicht getestet**. Ziel: UE 5.4/5.5. Der erste Build kann noch kleine
> Compile-Fehler bringen. Schick mir dann einfach die Fehlermeldung.

---

## 1. Installation

1. Den Ordner `Plugins/ManhuntCore` in dein Projekt kopieren: `<DeinProjekt>/Plugins/ManhuntCore`.
2. **Reines Blueprint-Projekt?** Einmal *Tools → New C++ Class → None → Create* ausführen,
   damit das Projekt C++ kompilieren kann (Visual Studio 2022 mit „Game development with C++“).
3. Rechtsklick auf die `.uproject` → *Generate Visual Studio project files* → im Editor bauen
   (oder beim Öffnen „Rebuild“ bestätigen).
4. *Edit → Plugins*: prüfen, ob **Manhunt Core** aktiv ist.

## 2. Projekt-Einstellungen

| Einstellung | Wert |
|---|---|
| Project Settings → Maps & Modes → Default GameMode | `ManhuntGameMode` (oder dein `BP_ManhuntGameMode`) |
| Project Settings → Input → Default Player Input Class | `EnhancedPlayerInput` |
| Project Settings → Input → Default Input Component Class | `EnhancedInputComponent` |
| World Settings der Map → GameMode Override | `BP_ManhuntGameMode` |

**Untergründe für E-Scooter/Fahrrad** (*Project Settings → Physics → Physical Surface*) oder in
`Config/DefaultEngine.ini`:

```ini
[/Script/Engine.PhysicsSettings]
+PhysicalSurfaces=(Type=SurfaceType1,Name="Asphalt")
+PhysicalSurfaces=(Type=SurfaceType2,Name="Kopfsteinpflaster")
+PhysicalSurfaces=(Type=SurfaceType3,Name="Waldboden")
+PhysicalSurfaces=(Type=SurfaceType4,Name="Schotter")
+PhysicalSurfaces=(Type=SurfaceType5,Name="Treppe")
+PhysicalSurfaces=(Type=SurfaceType6,Name="Gras")
```

Danach für jede Sorte ein Physical Material anlegen (z. B. `PM_Asphalt` mit Surface Type
*Asphalt*) und in den Materialien der Fab-Straßen, -Treppen und -Waldböden eintragen.
Ohne Physical Material fahren Fahrzeuge überall mit vollem Tempo.

## 3. Sofort testen (ohne eigene Assets)

1. Leere Map oder Testmap, ein paar `PlayerStart` mit **Player Start Tag** `Runner` bzw. `Hunter`.
2. *Play → Number of Players: 2*, *Net Mode: Play As Listen Server*.
3. Spieler 1 wird **Runner**, Spieler 2 **Hunter**. Danach läuft die Klassenwahl (20 s).
4. Ohne eigene Charaktere wird automatisch das UE5-Template-Mannequin geladen, falls es im
   Projekt liegt. Sonst siehst du nur eine unsichtbare Kapsel.

| Taste | Funktion |
|---|---|
| WASD / Maus / Shift / Leertaste | Laufen, Umsehen, Sprinten (Stamina), Springen |
| **E** | Interagieren (Tür, Mülleimer, Pfandautomat, Kasse, Scooter, Absteigen) |
| **Q** | Fähigkeit: Hacker = Kameras, Fährtenleser = Spuren lesen, Runner = Tür verriegeln |
| Linke Maustaste | Tackle (Hunter, nicht auf Fahrzeugen) |
| Leertaste/E/LMB hämmern | Losreißen, wenn du gepackt wurdest |
| Mausrad | Kamera wechseln (Hacker) |
| 1 / 2 / 3 | Vor dem Start: Hunter-Klasse. Im Spiel: Energy-Drink / Ping-Blocker / Fake-Ping |
| J / H | Speedhunt-Ziel wählen / starten (Taskforce-Leader) |
| Tab | Taktik-Tablet groß |

Konsole (`^`): `MH_Class 1`, `MH_Give 0 10` (10 Pfandflaschen), `MH_Give 4 500` (5,00 €).
Im GameMode-Blueprint `MinPlayersToStart`, `MatchDurationSeconds` usw. zum Testen verkürzen.

## 4. Architektur

```
AManhuntGameMode        Teams (3 Runner / 8 Hunter), Klassenwahl, 600-s-Matchflow:
                        Silent Hunt alle 60 s, Speedhunt 2x (Ping alle 10 s für 60 s),
                        Blitz-Drops 3:00 & 6:30, Finale 9:00 (Pings alle 15 s, 1 Extraktion pro Biom)
AManhuntGameState       Phase, Zeit, Tag-Nacht-Stunde, Speedhunt-Alarm,
                        Tür-/Fensterstatus als FFastArraySerializer (nur abweichende Türen = 0 Byte im Normalfall)
AManhuntPlayerState     Team, Klasse, Leader, Runner-Status, Geld in Cent, Pfandbon, Flaschen, Joker
AManhuntPlayerController Enhanced Input (zur Laufzeit erzeugt), Pings (Client-RPC nur an Hunter), HUD-Nachrichten
AManhuntCharacter       Stamina, Sprint (vorhergesagt), serverseitige Interaktion, Tackle & Struggle,
                        Fußspuren, Anti-Cheat-Relevanz (IsNetRelevantFor)
UManhuntCharacterMovement  Sprint per CompressedFlags, Fahrzeug-Tempo je Physical Surface
IManhuntInteractable    = BPI_Interactable    (Tür, Fundort, Automat, Kasse, Fahrzeug)
IManhuntMountableVehicle = BPI_MountableVehicle (E-Scooter, Fahrrad)
```

**Hunter-Klassen**

* **Hacker**: `UManhuntHackerComponent` + `AManhuntCCTVCamera`. Der Server setzt das ViewTarget
  und sperrt die Bewegung. Die Kameras sind in World Partition immer geladen; beim Zuschauen
  streamt eine Streaming-Source die Umgebung nach. 70 Stamina, schlechter Sprinter.
* **Kampfsportler**: 160 Stamina, Griffstärke 2,5 (Losreißen massiv schwerer), Sofort-Catch bei
  unter 25 % Runner-Stamina.
* **Fährtenleser**: `UManhuntTrackerComponent` + `UManhuntTrackingSubsystem`. Der Server speichert
  alle Runner-Schritte und Reifenspuren. Nur bei aktiver Fähigkeit (12 s, 45 s Cooldown) bekommt
  der Fährtenleser die Spuren im Umkreis von 45 m, mit Opazität und Farbe nach Alter. Beim Lesen:
  halbes Tempo, kein Sprint.

**Pfand-Kreislauf:** `AManhuntLootSpot` (Mülleimer → Flaschen à 0,25 €; auch Schnorren mit
`FindChance 0.2` und `LootItem Cash 20–50`) → `AManhuntPfandMachine` (Flaschen einzeln, 1,6 s pro
Stück, piept, druckt Pfandbon) → `AManhuntCheckout` (echte Schlange mit NPC-Kunden, automatisches
Aufrücken, Kassierer zahlt den Bon aus; Social Stealth).

**Anti-Cheat:** Hunter-Clients bekommen Runner nur repliziert bei Sichtlinie, über die aktive
Hacker-Kamera oder in Hörweite. Die Hörweite wächst mit jeder Pfandflasche im Rucksack.
Pings sind statische 2D-Snapshots ohne Stockwerk. Interaktionen traced der Server selbst.

## 5. Fab-Assets einbinden

| Fab-Asset | Blueprint-Child von | Was du setzt |
|---|---|---|
| Runner-/Hunter-Charakter | `ManhuntCharacter` → `BP_Runner`, `BP_Hunter` | Mesh, Anim Blueprint; im GameMode `RunnerPawnClass`/`HunterPawnClass` |
| Tür / Fenster (auch in Packed Level Actors) | `ManhuntDoor` | `DoorLeaf`-Mesh, Pivot am Scharnier, `bIsWindow` |
| Gebäude (Mall, Haus, Scheune) | `ManhuntBuildingVolume` | Box um das Gebäude, `BuildingName` |
| Überwachungskamera | `ManhuntCCTVCamera` | `Mesh`, `DisplayName`, Blickrichtung der `Camera` |
| E-Scooter / Fahrrad | `ManhuntEScooter` / `ManhuntBike` | `VehicleMesh` (Pivot unten), `MountOffset`; optional `ManhuntVehicleData` |
| Mülleimer / Flasche / Drop-Kiste | `ManhuntLootSpot` | `Mesh`, `LootItem`, Mengen, Chance, Suchdauer |
| Pfandautomat | `ManhuntPfandMachine` | `Mesh`; Piep-/Ratter-Sound in `OnBottleAccepted` |
| Supermarktkasse | `ManhuntCheckout` | `CounterMesh`, Pfeil `QueueStart` vor den Kassierer, NPC-Klassen |
| Helipad / Flucht-Van / Motorboot | `ManhuntExtractionPoint` | `Mesh`, `Biome`, `DisplayName` |
| Fußabdruck-Textur | Decal-Material | Domain *Deferred Decal*, Parameter `Opacity` + `Color` → in `BP_Hunter` › Tracker |

Blitz-Drops: `TargetPoint`s in der Center Zone mit Tag `BlitzDrop` platzieren und im GameMode
`BlitzDropClass` auf ein `ManhuntLootSpot`-Child setzen (Ping-Blocker/Fake-Ping, `bDestroyWhenLooted`).

## 6. Noch offen (nächste Module)

Casino & Spielautomaten mit Jackpot-Alarm · Läden (Energy-Drink, Kleidung, Schwarzmarkt) ·
Parkour/Vault durch Fenster und über Zäune (der Runner-Bonus von 15 % liegt schon in den Stats) ·
MassAI-Passanten · UMG-Widgets statt Debug-HUD · Zonen-Grenzen per Data Layer im Finale ·
PCG-Biome und die 1,5-km-World-Partition-Map.
