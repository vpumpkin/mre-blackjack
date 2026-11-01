#include "World/ManhuntExtractionPoint.h"
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntGameMode.h"
#include "Core/ManhuntPlayerState.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

AManhuntExtractionPoint::AManhuntExtractionPoint()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	bAlwaysRelevant = true; // alle Runner sollen aktive Punkte kennen

#if WITH_EDITORONLY_DATA
	bIsSpatiallyLoaded = false; // World Partition: immer geladen
#endif

	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	Trigger->InitSphereRadius(600.f);
	Trigger->SetCollisionProfileName(TEXT("Trigger"));
	RootComponent = Trigger;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Trigger);
}

void AManhuntExtractionPoint::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AManhuntExtractionPoint, bActive);
}

void AManhuntExtractionPoint::SetExtractionActive(bool bNewActive)
{
	if (!HasAuthority() || bActive == bNewActive)
	{
		return;
	}
	bActive = bNewActive;
	RunnersInside.Reset();
	if (bActive)
	{
		GetWorldTimerManager().SetTimer(CheckTimer, this, &AManhuntExtractionPoint::CheckRunners, 0.25f, true);
	}
	else
	{
		GetWorldTimerManager().ClearTimer(CheckTimer);
	}
	OnRep_Active();
}

void AManhuntExtractionPoint::OnRep_Active()
{
	OnActiveChanged(bActive);
}

void AManhuntExtractionPoint::CheckRunners()
{
	const float Now = GetWorld()->GetTimeSeconds();

	TArray<AActor*> Overlapping;
	Trigger->GetOverlappingActors(Overlapping, AManhuntCharacter::StaticClass());

	TSet<TWeakObjectPtr<AManhuntCharacter>> StillInside;
	for (AActor* Actor : Overlapping)
	{
		AManhuntCharacter* Char = Cast<AManhuntCharacter>(Actor);
		const AManhuntPlayerState* PS = Char ? Char->GetManhuntPlayerState() : nullptr;
		if (!PS || !PS->IsFreeRunner() || Char->GetGrabbedBy())
		{
			continue;
		}
		StillInside.Add(Char);
		const float* EnterTime = RunnersInside.Find(Char);
		if (!EnterTime)
		{
			RunnersInside.Add(Char, Now);
			Char->ShowMessage(FText::Format(NSLOCTEXT("Manhunt", "Extracting", "Extraktion laeuft - {0} s halten!"), FText::AsNumber(FMath::CeilToInt(ExtractionHoldTime))));
		}
		else if (Now - *EnterTime >= ExtractionHoldTime)
		{
			if (AManhuntGameMode* GM = GetWorld()->GetAuthGameMode<AManhuntGameMode>())
			{
				GM->HandleRunnerExtracted(Char, this);
			}
		}
	}

	for (auto It = RunnersInside.CreateIterator(); It; ++It)
	{
		if (!StillInside.Contains(It.Key()))
		{
			It.RemoveCurrent();
		}
	}
}
