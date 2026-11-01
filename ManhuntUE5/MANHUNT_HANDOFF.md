# MANHUNT: OPEN WORLD (3 vs. 8) – Übergabe an die lokale Claude-Code-Sitzung

Diese Datei fasst eine Cloud-Sitzung zusammen. Bitte zuerst komplett lesen, dann weiterarbeiten.

## Nutzer & Arbeitsweise
- Lukas spricht **Deutsch** und ist **Unreal-Einsteiger**. Schritte klein halten, jeden Klick erklären.
- Der **Editor ist auf Deutsch**. Menüpunkte deutsch nennen und den englischen Namen in Klammern dazuschreiben.
  Wo möglich auf das Suchfeld verweisen (z. B. „GameMode“ eintippen).
- Ziel: ein **spielbares** Spiel, gebaut aus seinen Fab-Assets. Begehbare Gebäude nutzen und fehlende
  Gebäude/Modelle **selbst mit Blender** erstellen.

## Projekt
- Pfad: `C:\Users\lukas\Documents\Unreal Projects\manhuntclaude\manhuntclaude.uproject`
- **Unreal Engine 5.8** (nicht 5.5!): `C:\Program Files\Epic Games\UE_5.8\`
- Visual Studio 2022, MSVC 14.44, Windows SDK 10.0.22621
- Ursprünglich Blueprint-Projekt, per *New C++ Class* (`manhunt`) in ein C++-Projekt umgewandelt
- Build von der Kommandozeile (Editor vorher schließen, sonst blockiert Live Coding):
  `"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" manhuntclaudeEditor Win64 Development "-Project=C:\Users\lukas\Documents\Unreal Projects\manhuntclaude\manhuntclaude.uproject" -WaitMutex`
- Build-Log: `%LOCALAPPDATA%\UnrealBuildTool\Log.txt`. Editor-Log: `<Projekt>\Saved\Logs\manhuntclaude.log`
- Python im Editor: Plugin „Python Editor Script Plugin“. Ohne Editor-Fenster:
  `UnrealEditor-Cmd.exe "<uproject>" -run=pythonscript -script="<datei.py>"`, mit Editor: `UnrealEditor.exe "<uproject>" -ExecutePythonScript="<datei.py>"`

## Spezifikation (aus dem Master-Prompt-PDF, Kurzfassung)
3 Runner gegen 8 Hunter, Match 600 s, eine Open World (~1,5 x 1,5 km) mit Großstadt (Hochhäuser, Mall,
Supermarkt, Casino, U-Bahn, Gassen, CCTV), Dorf/Vorstadt (Kopfstein, Einfamilienhäuser, Dorfladen,
verrauchte Kneipe mit Spielautomaten, Werkstätten, Höfe/Scheunen), Wald/Natur (Wald, Trampelpfade,
Forstwege, Flüsse, Hochsitze, Waldhütten) und Center Zone (Verkehrsknoten, Hunter-Start). Gebäude sollen
begehbar sein. Hunter-Klassen: Hacker (CCTV, Bewegungssperre, schlechter Sprinter), Kampfsportler (mehr
Stamina, harter Griff), Fährtenleser (verblassende Spuren, Cooldown). Wirtschaft: Pfandflaschen sammeln,
Pfandautomat, Kassenschlange mit NPCs, Casino. Fahrzeuge: E-Scooter (30 km/h, Akku), Fahrrad (25 km/h,
Stamina). Pings: Silent Hunt alle 60 s (nur X/Y), Speedhunt 2x, Blitz-Drops 3:00/6:30, Finale ab 9:00 mit
Extraktion (Helipad Stadt, Van Dorf, Boot Wald-Fluss).

## Stand: C++-Plugin `Plugins/ManhuntCore` (kompiliert erfolgreich unter UE 5.8)
- Quellcode auch auf GitHub: Repo `vpumpkin/mre-blackjack`, Branch `claude/focused-edison-b0g1k4`, Ordner `ManhuntUE5/`
- `ManhuntCore/Source/ManhuntCore/`:
  - `Core/`: `AManhuntGameMode` (Teams, Klassenwahl 20 s, Matchflow, Pings, Speedhunt, Blitz, Finale, Sieg),
    `AManhuntGameState` (Phase, Zeit, Türen per FFastArraySerializer), `AManhuntPlayerState` (Team, Klasse,
    Geld in Cent, Pfandbon, Items), `AManhuntPlayerController` (Enhanced Input zur Laufzeit erzeugt, Pings,
    Nachrichten, Konsole `MH_Class`/`MH_Give`), `AManhuntCharacter` (+ `...Actions.cpp`: Stamina, Sprint per
    CompressedFlags, serverseitige Interaktion, Tackle/Struggle, Fahrzeuge, Items, Anti-Cheat
    `IsNetRelevantFor`), `UManhuntCharacterMovement`, `AManhuntHUD` (Canvas-Debug-HUD + Taktik-Tablet)
  - `Interfaces/`: `IManhuntInteractable` (= BPI_Interactable), `IManhuntMountableVehicle` (= BPI_MountableVehicle)
  - `Hunters/`: `UManhuntHackerComponent`, `AManhuntCCTVCamera`, `UManhuntTrackerComponent`, `UManhuntTrackingSubsystem`
  - `World/`: `AManhuntDoor`, `AManhuntBuildingVolume`, `AManhuntExtractionPoint`
  - `Vehicles/`: `AManhuntRideable`, `AManhuntEScooter`, `AManhuntBike`, `UManhuntVehicleData`
  - `Economy/`: `AManhuntLootSpot` (Mülleimer/Flaschen/Drops/Schnorren), `AManhuntPfandMachine`, `AManhuntCheckout` (Schlange mit NPCs)
- Für UE 5.8 bereits behoben: Variablen-Shadowing (C4458), `TWeakObjectPtr`-Zuweisungen brauchen
  vollständige Typen (nicht inline im Header), `EPhysicalSurface` statt `TEnumAsByte` in UFUNCTION-Parametern.
- **Noch nicht im Spiel getestet.** Erster Test: GameMode `ManhuntGameMode` (Projekteinstellungen und
  World Settings → GameMode Override), 2 Spielerstarts mit Tag `Runner`/`Hunter`, PIE mit 2 Spielern als
  Listen Server. Ablauf: Klassenwahl mit 1/2/3, nach 20 s Spawn, Tackle mit LMB, Losreißen mit Leertaste.
- Die Python-Namen der Klassen lauten `unreal.ManhuntLootSpot` usw., Enums `unreal.ManhuntItem.PFAND_BOTTLE`.

## Fab-Assets im Projekt (Liste: `Manhunt_Assets.txt` im Projektordner)
- **Stadt:** `/Game/Megapack/Maps/Yakohama/Yakohama`, `/Game/Downtown_West/Maps/Demo_Environment`,
  `/Game/Downtown_Alley/Maps/Downtown_Alley`, AccuCities (London-Kacheln), City_of_Brass (Fantasy)
- **Dorf:** JustBStudios 1850s Post Office (`.../Levels/L_Showcase` + SubLevels `L_House_Main`, `L_House_fish`,
  `L_House_fish_01`), `/Game/Cigar_room/Maps/Cigar_room` (Kneipe), Construction_VOL1/2 (Werkstatt/Baustelle),
  **ProceduralBuildingGenerator** (`/Prefabs/PBG_Building_2F_2R`, `2F_3R`, `3F_3R` = begehbare Häuser mit Räumen)
- **Natur:** `/Game/GrassLandscape/Map/LandscapeDemo`, TemplesOfCambodia Exterior, `/Game/BeachScene/Maps/Beach_Environment`, Cave_Ruins
- **Center:** `/Game/AutomotiveBridgeScene/Maps/Bridge_Meshes` + `Bridge_Details` (Brücke als Verkehrsknoten)
- **Innenräume:** `/Game/EF_FirstFloor/Maps/FirstFloor`, Deko_MatrixDemo Apartment, FreeFurniturePack
- **Figuren:** UE5-Mannequins mit fertigen ABPs: `/Game/SampleAnimationPack/Demo/Characters/Mannequins/Meshes/SKM_Quinn`
  + `.../Animations/ABP_Quinn` (Runner), `SKM_Manny` + `ABP_Manny` (Hunter). NPCs: `/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter`.
  Später realistischer: „Man“-Pack (UE4-Skelett) oder CitySampleCrowd (MetaHuman-Skelett) per IK-Retargeting.
- **Requisiten:** Mülleimer `/Game/Downtown_Alley/Models/SM_Trash_Bin_Big_Closed`, `SM_TrashBin_Close`,
  `/Game/AutomotiveBridgeScene/.../SM_Trashcan`, `/Game/Construction_VOL1/Meshes/SM_Dumpster`; Pfandflaschen
  `/Game/Downtown_Alley/Models/SM_Small_Trash_Bottle_01..10`; Boot `/Game/JustBStudios/1850sPostOffice/Meshes/SM_Boat`;
  Theke `/Game/EF_FirstFloor/Meshes/counter_island_a`; Kisten `/Game/Construction_VOL1/Meshes/SM_Crate_01a`;
  Kamera `/Game/HighTechPack1/Assets/meshes/Camera01/SM_Camera01`
- **Fehlt komplett:** E-Scooter, Fahrrad, Autos, Supermarkt, Casino/Spielautomaten, echte CCTV-Kamera, Wald-Bäume
  → mit Blender erstellen (oder weitere Fab-Pakete).

## Geplanter nächster Schritt (noch nicht umgesetzt)
1. **Charaktere:** Blueprints `BP_Runner`/`BP_Hunter` (Parent `ManhuntCharacter`, Mesh + AnimClass wie oben),
   `BP_BlitzDrop` (Parent `ManhuntLootSpot`, Ping-Blocker, Kisten-Mesh), `BP_ManhuntGameMode`
   (RunnerPawnClass/HunterPawnClass/BlitzDropClass gesetzt). Per Python über das CDO
   (`unreal.get_default_object(bp.generated_class())`).
2. **Karte** `/Game/Manhunt/Maps/L_Manhunt_OpenWorld`: Demo-Maps nach `/Game/Manhunt/Maps/Sectors/` duplizieren,
   in den Kopien globale Beleuchtung entfernen (DirectionalLight, SkyLight, SkyAtmosphere, Fog, VolumetricCloud,
   PostProcess, PlayerStart, HDRI/SkySphere-BPs), dann als Sublevels mit Versatz einbinden
   (`EditorLevelUtils.add_level_to_world_with_transform`, LevelStreamingAlwaysLoaded). Center in der Mitte, Stadt +X,
   Dorf +Y, Natur −Y, Supermarkt −X. Darüber eine eigene Beleuchtung, eine Bodenplatte für die Lücken und die
   Spielobjekte: Spielerstarts (8 Hunter im Zentrum, Runner pro Biom), Mülleimer/Flaschen als LootSpots, Supermarkt
   mit Pfandautomat + Kasse + NPC-Schlange, CCTV in der Stadt, Fahrzeuge, 2 Extraktionspunkte pro Biom,
   BuildingVolumes um begehbare Gebäude, TargetPoints mit Tag `BlitzDrop` und GameMode-Override in den World Settings.
3. **Blender:** begehbare modulare Gebäude erzeugen (Wände mit Tür-/Fensteröffnungen, Böden, Treppen, Dach;
   Pivot unten, Maßstab cm), dazu Supermarkt, Kneipe/Casino, Waldhütte, Hochsitz, E-Scooter, Fahrrad,
   Spielautomat, CCTV-Kamera, Helipad. Als FBX exportieren (Kollision als `UCX_`-Meshes oder in UE
   „Complex as Simple“), per Python importieren und platzieren.
4. Danach: Türen (`ManhuntDoor`) mit Blender-Türblättern (Pivot am Scharnier), Decal-Material für Fußspuren,
   Parkour/Vault, Casino-Modul, UMG-HUD und Umstellung auf World Partition.
