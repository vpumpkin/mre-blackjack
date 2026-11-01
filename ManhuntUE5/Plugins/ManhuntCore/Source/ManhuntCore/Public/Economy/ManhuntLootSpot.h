// Durchsuchbarer Fundort: Muelleimer/Parkbank/Wohnung (Pfandflaschen), Passant zum Schnorren
// (Kleingeld, 80 % Absage), Blitz-Challenge-Drop (Ping-Blocker/Fake-Ping) ...
// Fab-Integration: Mesh tauschen und Werte einstellen – oder Blueprint-Child pro Objekttyp.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Interfaces/ManhuntInteractable.h"
#include "ManhuntTypes.h"
#include "ManhuntLootSpot.generated.h"

class UStaticMeshComponent;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntLootSpot : public AActor, public IManhuntInteractable
{
	GENERATED_BODY()

public:
	AManhuntLootSpot();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Loot") TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") EManhuntItem LootItem = EManhuntItem::PfandBottle;
	/** Menge (bei Cash in Cent: 20..50 = 0,20 bis 0,50 EUR). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") int32 MinAmount = 1;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") int32 MaxAmount = 3;
	/** Erfolgschance (Schnorren bei Passanten: 0.2 = 80 % Absage). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot", meta = (ClampMin = "0", ClampMax = "1")) float FindChance = 0.65f;
	/** 0 = sofort aufheben. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") float SearchDuration = 2.5f;
	/** 0 = fuellt sich nie wieder auf. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") float RespawnSeconds = 90.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") bool bDestroyWhenLooted = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") bool bRunnersOnly = true;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") FText PromptText;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Loot") FText FailText;

	UFUNCTION(BlueprintImplementableEvent, Category = "Loot") void OnLooted(AManhuntCharacter* ByCharacter, int32 Amount);
	UFUNCTION(BlueprintImplementableEvent, Category = "Loot") void OnEmptyChanged(bool bNowEmpty);

	// IManhuntInteractable
	virtual bool CanInteract_Implementation(AManhuntCharacter* Interactor) override;
	virtual void Interact_Implementation(AManhuntCharacter* Interactor) override;
	virtual FText GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor) override;
	virtual void CancelInteraction_Implementation(AManhuntCharacter* Interactor) override;

protected:
	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION() void OnRep_Empty();
	void FinishSearch(AManhuntCharacter* ByCharacter);
	void SetEmpty(bool bNewEmpty);
	void Refill();

	UPROPERTY(ReplicatedUsing = OnRep_Empty) bool bEmpty = false;

	TWeakObjectPtr<AManhuntCharacter> Searcher;
	FTimerHandle RefillTimer;
};
