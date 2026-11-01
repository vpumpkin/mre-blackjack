// Extraktionspunkt fuers Finale (ab 9:00): Helipad auf Stadt-Dach, Flucht-Van im Dorf,
// Motorboot am Wald-Fluss. Pro Biom wird genau einer zufaellig aktiviert.
// Fab-Integration: Helikopter/Van/Boot als Mesh setzen, Rotor-/Motor-Sound in OnActiveChanged.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ManhuntTypes.h"
#include "ManhuntExtractionPoint.generated.h"

class USphereComponent;
class UStaticMeshComponent;
class AManhuntCharacter;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntExtractionPoint : public AActor
{
	GENERATED_BODY()

public:
	AManhuntExtractionPoint();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Extraction") TObjectPtr<USphereComponent> Trigger;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Extraction") TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Extraction") EManhuntBiome Biome = EManhuntBiome::City;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Extraction") FText DisplayName;
	/** So lange muss ein Runner ungestoert im Bereich bleiben. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Extraction") float ExtractionHoldTime = 5.f;

	UFUNCTION(BlueprintPure, Category = "Extraction") bool IsExtractionActive() const { return bActive; }

	/** Server. */
	void SetExtractionActive(bool bNewActive);

	UFUNCTION(BlueprintImplementableEvent, Category = "Extraction") void OnActiveChanged(bool bNowActive);

protected:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	UFUNCTION() void OnRep_Active();
	void CheckRunners();

	UPROPERTY(ReplicatedUsing = OnRep_Active) bool bActive = false;

	TMap<TWeakObjectPtr<AManhuntCharacter>, float> RunnersInside;
	FTimerHandle CheckTimer;
};
