// MANHUNT: OPEN WORLD (3 vs. 8) – gemeinsame Typen, Enums und Structs.
#pragma once

#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "ManhuntTypes.generated.h"

class APlayerState;

MANHUNTCORE_API DECLARE_LOG_CATEGORY_EXTERN(LogManhunt, Log, All);

UENUM(BlueprintType)
enum class EManhuntTeam : uint8
{
	None,
	Runner,
	Hunter
};

/** Die 3 spezialisierten Hunter-Klassen (Runner haben keine Klasse). */
UENUM(BlueprintType)
enum class EHunterClass : uint8
{
	None,
	Hacker   UMETA(DisplayName = "Hacker (Stadt-Aufklaerer)"),
	Brawler  UMETA(DisplayName = "Kampfsportler (Nahkampf-Brecher)"),
	Tracker  UMETA(DisplayName = "Faehrtenleser (Spuren-Tracker)")
};

UENUM(BlueprintType)
enum class EManhuntPhase : uint8
{
	WaitingForPlayers,
	ClassSelection,
	Hunt,
	Finale,
	Ended
};

UENUM(BlueprintType)
enum class ERunnerStatus : uint8
{
	Free,
	Caught,
	Extracted
};

UENUM(BlueprintType)
enum class EManhuntBiome : uint8
{
	City        UMETA(DisplayName = "Grossstadt"),
	Village     UMETA(DisplayName = "Dorf & Vorstadt"),
	Forest      UMETA(DisplayName = "Wald & Natur"),
	CenterZone  UMETA(DisplayName = "Center Zone")
};

UENUM(BlueprintType)
enum class EManhuntPingType : uint8
{
	SilentHunt,
	Speedhunt,
	Finale
};

UENUM(BlueprintType)
enum class EManhuntDoorState : uint8
{
	Closed,
	Open,
	Locked
};

/** Inventar-Gegenstaende, die gefunden, gekauft oder benutzt werden koennen. */
UENUM(BlueprintType)
enum class EManhuntItem : uint8
{
	PfandBottle  UMETA(DisplayName = "Pfandflasche"),
	PingBlocker  UMETA(DisplayName = "Ping-Blocker"),
	FakePing     UMETA(DisplayName = "Fake-Ping"),
	EnergyDrink  UMETA(DisplayName = "Energy-Drink"),
	Cash         UMETA(DisplayName = "Bargeld (Cent)")
};

/** Gruende fuer eine Bewegungssperre (Bitmaske, serverseitig gesetzt und repliziert). */
namespace EManhuntLock
{
	enum Type : uint8
	{
		None    = 0,
		Busy    = 1 << 0, // z.B. Muelleimer durchsuchen
		Grabbed = 1 << 1, // Tackle / Struggle
		CCTV    = 1 << 2, // Hacker schaut auf das Kamerabild
		Caught  = 1 << 3,
		Stunned = 1 << 4  // Hunter nach erfolgreichem Losreissen des Runners
	};
}

/** Werte pro Rolle/Klasse. Defaults stehen im GameMode und sind im Blueprint editierbar. */
USTRUCT(BlueprintType)
struct FManhuntClassStats
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float MaxStamina = 100.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float WalkSpeed = 320.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float SprintSpeed = 600.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float SprintStaminaPerSecond = 10.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float StaminaRegenPerSecond = 8.f;
	/** Runner: 1.15 = 15 % wendiger bei Parkour/Klettern (Fenster, Zaeune). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float ParkourSpeedMultiplier = 1.f;
	/** Griffstaerke beim Tackle. Hoeher = Losreissen schwerer (Kampfsportler). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float GripStrength = 1.f;
	/** Ist die Runner-Stamina beim Tackle unter diesem Anteil (0..1), wird sofort gefangen. 0 = aus. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float InstantCatchStaminaRatio = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float AbilityCooldown = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Stats") float AbilityDuration = 0.f;
};

/**
 * Statischer Radar-Ping vom Server (FVector-Snapshot, KEINE Live-Position).
 * Bewusst nur X/Y: In Gebaeuden wird das Gebaeude im 2D-Grundriss gezeigt, nie das Stockwerk.
 */
USTRUCT(BlueprintType)
struct FManhuntRunnerPing
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Ping") TObjectPtr<APlayerState> Runner = nullptr;
	UPROPERTY(BlueprintReadOnly, Category = "Ping") FVector2D Location = FVector2D::ZeroVector;
	/** Leer = im Freien. Sonst Name des Gebaeudes (BuildingVolume). */
	UPROPERTY(BlueprintReadOnly, Category = "Ping") FName BuildingName;
	/** Halbe Ausdehnung des Gebaeude-Grundrisses (fuer die Markierung auf dem Taktik-Tablet). */
	UPROPERTY(BlueprintReadOnly, Category = "Ping") FVector2D BuildingExtent = FVector2D::ZeroVector;
	UPROPERTY(BlueprintReadOnly, Category = "Ping") EManhuntPingType Type = EManhuntPingType::SilentHunt;
};

/** Fussabdruck / Reifenspur, die der Faehrtenleser sehen kann. Age = Alter in Sekunden beim Senden. */
USTRUCT(BlueprintType)
struct FManhuntFootprint
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Track") FVector_NetQuantize10 Location = FVector::ZeroVector;
	UPROPERTY(BlueprintReadOnly, Category = "Track") float Yaw = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Track") float Age = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Track") bool bTireTrack = false;
};

namespace ManhuntMoney
{
	/** 250 -> "2,50 EUR" */
	inline FString Format(int32 Cents)
	{
		return FString::Printf(TEXT("%d,%02d EUR"), Cents / 100, FMath::Abs(Cents % 100));
	}
}
