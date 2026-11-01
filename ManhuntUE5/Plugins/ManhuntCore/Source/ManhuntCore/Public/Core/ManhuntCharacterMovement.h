// CharacterMovement mit vorhergesagtem Sprint (CompressedFlags), Stamina-Simulation
// und Fahrzeug-Tempo je Untergrund (UPhysicalMaterial -> EPhysicalSurface).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Chaos/ChaosEngineInterface.h"
#include "ManhuntCharacterMovement.generated.h"

UCLASS()
class MANHUNTCORE_API UManhuntCharacterMovement : public UCharacterMovementComponent
{
	GENERATED_BODY()

public:
	UManhuntCharacterMovement();

	/** Wird vom Client gesetzt und per CompressedFlags an den Server uebertragen. */
	uint8 bWantsToSprint : 1;

	UFUNCTION(BlueprintPure, Category = "Manhunt|Movement") bool IsSprinting() const;
	UFUNCTION(BlueprintPure, Category = "Manhunt|Movement") EPhysicalSurface GetCurrentSurface() const { return CurrentSurface; }

	virtual float GetMaxSpeed() const override;
	virtual void UpdateFromCompressedFlags(uint8 Flags) override;
	virtual FNetworkPredictionData_Client* GetPredictionData_Client() const override;

protected:
	/** Laeuft pro Move auf Client (Prediction) und Server (Replay) -> deterministisch. */
	virtual void UpdateCharacterStateBeforeMovement(float DeltaSeconds) override;

	void UpdateSurface();

	TEnumAsByte<EPhysicalSurface> CurrentSurface = SurfaceType_Default;
};
