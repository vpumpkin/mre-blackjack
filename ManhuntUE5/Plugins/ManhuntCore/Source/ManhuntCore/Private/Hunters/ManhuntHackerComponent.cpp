#include "Hunters/ManhuntHackerComponent.h"
#include "Hunters/ManhuntCCTVCamera.h"
#include "Core/ManhuntCharacter.h"
#include "GameFramework/PlayerController.h"
#include "Net/UnrealNetwork.h"
#include "EngineUtils.h"

UManhuntHackerComponent::UManhuntHackerComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);
}

void UManhuntHackerComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UManhuntHackerComponent, ActiveCamera); // alle: fuer die "Handy-Animation"
}

AManhuntCharacter* UManhuntHackerComponent::GetCharacter() const
{
	return Cast<AManhuntCharacter>(GetOwner());
}

void UManhuntHackerComponent::RequestToggleCCTV()
{
	Server_ToggleCCTV();
}

void UManhuntHackerComponent::RequestCycleCamera(int32 Direction)
{
	Server_CycleCamera(Direction);
}

void UManhuntHackerComponent::GatherCameras(TArray<AManhuntCCTVCamera*>& OutCameras) const
{
	for (TActorIterator<AManhuntCCTVCamera> It(GetWorld()); It; ++It)
	{
		OutCameras.Add(*It);
	}
	// Stabile Reihenfolge fuers Durchschalten
	OutCameras.Sort([](const AManhuntCCTVCamera& A, const AManhuntCCTVCamera& B) { return A.GetName() < B.GetName(); });
}

void UManhuntHackerComponent::Server_ToggleCCTV_Implementation()
{
	AManhuntCharacter* Char = GetCharacter();
	if (!Char || Char->GetHunterClass() != EHunterClass::Hacker)
	{
		return;
	}
	if (ActiveCamera)
	{
		SetActiveCamera(nullptr);
		return;
	}
	if (Char->IsMovementLocked() || Char->GetMountedVehicle())
	{
		return;
	}

	TArray<AManhuntCCTVCamera*> Cameras;
	GatherCameras(Cameras);
	if (Cameras.Num() == 0)
	{
		Char->ShowMessage(NSLOCTEXT("Manhunt", "NoCams", "Keine Ueberwachungskameras erreichbar."));
		return;
	}

	// Mit der naechstgelegenen Kamera starten.
	AManhuntCCTVCamera* Nearest = Cameras[0];
	float BestDistSq = TNumericLimits<float>::Max();
	for (AManhuntCCTVCamera* Cam : Cameras)
	{
		const float DistSq = FVector::DistSquared(Cam->GetActorLocation(), Char->GetActorLocation());
		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			Nearest = Cam;
		}
	}
	SetActiveCamera(Nearest);
}

void UManhuntHackerComponent::Server_CycleCamera_Implementation(int32 Direction)
{
	if (!ActiveCamera)
	{
		return;
	}
	TArray<AManhuntCCTVCamera*> Cameras;
	GatherCameras(Cameras);
	if (Cameras.Num() == 0)
	{
		SetActiveCamera(nullptr);
		return;
	}
	const int32 Current = FMath::Max(0, Cameras.IndexOfByKey(ActiveCamera.Get()));
	const int32 Next = (Current + (Direction >= 0 ? 1 : -1) + Cameras.Num()) % Cameras.Num();
	SetActiveCamera(Cameras[Next]);
}

void UManhuntHackerComponent::StopViewing()
{
	if (ActiveCamera && GetOwner() && GetOwner()->HasAuthority())
	{
		SetActiveCamera(nullptr);
	}
}

void UManhuntHackerComponent::SetActiveCamera(AManhuntCCTVCamera* NewCamera)
{
	AManhuntCharacter* Char = GetCharacter();
	if (!Char)
	{
		return;
	}
	ActiveCamera = NewCamera;

	// Trade-off: Bewegungssperre, solange er auf das Kamerabild schaut.
	Char->SetMovementLock(EManhuntLock::CCTV, NewCamera != nullptr);

	// Server setzt das ViewTarget; der Client bekommt es automatisch per ClientSetViewTarget.
	if (APlayerController* PC = Cast<APlayerController>(Char->GetController()))
	{
		PC->SetViewTargetWithBlend(NewCamera ? static_cast<AActor*>(NewCamera) : static_cast<AActor*>(Char), 0.2f);
	}
	OnRep_ActiveCamera(); // Listen-Server
}

void UManhuntHackerComponent::OnRep_ActiveCamera()
{
	const AManhuntCharacter* Char = GetCharacter();
	const bool bLocal = Char && Char->IsLocallyControlled();

	AManhuntCCTVCamera* Previous = LocallyViewedCamera.Get();
	if (Previous && Previous != ActiveCamera)
	{
		Previous->SetLocallyViewed(false);
	}
	if (bLocal && ActiveCamera)
	{
		ActiveCamera->SetLocallyViewed(true); // World Partition streamt die Umgebung der Kamera
	}
	LocallyViewedCamera = bLocal ? ActiveCamera.Get() : nullptr;
}

void UManhuntHackerComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (AManhuntCCTVCamera* Previous = LocallyViewedCamera.Get())
	{
		Previous->SetLocallyViewed(false);
	}
	Super::EndPlay(EndPlayReason);
}
