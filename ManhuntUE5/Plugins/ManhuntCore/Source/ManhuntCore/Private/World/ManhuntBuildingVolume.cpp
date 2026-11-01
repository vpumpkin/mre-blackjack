#include "World/ManhuntBuildingVolume.h"
#include "Core/ManhuntCharacter.h"
#include "Components/BoxComponent.h"

AManhuntBuildingVolume::AManhuntBuildingVolume()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = false; // nur der Server braucht es (Ping-Berechnung)

	Box = CreateDefaultSubobject<UBoxComponent>(TEXT("Box"));
	Box->InitBoxExtent(FVector(1000.f, 1000.f, 1500.f));
	Box->SetCollisionProfileName(TEXT("Trigger"));
	Box->SetGenerateOverlapEvents(true);
	Box->SetHiddenInGame(true);
	RootComponent = Box;
}

void AManhuntBuildingVolume::BeginPlay()
{
	Super::BeginPlay();
	if (HasAuthority())
	{
		Box->OnComponentBeginOverlap.AddDynamic(this, &AManhuntBuildingVolume::OnBeginOverlap);
		Box->OnComponentEndOverlap.AddDynamic(this, &AManhuntBuildingVolume::OnEndOverlap);
	}
}

FVector2D AManhuntBuildingVolume::GetFootprintExtent() const
{
	const FVector Extent = Box->Bounds.BoxExtent;
	return FVector2D(Extent.X, Extent.Y);
}

void AManhuntBuildingVolume::OnBeginOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor, UPrimitiveComponent* OtherComp,
	int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (AManhuntCharacter* Char = Cast<AManhuntCharacter>(OtherActor))
	{
		Char->SetCurrentBuilding(this);
	}
}

void AManhuntBuildingVolume::OnEndOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex)
{
	AManhuntCharacter* Char = Cast<AManhuntCharacter>(OtherActor);
	if (!Char || Char->GetCurrentBuilding() != this)
	{
		return;
	}
	// Steht er noch in einem angrenzenden Gebaeude?
	TArray<AActor*> Others;
	Char->GetOverlappingActors(Others, AManhuntBuildingVolume::StaticClass());
	Others.Remove(this);
	Char->SetCurrentBuilding(Others.Num() > 0 ? Cast<AManhuntBuildingVolume>(Others[0]) : nullptr);
}
