// Replizierter Match-Zustand fuer alle 11 Spieler: Phase, Zeit, Speedhunt-Alarm und
// der bandbreitensparende Tuer-/Fenster-Status (FFastArraySerializer).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameState.h"
#include "Net/Serialization/FastArraySerializer.h"
#include "ManhuntTypes.h"
#include "ManhuntGameState.generated.h"

class AManhuntGameState;
class AManhuntDoor;

/** Ein Eintrag existiert NUR, solange die Tuer vom Ausgangszustand abweicht -> tausende Tueren kosten 0 Bytes. */
USTRUCT()
struct FManhuntDoorItem : public FFastArraySerializerItem
{
	GENERATED_BODY()

	UPROPERTY() uint64 DoorKey = 0;
	UPROPERTY() EManhuntDoorState State = EManhuntDoorState::Closed;

	void PostReplicatedAdd(const struct FManhuntDoorArray& InArray);
	void PostReplicatedChange(const struct FManhuntDoorArray& InArray);
	void PreReplicatedRemove(const struct FManhuntDoorArray& InArray);
};

USTRUCT()
struct FManhuntDoorArray : public FFastArraySerializer
{
	GENERATED_BODY()

	UPROPERTY() TArray<FManhuntDoorItem> Items;

	/** Nicht repliziert, lokal gesetzt: Ziel fuer die Client-Callbacks. */
	TWeakObjectPtr<AManhuntGameState> OwnerState;

	bool NetDeltaSerialize(FNetDeltaSerializeInfo& DeltaParms)
	{
		return FFastArraySerializer::FastArrayDeltaSerialize<FManhuntDoorItem, FManhuntDoorArray>(Items, DeltaParms, *this);
	}
};

template<>
struct TStructOpsTypeTraits<FManhuntDoorArray> : public TStructOpsTypeTraitsBase2<FManhuntDoorArray>
{
	enum { WithNetDeltaSerializer = true };
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnManhuntPhaseChanged, EManhuntPhase, NewPhase);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnManhuntSpeedhuntChanged, bool, bActive);

UCLASS()
class MANHUNTCORE_API AManhuntGameState : public AGameState
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "Manhunt") EManhuntPhase GetPhase() const { return Phase; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") int32 GetElapsedSeconds() const { return ElapsedSeconds; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") int32 GetRemainingSeconds() const { return FMath::Max(0, MatchDurationSeconds - ElapsedSeconds); }
	UFUNCTION(BlueprintPure, Category = "Manhunt") float GetClassSelectionRemaining() const;
	UFUNCTION(BlueprintPure, Category = "Manhunt") bool IsSpeedhuntActive() const { return bSpeedhuntActive; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") int32 GetSpeedhuntsRemaining() const { return SpeedhuntsRemaining; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") EManhuntTeam GetWinningTeam() const { return WinningTeam; }

	/** Beschleunigter Tag-Nacht-Zyklus: 600 s Match -> DayCycleStartHour..DayCycleEndHour. Fuer Sky-/Licht-Blueprints. */
	UFUNCTION(BlueprintPure, Category = "Manhunt") float GetTimeOfDayHours() const;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|DayCycle") float DayCycleStartHour = 15.f;
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Manhunt|DayCycle") float DayCycleEndHour = 23.f;

	UPROPERTY(BlueprintAssignable, Category = "Manhunt") FOnManhuntPhaseChanged OnPhaseChanged;
	UPROPERTY(BlueprintAssignable, Category = "Manhunt") FOnManhuntSpeedhuntChanged OnSpeedhuntChanged;

	// ---- Nur Server ----
	void SetPhase(EManhuntPhase NewPhase);
	void SetElapsedSeconds(int32 Seconds) { ElapsedSeconds = Seconds; }
	void SetMatchDuration(int32 Seconds) { MatchDurationSeconds = Seconds; }
	void SetClassSelectionEnd(float ServerTime) { ClassSelectionEndServerTime = ServerTime; }
	void SetSpeedhunt(bool bActive, int32 Remaining);
	void SetWinningTeam(EManhuntTeam Team) { WinningTeam = Team; }

	// ---- Tueren & Fenster ----
	/** Server: Zustand setzen. Ist er gleich dem Ausgangszustand, wird der Eintrag entfernt. */
	void SetDoorState(uint64 DoorKey, EManhuntDoorState NewState, EManhuntDoorState DefaultState);
	bool FindDoorState(uint64 DoorKey, EManhuntDoorState& OutState) const;
	/** Jede Tuer meldet sich lokal an (Server und Clients), auch nach World-Partition-Streaming. */
	void RegisterDoor(AManhuntDoor* Door);
	void UnregisterDoor(AManhuntDoor* Door);
	/** Client: aus den FastArray-Callbacks. */
	void HandleDoorReplicated(uint64 DoorKey, EManhuntDoorState State, bool bRemoved);

protected:
	virtual void PostInitializeComponents() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION() void OnRep_Phase();
	UFUNCTION() void OnRep_Speedhunt();

	UPROPERTY(ReplicatedUsing = OnRep_Phase) EManhuntPhase Phase = EManhuntPhase::WaitingForPlayers;
	UPROPERTY(Replicated) int32 ElapsedSeconds = 0;
	UPROPERTY(Replicated) int32 MatchDurationSeconds = 600;
	UPROPERTY(Replicated) float ClassSelectionEndServerTime = 0.f;
	UPROPERTY(ReplicatedUsing = OnRep_Speedhunt) bool bSpeedhuntActive = false;
	UPROPERTY(Replicated) int32 SpeedhuntsRemaining = 2;
	UPROPERTY(Replicated) EManhuntTeam WinningTeam = EManhuntTeam::None;

	UPROPERTY(Replicated) FManhuntDoorArray DoorStates;

	/** Lokal (nicht repliziert): DoorKey -> geladene Tuer. */
	TMap<uint64, TWeakObjectPtr<AManhuntDoor>> DoorRegistry;
};
