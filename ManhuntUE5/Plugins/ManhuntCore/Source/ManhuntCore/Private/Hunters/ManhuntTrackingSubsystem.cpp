#include "Hunters/ManhuntTrackingSubsystem.h"
#include "Engine/World.h"

bool UManhuntTrackingSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UManhuntTrackingSubsystem::RecordStep(const FVector& Location, float Yaw, bool bTireTrack)
{
	if (Ring.Num() < Capacity)
	{
		Ring.AddDefaulted(Capacity - Ring.Num());
	}
	FStep& Step = Ring[Head];
	Step.Location = Location;
	Step.Yaw = Yaw;
	Step.Time = GetWorld()->GetTimeSeconds();
	Step.bTire = bTireTrack;
	Head = (Head + 1) % Capacity;
}

void UManhuntTrackingSubsystem::GatherFootprints(const FVector& Center, float Radius, float MaxAge, int32 MaxCount, TArray<FManhuntFootprint>& OutPrints) const
{
	const double Now = GetWorld()->GetTimeSeconds();
	const float RadiusSq = Radius * Radius;

	for (const FStep& Step : Ring)
	{
		if (Step.Time < 0.0)
		{
			continue;
		}
		const float Age = static_cast<float>(Now - Step.Time);
		if (Age > MaxAge || FVector::DistSquared2D(Step.Location, Center) > RadiusSq)
		{
			continue;
		}
		FManhuntFootprint& Print = OutPrints.AddDefaulted_GetRef();
		Print.Location = Step.Location;
		Print.Yaw = Step.Yaw;
		Print.Age = Age;
		Print.bTireTrack = Step.bTire;
	}

	OutPrints.Sort([](const FManhuntFootprint& A, const FManhuntFootprint& B) { return A.Age < B.Age; });
	if (OutPrints.Num() > MaxCount)
	{
		OutPrints.SetNum(MaxCount);
	}
}
