// Server-only: speichert Fussabdruecke und Reifenspuren aller Runner in einem Ringpuffer.
// Clients bekommen Spuren NUR, wenn ein Faehrtenleser seine Faehigkeit aktiviert (Anti-Cheat).
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "ManhuntTypes.h"
#include "ManhuntTrackingSubsystem.generated.h"

UCLASS()
class MANHUNTCORE_API UManhuntTrackingSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	void RecordStep(const FVector& Location, float Yaw, bool bTireTrack);

	/** Spuren im Radius, juenger als MaxAge, neueste zuerst. Age wird beim Sammeln berechnet. */
	void GatherFootprints(const FVector& Center, float Radius, float MaxAge, int32 MaxCount, TArray<FManhuntFootprint>& OutPrints) const;

protected:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

private:
	struct FStep
	{
		FVector Location = FVector::ZeroVector;
		float Yaw = 0.f;
		double Time = -1.0;
		bool bTire = false;
	};

	static constexpr int32 Capacity = 4096; // ~3 Runner x 2-3 Minuten
	TArray<FStep> Ring;
	int32 Head = 0;
};
