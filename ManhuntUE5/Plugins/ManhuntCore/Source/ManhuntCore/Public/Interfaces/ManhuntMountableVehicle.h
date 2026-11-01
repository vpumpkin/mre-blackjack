// BPI_MountableVehicle – E-Scooter, Fahrraeder (und spaeter weitere Fab-Fahrzeuge).
// Das Fahrzeug liefert nur Regeln (Tempo je Untergrund, Kosten); bewegt wird der
// Charakter selbst ueber seine CharacterMovement. Das spart eigene Fahrzeugphysik
// und ist im Multiplayer voll vorhergesagt (Client-Prediction).
#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "Chaos/ChaosEngineInterface.h"
#include "ManhuntMountableVehicle.generated.h"

class AManhuntCharacter;

UINTERFACE(MinimalAPI, Blueprintable)
class UManhuntMountableVehicle : public UInterface
{
	GENERATED_BODY()
};

class MANHUNTCORE_API IManhuntMountableVehicle
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Vehicle")
	bool CanMount(AManhuntCharacter* Rider);

	/** Server. */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Vehicle")
	void Mount(AManhuntCharacter* Rider);

	/** Server. */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Vehicle")
	void Dismount(AManhuntCharacter* Rider);

	/** Hoechsttempo in cm/s auf diesem Untergrund. 0 = hier unbrauchbar (Treppe, Matsch). */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Vehicle")
	float GetMaxSpeedOnSurface(TEnumAsByte<EPhysicalSurface> Surface);

	/** Stamina-Kosten pro Sekunde bei voller Fahrt (Fahrrad > 0, E-Scooter = 0). */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Vehicle")
	float GetRiderStaminaCostPerSecond();
};
