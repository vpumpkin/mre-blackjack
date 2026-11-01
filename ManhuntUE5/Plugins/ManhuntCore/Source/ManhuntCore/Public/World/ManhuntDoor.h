// Tuer oder Fenster (100 % begehbare Gebaeude). Der Actor selbst repliziert NICHT –
// sein Zustand liegt im GameState-FastArray. So kosten tausende Tueren keine Bandbreite.
// Fab-Integration: Mesh im Blueprint-Child (oder in der Packed-Level-Actor-Vorlage)
// auf "DoorLeaf" setzen, Pivot = Scharnier.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Interfaces/ManhuntInteractable.h"
#include "ManhuntTypes.h"
#include "ManhuntDoor.generated.h"

class UStaticMeshComponent;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntDoor : public AActor, public IManhuntInteractable
{
	GENERATED_BODY()

public:
	AManhuntDoor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Door") TObjectPtr<USceneComponent> Root;
	/** Das bewegliche Teil (Tuerblatt / Fensterfluegel). Pivot muss am Scharnier liegen. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Door") TObjectPtr<UStaticMeshComponent> DoorLeaf;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Door") EManhuntDoorState DefaultState = EManhuntDoorState::Closed;
	/** Fenster: offen = kletterbar fuer Parkour. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Door") bool bIsWindow = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Door") float OpenYaw = 95.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Door") float OpenSpeed = 240.f;
	/** Runner koennen von innen verriegeln (haelt Hunter auf). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Door") bool bRunnerCanLock = true;

	uint64 GetDoorKey() const { return DoorKey; }
	EManhuntDoorState GetDefaultState() const { return DefaultState; }
	UFUNCTION(BlueprintPure, Category = "Door") EManhuntDoorState GetDoorState() const { return CurrentState; }

	/** Lokal anwenden (vom GameState aufgerufen, Server + Clients). */
	void ApplyDoorState(EManhuntDoorState NewState);

	/** Server: Zustand aendern (repliziert ueber den GameState). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Door")
	void SetDoorStateServer(EManhuntDoorState NewState);

	/** Deterministischer Schluessel aus der Weltposition: identisch auf Server und Clients,
	 *  funktioniert auch fuer Level Instances, Packed Level Actors und PCG-Spawns. */
	static uint64 MakeDoorKey(const FVector& Location);

	/** Server: Runner verriegelt/entriegelt eine geschlossene Tuer (Faehigkeits-Taste [Q] als Runner). */
	bool TryToggleLock(AManhuntCharacter* Interactor);

	/** Fuer Sounds/Animation im Blueprint (Fab-Sounds hier anschliessen). */
	UFUNCTION(BlueprintImplementableEvent, Category = "Door")
	void OnDoorStateChanged(EManhuntDoorState NewState);

	// IManhuntInteractable
	virtual bool CanInteract_Implementation(AManhuntCharacter* Interactor) override;
	virtual void Interact_Implementation(AManhuntCharacter* Interactor) override;
	virtual FText GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor) override;
	virtual void CancelInteraction_Implementation(AManhuntCharacter* Interactor) override {}

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;

	uint64 DoorKey = 0;
	EManhuntDoorState CurrentState = EManhuntDoorState::Closed;
	float CurrentYaw = 0.f;
	float OpenDirection = 1.f;
};
