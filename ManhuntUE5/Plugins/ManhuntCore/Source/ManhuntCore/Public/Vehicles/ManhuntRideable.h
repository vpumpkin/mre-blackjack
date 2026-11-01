// E-Scooter & Fahrrad (3-Stufen-Fortbewegung). Das Fahrzeug wird an den Charakter gehaengt,
// gefahren wird mit der vorhergesagten CharacterMovement -> kein Lag, keine eigene Fahrphysik.
// Tempo je Untergrund ueber UPhysicalMaterial-SurfaceTypes (Projekt-Einstellungen -> Physics):
//   SurfaceType1 Asphalt | 2 Kopfsteinpflaster | 3 Waldboden/Matsch | 4 Schotter | 5 Treppe | 6 Gras
// Fab-Integration: Fahrzeug-Mesh auf "VehicleMesh" setzen (Pivot unten mittig), optional DataAsset.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/DataAsset.h"
#include "Interfaces/ManhuntInteractable.h"
#include "Interfaces/ManhuntMountableVehicle.h"
#include "ManhuntRideable.generated.h"

class UStaticMeshComponent;

USTRUCT(BlueprintType)
struct FManhuntVehicleConfig
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") FText DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") float MaxSpeedKmh = 30.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") float DefaultSurfaceMultiplier = 1.f;
	/** Tempo-Faktor je Untergrund (0 = unbrauchbar -> automatisch absteigen). */
	UPROPERTY(EditAnywhere, Category = "Vehicle") TMap<TEnumAsByte<EPhysicalSurface>, float> SurfaceMultipliers;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") bool bUsesBattery = true;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") float BatteryCapacitySeconds = 300.f;
	/** Fahrrad: Stamina-Kosten beim schnellen Treten. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") float RiderStaminaPerSecond = 0.f;
	/** Freischalten per Handy-App (Runner). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") int32 UnlockPriceCents = 300;
	/** Taskforce-Flatrate. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") bool bFreeForHunters = true;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") FVector MountOffset = FVector(0.f, 0.f, -96.f);
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") FRotator MountRotation = FRotator::ZeroRotator;
};

/** Austauschbare Fahrzeugwerte (z.B. DA_EScooter_Fab, DA_Mountainbike_Fab). */
UCLASS(BlueprintType)
class MANHUNTCORE_API UManhuntVehicleData : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") FManhuntVehicleConfig Config;
};

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntRideable : public AActor, public IManhuntInteractable, public IManhuntMountableVehicle
{
	GENERATED_BODY()

public:
	AManhuntRideable();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Vehicle") TObjectPtr<UStaticMeshComponent> VehicleMesh;
	/** Optional: ueberschreibt Config. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") TObjectPtr<UManhuntVehicleData> VehicleData;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle") FManhuntVehicleConfig Config;
	/** false = unverschlossen -> Runner koennen ihn gratis "klauen". */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category = "Vehicle") bool bLocked = true;

	const FManhuntVehicleConfig& GetConfig() const { return VehicleData ? VehicleData->Config : Config; }
	UFUNCTION(BlueprintPure, Category = "Vehicle") float GetBatteryRatio() const;
	UFUNCTION(BlueprintPure, Category = "Vehicle") AManhuntCharacter* GetRider() const { return Rider; }

	UFUNCTION(BlueprintImplementableEvent, Category = "Vehicle") void OnRiderChanged(AManhuntCharacter* NewRider);

	// IManhuntInteractable
	virtual bool CanInteract_Implementation(AManhuntCharacter* Interactor) override;
	virtual void Interact_Implementation(AManhuntCharacter* Interactor) override;
	virtual FText GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor) override;
	virtual void CancelInteraction_Implementation(AManhuntCharacter* Interactor) override {}

	// IManhuntMountableVehicle
	virtual bool CanMount_Implementation(AManhuntCharacter* NewRider) override;
	virtual void Mount_Implementation(AManhuntCharacter* NewRider) override;
	virtual void Dismount_Implementation(AManhuntCharacter* OldRider) override;
	virtual float GetMaxSpeedOnSurface_Implementation(EPhysicalSurface Surface) override;
	virtual float GetRiderStaminaCostPerSecond_Implementation() override;

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION() void OnRep_Rider();

	UPROPERTY(ReplicatedUsing = OnRep_Rider) TObjectPtr<AManhuntCharacter> Rider;
	UPROPERTY(Replicated) float BatterySeconds = 300.f;
};

/** E-Scooter: Stadt-Sprinter, 30 km/h, Akku statt Stamina, 3,00 EUR per App. */
UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntEScooter : public AManhuntRideable
{
	GENERATED_BODY()
public:
	AManhuntEScooter();
};

/** Fahrrad/Mountainbike: Biom-Wechsler, 25 km/h, kostet langsam Stamina, 4,00 EUR Leihgebuehr. */
UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntBike : public AManhuntRideable
{
	GENERATED_BODY()
public:
	AManhuntBike();
};
