// Stufe 2 des Pfand-Kreislaufs: Leergutautomat (Einkaufszentrum / Supermarkt).
// Flaschen werden EINZELN eingefuehrt (dauert, piept und rattert), am Ende druckt der
// Automat einen Pfandbon (Inventar-Item). Weglaufen oder erneutes [E] = Bon drucken.
// Fab-Integration: Automaten-Mesh setzen; Piep-/Ratter-Sounds in OnBottleAccepted.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Interfaces/ManhuntInteractable.h"
#include "ManhuntPfandMachine.generated.h"

class UStaticMeshComponent;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntPfandMachine : public AActor, public IManhuntInteractable
{
	GENERATED_BODY()

public:
	AManhuntPfandMachine();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Pfand") TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pfand") int32 BottleValueCents = 25;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pfand") float SecondsPerBottle = 1.6f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pfand") float MaxUseDistance = 260.f;

	UFUNCTION(BlueprintPure, Category = "Pfand") AManhuntCharacter* GetCurrentUser() const { return CurrentUser; }

	/** Piepen/Rattern (alle Clients in der Naehe hoeren es – auch Hunter!). Count > 0 pruefen. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Pfand") void OnBottleAccepted(int32 Count);
	UFUNCTION(BlueprintImplementableEvent, Category = "Pfand") void OnBonPrinted(int32 ValueCents);

	// IManhuntInteractable
	virtual bool CanInteract_Implementation(AManhuntCharacter* Interactor) override;
	virtual void Interact_Implementation(AManhuntCharacter* Interactor) override;
	virtual FText GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor) override;
	virtual void CancelInteraction_Implementation(AManhuntCharacter* Interactor) override;

protected:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION() void OnRep_InsertedCount();
	void InsertNextBottle();
	void PrintBon();

	UPROPERTY(Replicated) TObjectPtr<AManhuntCharacter> CurrentUser;
	UPROPERTY(ReplicatedUsing = OnRep_InsertedCount) int32 InsertedCount = 0;

	FTimerHandle InsertTimer;
};
