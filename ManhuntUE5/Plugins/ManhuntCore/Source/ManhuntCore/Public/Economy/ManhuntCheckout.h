// Stufe 3 des Pfand-Kreislaufs: die Supermarktkasse mit echter Warteschlange.
// Der Runner stellt sich HINTER die wartenden NPC-Kunden, rueckt automatisch auf und bekommt
// vorne vom Kassierer das Bargeld fuer seinen Pfandbon. Social Stealth: In der Schlange
// schlurft er wie ein NPC – Hunter muessen genau hinsehen.
// Fab-Integration: Kassentheken-Mesh auf "CounterMesh", "QueueStart" (Pfeil) vor den Kassierer
// legen (Pfeil zeigt zur Kasse), NPC-Kunden-Blueprints (Fab-Charaktere mit Idle-Animation)
// in NpcCustomerClasses eintragen.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Interfaces/ManhuntInteractable.h"
#include "ManhuntCheckout.generated.h"

class UStaticMeshComponent;
class UArrowComponent;

USTRUCT()
struct FManhuntQueueEntry
{
	GENERATED_BODY()

	UPROPERTY() TObjectPtr<AActor> Actor = nullptr;
	/** Nur auf dem Server bekannt: Clients sollen Spieler nicht an diesem Flag erkennen. */
	UPROPERTY(NotReplicated) bool bIsPlayer = false;
	/** Server: Spieler hat seinen Platz einmal erreicht (erst dann zaehlt "Platz verlassen"). */
	UPROPERTY(NotReplicated) bool bArrived = false;
	UPROPERTY(NotReplicated) float JoinTime = 0.f;
};

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntCheckout : public AActor, public IManhuntInteractable
{
	GENERATED_BODY()

public:
	AManhuntCheckout();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Checkout") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Checkout") TObjectPtr<UStaticMeshComponent> CounterMesh;
	/** Platz 1 der Schlange (auf Bodenhoehe). Die Schlange waechst entgegen der Pfeilrichtung. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Checkout") TObjectPtr<UArrowComponent> QueueStart;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") float SlotSpacing = 95.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") int32 MaxQueueLength = 8;
	/** Bedienzeit pro Kunde (min/max Sekunden). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") FVector2D ServiceTimeRange = FVector2D(5.f, 9.f);
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") TArray<TSubclassOf<AActor>> NpcCustomerClasses;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") int32 InitialNpcCount = 3;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") FVector2D NpcArrivalIntervalRange = FVector2D(6.f, 14.f);
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") float NpcMoveSpeed = 110.f;
	/** Wer sich weiter als das von seinem Platz entfernt, verliert ihn. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") float LeaveDistance = 260.f;
	/** Nur Clients in diesem Umkreis bekommen die Schlange repliziert (Anti-Cheat). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Checkout") float ReplicationRadius = 6000.f;

	FVector GetSlotLocation(int32 Index) const;
	int32 GetQueueIndex(const AActor* Who) const;
	bool GetSlotLocationFor(const AActor* Who, FVector& OutLocation) const;

	/** Kassen-Piepen, Schublade, "Naechster bitte!" (Fab-Sounds/Animationen). */
	UFUNCTION(BlueprintImplementableEvent, Category = "Checkout") void OnCustomerServed(AActor* Customer, int32 PaidCents);

	// IManhuntInteractable
	virtual bool CanInteract_Implementation(AManhuntCharacter* Interactor) override;
	virtual void Interact_Implementation(AManhuntCharacter* Interactor) override;
	virtual FText GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor) override;
	virtual void CancelInteraction_Implementation(AManhuntCharacter* Interactor) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual bool IsNetRelevantFor(const AActor* RealViewer, const AActor* ViewTarget, const FVector& SrcLocation) const override;

	void ScheduleService();
	void ServeFront();
	void ScheduleArrival();
	void SpawnNpc();
	void RemoveEntryAt(int32 Index, bool bDestroyNpc);
	void MoveNpcs(float DeltaSeconds);
	void CheckPlayersInLine();

	UPROPERTY(Replicated) TArray<FManhuntQueueEntry> Queue;

	FTimerHandle ServiceTimer;
	FTimerHandle ArrivalTimer;
	float LastAdvanceTime = 0.f;
};
