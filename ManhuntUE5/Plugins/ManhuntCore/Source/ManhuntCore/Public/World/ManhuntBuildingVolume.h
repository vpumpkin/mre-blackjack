// Box um ein begehbares Gebaeude (Mall, Hochhaus, Scheune ...). Der Ping zeigt dann nur
// das Gebaeude im 2D-Grundriss – nie das Stockwerk. Einfach um das Fab-Gebaeude ziehen.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ManhuntTypes.h"
#include "ManhuntBuildingVolume.generated.h"

class UBoxComponent;
class UPrimitiveComponent;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntBuildingVolume : public AActor
{
	GENERATED_BODY()

public:
	AManhuntBuildingVolume();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Building") TObjectPtr<UBoxComponent> Box;
	/** Name auf dem Taktik-Tablet, z.B. "Einkaufszentrum" oder "Scheune Hof Berger". */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Building") FName BuildingName = TEXT("Gebaeude");
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Building") EManhuntBiome Biome = EManhuntBiome::City;

	/** Halbe Ausdehnung des Grundrisses (achsenparallel, Welt-X/Y). */
	FVector2D GetFootprintExtent() const;

protected:
	virtual void BeginPlay() override;

	UFUNCTION() void OnBeginOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor, UPrimitiveComponent* OtherComp,
		int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);
	UFUNCTION() void OnEndOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex);
};
