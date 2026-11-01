#include "World/ManhuntDoor.h"
#include "Core/ManhuntGameState.h"
#include "Core/ManhuntCharacter.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"

AManhuntDoor::AManhuntDoor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false; // tickt nur waehrend der Animation
	bReplicates = false;                            // Zustand kommt aus dem GameState

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	DoorLeaf = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("DoorLeaf"));
	DoorLeaf->SetupAttachment(Root);
	DoorLeaf->SetCollisionProfileName(TEXT("BlockAll"));
}

uint64 AManhuntDoor::MakeDoorKey(const FVector& L)
{
	// 21 Bit pro Achse, 1-cm-Raster, Bereich +-10,4 km (die Map ist 1,5 x 1,5 km).
	auto Pack = [](double V) -> uint64
	{
		constexpr int64 Half = int64(1) << 20;
		const int64 I = FMath::Clamp<int64>(FMath::RoundToInt64(V), -Half, Half - 1);
		return static_cast<uint64>(I + Half) & 0x1FFFFFull;
	};
	return (Pack(L.X) << 42) | (Pack(L.Y) << 21) | Pack(L.Z);
}

void AManhuntDoor::BeginPlay()
{
	Super::BeginPlay();

	DoorKey = MakeDoorKey(GetActorLocation());
	CurrentState = DefaultState;
	CurrentYaw = (CurrentState == EManhuntDoorState::Open) ? OpenYaw : 0.f;
	DoorLeaf->SetRelativeRotation(FRotator(0.f, CurrentYaw, 0.f));

	if (AManhuntGameState* GS = GetWorld()->GetGameState<AManhuntGameState>())
	{
		GS->RegisterDoor(this);
	}
}

void AManhuntDoor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (UWorld* World = GetWorld())
	{
		if (AManhuntGameState* GS = World->GetGameState<AManhuntGameState>())
		{
			GS->UnregisterDoor(this);
		}
	}
	Super::EndPlay(EndPlayReason);
}

void AManhuntDoor::ApplyDoorState(EManhuntDoorState NewState)
{
	if (CurrentState == NewState)
	{
		return;
	}
	CurrentState = NewState;
	SetActorTickEnabled(true);
	OnDoorStateChanged(NewState);
}

void AManhuntDoor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	const float Target = (CurrentState == EManhuntDoorState::Open) ? OpenYaw : 0.f;
	CurrentYaw = FMath::FInterpConstantTo(CurrentYaw, Target, DeltaSeconds, OpenSpeed);
	DoorLeaf->SetRelativeRotation(FRotator(0.f, CurrentYaw, 0.f));

	if (FMath::IsNearlyEqual(CurrentYaw, Target, 0.1f))
	{
		SetActorTickEnabled(false);
	}
}

void AManhuntDoor::SetDoorStateServer(EManhuntDoorState NewState)
{
	if (!HasAuthority())
	{
		return;
	}
	if (AManhuntGameState* GS = GetWorld()->GetGameState<AManhuntGameState>())
	{
		GS->SetDoorState(DoorKey, NewState, DefaultState);
	}
	else
	{
		ApplyDoorState(NewState);
	}
}

bool AManhuntDoor::TryToggleLock(AManhuntCharacter* Interactor)
{
	if (!Interactor || !Interactor->IsRunner() || !bRunnerCanLock)
	{
		return false;
	}
	if (CurrentState == EManhuntDoorState::Closed)
	{
		SetDoorStateServer(EManhuntDoorState::Locked);
		return true;
	}
	if (CurrentState == EManhuntDoorState::Locked)
	{
		SetDoorStateServer(EManhuntDoorState::Closed);
		return true;
	}
	return false;
}

bool AManhuntDoor::CanInteract_Implementation(AManhuntCharacter* Interactor)
{
	return Interactor != nullptr;
}

void AManhuntDoor::Interact_Implementation(AManhuntCharacter* Interactor)
{
	if (!Interactor)
	{
		return;
	}

	switch (CurrentState)
	{
	case EManhuntDoorState::Closed:
		SetDoorStateServer(EManhuntDoorState::Open);
		break;

	case EManhuntDoorState::Open:
		SetDoorStateServer(EManhuntDoorState::Closed);
		break;

	case EManhuntDoorState::Locked:
		if (Interactor->IsRunner())
		{
			SetDoorStateServer(EManhuntDoorState::Closed); // von innen aufschliessen
		}
		else
		{
			// Hunter brechen verriegelte Tueren auf – kostet Zeit und macht Laerm.
			TWeakObjectPtr<AManhuntDoor> WeakThis(this);
			Interactor->StartTimedAction(2.5f, NSLOCTEXT("Manhunt", "Breach", "Tuer wird aufgebrochen ..."),
				[WeakThis]()
				{
					if (WeakThis.IsValid())
					{
						WeakThis->SetDoorStateServer(EManhuntDoorState::Open);
					}
				});
		}
		break;
	}
}

FText AManhuntDoor::GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor)
{
	switch (CurrentState)
	{
	case EManhuntDoorState::Open:
		return bIsWindow ? NSLOCTEXT("Manhunt", "WinClose", "Fenster schliessen") : NSLOCTEXT("Manhunt", "DoorClose", "Tuer schliessen");
	case EManhuntDoorState::Locked:
		return (Interactor && Interactor->IsRunner()) ? NSLOCTEXT("Manhunt", "Unlock", "Aufschliessen") : NSLOCTEXT("Manhunt", "BreachPrompt", "Aufbrechen");
	default:
		return bIsWindow ? NSLOCTEXT("Manhunt", "WinOpen", "Fenster oeffnen") : NSLOCTEXT("Manhunt", "DoorOpen", "Tuer oeffnen");
	}
}
