// Server-Logik des 10-Minuten-Matchflows: Teams (3 Runner vs. 8 Hunter), Klassenwahl,
// Silent Hunt (alle 60 s), Speedhunt (2x), Blitz-Challenges (3:00 & 6:30), Finale (9:00-10:00).
// Alle Zahlen sind im Blueprint-Child (BP_ManhuntGameMode) editierbar.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameMode.h"
#include "ManhuntTypes.h"
#include "ManhuntGameMode.generated.h"

class AManhuntPlayerState;
class AManhuntGameState;
class AManhuntCharacter;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntGameMode : public AGameMode
{
	GENERATED_BODY()

public:
	AManhuntGameMode();

	// ---------------- Regeln ----------------
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 MaxRunners = 3;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 MaxHunters = 8;
	/** Zum Testen 2 (1 Runner + 1 Hunter). Fuer echte Matches 11. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 MinPlayersToStart = 2;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") float ClassSelectionSeconds = 20.f;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 MatchDurationSeconds = 600;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 SilentHuntInterval = 60;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 FinaleStartSecond = 540;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 FinalePingInterval = 15;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") TArray<int32> BlitzChallengeSeconds;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 SpeedhuntsPerMatch = 2;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 SpeedhuntDuration = 60;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") int32 SpeedhuntPingInterval = 10;
	/** true: Runner gewinnen nur per Extraktion. false: Ueberleben bis 10:00 reicht. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") bool bRunnersMustExtract = true;
	/** Fake-Ping: Versatz der falschen Position in cm. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") FVector2D FakePingOffsetRange = FVector2D(25000.f, 60000.f);
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Rules") float RestartDelayAfterMatch = 20.f;

	// ---------------- Klassen & Fab-Charaktere ----------------
	/** BP_Runner / BP_Hunter mit euren Fab-Meshes. Leer = DefaultPawnClass. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Classes") TSubclassOf<APawn> RunnerPawnClass;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Classes") TSubclassOf<APawn> HunterPawnClass;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Classes") FManhuntClassStats RunnerStats;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Classes") TMap<EHunterClass, FManhuntClassStats> HunterStats;

	// ---------------- Blitz-Challenges ----------------
	/** Risiko-Drop (z.B. BP_ManhuntLootSpot mit Ping-Blocker/Fake-Ping und Fab-Mesh). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Blitz") TSubclassOf<AActor> BlitzDropClass;
	/** Actor-Tag der Spawnpunkte in der Center Zone (z.B. TargetPoints). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Blitz") FName BlitzDropSpawnTag = TEXT("BlitzDrop");
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|Blitz") int32 DropsPerChallenge = 3;

	// ---------------- API ----------------
	const FManhuntClassStats& GetStatsFor(const AManhuntPlayerState* PS) const;
	bool TrySelectHunterClass(AManhuntPlayerState* PS, EHunterClass NewClass);
	bool TryStartSpeedhunt(AManhuntPlayerState* Requester, AManhuntPlayerState* Target);
	void HandleRunnerCaught(AManhuntCharacter* Runner, AManhuntCharacter* Hunter);
	void HandleRunnerExtracted(AManhuntCharacter* Runner, AActor* ExtractionPoint);
	void BroadcastMessage(const FText& Message, EManhuntTeam OnlyTeam = EManhuntTeam::None);

	// ---------------- Blueprint-Hooks (Musik, Licht, Zonen-Grenzen ...) ----------------
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnHuntStarted();
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnBlitzChallenge(int32 ChallengeIndex);
	/** Hier die Zonen-Grenzen (Data Layers / Blocking Volumes) abschalten. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnFinaleStarted();
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnManhuntEnded(EManhuntTeam Winner);

protected:
	virtual void PostLogin(APlayerController* NewPlayer) override;
	virtual void Logout(AController* Exiting) override;
	virtual UClass* GetDefaultPawnClassForController_Implementation(AController* InController) override;
	virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;
	virtual bool ReadyToStartMatch_Implementation() override;
	virtual bool PlayerCanRestart_Implementation(APlayerController* Player) override;
	virtual void HandleMatchHasStarted() override;

	AManhuntGameState* GetManhuntGameState() const;
	void AssignTeam(AManhuntPlayerState* PS);
	void EnsureTaskforceLeader();
	void MatchTick();
	void SendRunnerPings(EManhuntPingType Type, AManhuntPlayerState* OnlyRunner = nullptr);
	void SpawnBlitzDrops(int32 ChallengeIndex);
	void StartFinale();
	void CheckEndConditions();
	void EndManhunt(EManhuntTeam Winner);
	void RemoveRunnerFromPlay(AManhuntCharacter* Runner, float Delay);

	FTimerHandle MatchTickTimer;
	int32 ElapsedSeconds = 0;
	bool bClassSelectionStarted = false;
	bool bMatchFinished = false;
	TWeakObjectPtr<AManhuntPlayerState> SpeedhuntTarget;
	int32 SpeedhuntSecondsLeft = 0;
	int32 SpeedhuntsUsed = 0;
};
