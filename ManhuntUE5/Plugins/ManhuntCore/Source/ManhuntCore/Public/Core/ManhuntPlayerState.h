// Team, Hunter-Klasse, Geld (in Cent!) und Inventar eines Spielers.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "ManhuntTypes.h"
#include "ManhuntPlayerState.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnManhuntPlayerStateChanged);

UCLASS()
class MANHUNTCORE_API AManhuntPlayerState : public APlayerState
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "Manhunt") EManhuntTeam GetTeam() const { return Team; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") EHunterClass GetHunterClass() const { return HunterClass; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") bool IsTaskforceLeader() const { return bTaskforceLeader; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") ERunnerStatus GetRunnerStatus() const { return RunnerStatus; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") bool IsFreeRunner() const { return Team == EManhuntTeam::Runner && RunnerStatus == ERunnerStatus::Free; }

	UFUNCTION(BlueprintPure, Category = "Manhunt|Economy") int32 GetMoneyCents() const { return MoneyCents; }
	UFUNCTION(BlueprintPure, Category = "Manhunt|Economy") int32 GetPfandbonCents() const { return PfandbonCents; }
	UFUNCTION(BlueprintPure, Category = "Manhunt|Economy") int32 GetBottleCount() const { return BottleCount; }
	UFUNCTION(BlueprintPure, Category = "Manhunt|Economy") int32 GetItemCount(EManhuntItem Item) const;

	// ---- Nur Server ----
	void SetTeam(EManhuntTeam NewTeam);
	void SetHunterClass(EHunterClass NewClass);
	void SetTaskforceLeader(bool bLeader);
	void SetRunnerStatus(ERunnerStatus NewStatus);

	void AddItem(EManhuntItem Item, int32 Amount);
	/** Entfernt 1 Stueck. false, wenn keins vorhanden ist. */
	bool ConsumeItem(EManhuntItem Item);
	bool SpendMoney(int32 Cents);
	void AddPfandbon(int32 Cents);
	/** Kasse: Pfandbon -> Bargeld. Gibt den ausgezahlten Betrag zurueck. */
	int32 CashOutPfandbon();

	/** Joker sind "scharf" geschaltet und wirken beim naechsten Ping (Server). */
	bool bPingBlockerArmed = false;
	bool bFakePingArmed = false;

	UPROPERTY(BlueprintAssignable, Category = "Manhunt")
	FOnManhuntPlayerStateChanged OnManhuntStateChanged;

protected:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION() void OnRep_Changed();
	void NotifyChanged();

	UPROPERTY(ReplicatedUsing = OnRep_Changed) EManhuntTeam Team = EManhuntTeam::None;
	UPROPERTY(ReplicatedUsing = OnRep_Changed) EHunterClass HunterClass = EHunterClass::None;
	UPROPERTY(ReplicatedUsing = OnRep_Changed) bool bTaskforceLeader = false;
	UPROPERTY(ReplicatedUsing = OnRep_Changed) ERunnerStatus RunnerStatus = ERunnerStatus::Free;

	/** Fuer alle sichtbar: je mehr Flaschen, desto lauter klappert der Rucksack. */
	UPROPERTY(ReplicatedUsing = OnRep_Changed) int32 BottleCount = 0;

	// Nur fuer den Besitzer repliziert (Anti-Cheat: Hunter sehen kein Runner-Inventar).
	UPROPERTY(ReplicatedUsing = OnRep_Changed) int32 MoneyCents = 0;
	UPROPERTY(ReplicatedUsing = OnRep_Changed) int32 PfandbonCents = 0;
	UPROPERTY(ReplicatedUsing = OnRep_Changed) int32 PingBlockers = 0;
	UPROPERTY(ReplicatedUsing = OnRep_Changed) int32 FakePings = 0;
	UPROPERTY(ReplicatedUsing = OnRep_Changed) int32 EnergyDrinks = 0;
};
