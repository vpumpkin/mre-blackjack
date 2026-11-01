#include "Hunters/ManhuntCCTVCamera.h"
#include "Components/StaticMeshComponent.h"
#include "Components/WorldPartitionStreamingSourceComponent.h"

AManhuntCCTVCamera::AManhuntCCTVCamera()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false; // tickt nur, solange ein lokaler Hacker zuschaut
	bReplicates = false;                            // statisch platziert, per Name netzwerk-adressierbar

#if WITH_EDITORONLY_DATA
	bIsSpatiallyLoaded = false; // World Partition: immer geladen, damit der Hacker jede Kamera erreicht
#endif

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Root);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);
	Camera->SetFieldOfView(80.f);

	StreamingSource = CreateDefaultSubobject<UWorldPartitionStreamingSourceComponent>(TEXT("StreamingSource"));
	StreamingSource->DisableStreamingSource();
}

void AManhuntCCTVCamera::BeginPlay()
{
	Super::BeginPlay();
	BaseRotation = Camera->GetRelativeRotation();
}

void AManhuntCCTVCamera::SetLocallyViewed(bool bViewed)
{
	if (bViewed)
	{
		StreamingSource->EnableStreamingSource();
	}
	else
	{
		StreamingSource->DisableStreamingSource();
		Camera->SetRelativeRotation(BaseRotation);
	}
	SetActorTickEnabled(bViewed && SweepAngle > 0.f && SweepSpeed > 0.f);
}

void AManhuntCCTVCamera::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	SweepTime += DeltaSeconds;
	const float Yaw = SweepAngle * FMath::Sin(SweepTime * SweepSpeed * 2.f * PI);
	Camera->SetRelativeRotation(BaseRotation + FRotator(0.f, Yaw, 0.f));
}
