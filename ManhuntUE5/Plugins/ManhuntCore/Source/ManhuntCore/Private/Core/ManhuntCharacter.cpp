// Teil 1: Setup, Input, Stamina, Fokus, Fussspuren und Anti-Cheat-Relevanz.
// Teil 2 (Interaktion, Tackle/Struggle, Fahrzeuge, Items): ManhuntCharacterActions.cpp
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntCharacterMovement.h"
#include "Core/ManhuntPlayerState.h"
#include "Core/ManhuntGameMode.h"
#include "Hunters/ManhuntHackerComponent.h"
#include "Hunters/ManhuntTrackerComponent.h"
#include "Hunters/ManhuntTrackingSubsystem.h"
#include "Hunters/ManhuntCCTVCamera.h"
#include "Economy/ManhuntCheckout.h"
#include "Interfaces/ManhuntInteractable.h"
#include "Interfaces/ManhuntMountableVehicle.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/GameStateBase.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/WorldPartitionStreamingSourceComponent.h"
#include "Animation/AnimInstance.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "Net/UnrealNetwork.h"

AManhuntCharacter::AManhuntCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<UManhuntCharacterMovement>(ACharacter::CharacterMovementComponentName))
{
	PrimaryActorTick.bCanEverTick = true;

	GetCapsuleComponent()->InitCapsuleSize(42.f, 96.f);
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.f, 540.f, 0.f);
	Move->JumpZVelocity = 450.f;
	Move->AirControl = 0.3f;
	Move->BrakingDecelerationWalking = 2000.f;

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 320.f;
	CameraBoom->SocketOffset = FVector(0.f, 45.f, 55.f);
	CameraBoom->bUsePawnControlRotation = true;

	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;

	Hacker = CreateDefaultSubobject<UManhuntHackerComponent>(TEXT("Hacker"));
	Tracker = CreateDefaultSubobject<UManhuntTrackerComponent>(TEXT("Tracker"));

	StreamingSource = CreateDefaultSubobject<UWorldPartitionStreamingSourceComponent>(TEXT("StreamingSource"));
	StreamingSource->DisableStreamingSource(); // wird nur fuer die lokal gesteuerte Figur aktiviert

	// Standard-Ausrichtung fuer UE5-Mannequin-kompatible Fab-Charaktere.
	GetMesh()->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -96.f), FRotator(0.f, -90.f, 0.f));
}

void AManhuntCharacter::BeginPlay()
{
	Super::BeginPlay();
	ManhuntMovement = Cast<UManhuntCharacterMovement>(GetCharacterMovement());
	Stamina = ClassStats.MaxStamina;
	LastFootprintLocation = GetActorLocation();
	TryLoadFallbackMesh();
}

void AManhuntCharacter::TryLoadFallbackMesh()
{
	// Nur Entwicklungs-Komfort: Ohne zugewiesenes Fab-Mesh das UE5-Template-Mannequin
	// verwenden, falls es im Projekt existiert. Im BP_Runner/BP_Hunter einfach ueberschreiben.
	if (GetMesh()->GetSkeletalMeshAsset() != nullptr)
	{
		return;
	}
	static const TCHAR* MeshPaths[] = {
		TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"),
		TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny.SKM_Manny") };
	static const TCHAR* AnimPaths[] = {
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C"),
		TEXT("/Game/Characters/Mannequins/Animations/ABP_Manny.ABP_Manny_C") };

	for (const TCHAR* Path : MeshPaths)
	{
		if (USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet))
		{
			GetMesh()->SetSkeletalMeshAsset(Mesh);
			break;
		}
	}
	for (const TCHAR* Path : AnimPaths)
	{
		if (UClass* AnimClass = LoadClass<UAnimInstance>(nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet))
		{
			GetMesh()->SetAnimInstanceClass(AnimClass);
			break;
		}
	}
}

void AManhuntCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	if (const AManhuntGameMode* GM = GetWorld()->GetAuthGameMode<AManhuntGameMode>())
	{
		ApplyClassStats(GM->GetStatsFor(GetManhuntPlayerState()));
	}
}

void AManhuntCharacter::NotifyControllerChanged()
{
	Super::NotifyControllerChanged();
	if (StreamingSource)
	{
		if (IsLocallyControlled())
		{
			StreamingSource->EnableStreamingSource();
		}
		else
		{
			StreamingSource->DisableStreamingSource();
		}
	}
}

void AManhuntCharacter::ApplyClassStats(const FManhuntClassStats& NewStats)
{
	ClassStats = NewStats;
	Stamina = ServerStamina = ClassStats.MaxStamina;
	bExhausted = false;
}

void AManhuntCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AManhuntCharacter, ClassStats);
	DOREPLIFETIME(AManhuntCharacter, MovementLockFlags);
	DOREPLIFETIME_CONDITION(AManhuntCharacter, ServerStamina, COND_OwnerOnly);
	DOREPLIFETIME(AManhuntCharacter, MountedVehicle);
	DOREPLIFETIME_CONDITION(AManhuntCharacter, ActiveQueue, COND_OwnerOnly);
	DOREPLIFETIME(AManhuntCharacter, GrabbedBy);
	DOREPLIFETIME(AManhuntCharacter, GrabbedRunner);
	DOREPLIFETIME(AManhuntCharacter, StruggleProgress);
	DOREPLIFETIME_CONDITION(AManhuntCharacter, TimedActionEndTime, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(AManhuntCharacter, TimedActionDuration, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(AManhuntCharacter, TimedActionLabel, COND_OwnerOnly);
}

void AManhuntCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (IsLocallyControlled())
	{
		UpdateFocus();
		UpdateQueueAutoWalk();
	}
	if (HasAuthority())
	{
		TickServerChecks(DeltaSeconds);
		RecordFootprints();
		ServerStamina = Stamina;
	}
}

// ---------------------------------------------------------------------------
// Abfragen
// ---------------------------------------------------------------------------

AManhuntPlayerState* AManhuntCharacter::GetManhuntPlayerState() const
{
	return GetPlayerState<AManhuntPlayerState>();
}

EManhuntTeam AManhuntCharacter::GetTeam() const
{
	const AManhuntPlayerState* PS = GetManhuntPlayerState();
	return PS ? PS->GetTeam() : EManhuntTeam::None;
}

EHunterClass AManhuntCharacter::GetHunterClass() const
{
	const AManhuntPlayerState* PS = GetManhuntPlayerState();
	return PS ? PS->GetHunterClass() : EHunterClass::None;
}

float AManhuntCharacter::GetStaminaRatio() const
{
	return ClassStats.MaxStamina > 0.f ? Stamina / ClassStats.MaxStamina : 0.f;
}

bool AManhuntCharacter::CanSprint() const
{
	return !bExhausted && Stamina > 0.f && !MountedVehicle && !ActiveQueue && !IsMovementLocked()
		&& !(Tracker && Tracker->IsReadingTracks());
}

float AManhuntCharacter::GetSpeedMultiplier() const
{
	if (ActiveQueue)
	{
		return 0.45f; // in der Schlange schlurfen wie ein NPC
	}
	if (Tracker && Tracker->IsReadingTracks())
	{
		return 0.5f;  // Spur konzentriert am Boden lesen
	}
	return 1.f;
}

float AManhuntCharacter::GetTimedActionProgress() const
{
	const AGameStateBase* GS = GetWorld() ? GetWorld()->GetGameState() : nullptr;
	if (!GS || TimedActionDuration <= 0.f)
	{
		return 0.f;
	}
	const float Remaining = TimedActionEndTime - static_cast<float>(GS->GetServerWorldTimeSeconds());
	return Remaining > 0.f ? 1.f - FMath::Clamp(Remaining / TimedActionDuration, 0.f, 1.f) : 0.f;
}

float AManhuntCharacter::GetAudibleRadius() const
{
	// Klappernder Rucksack: nur beim Rennen hoerbar, lauter mit jeder Flasche.
	const AManhuntPlayerState* PS = GetManhuntPlayerState();
	const bool bRunning = GetVelocity().SizeSquared2D() > FMath::Square(ClassStats.WalkSpeed + 10.f);
	return BaseAudibleRadius + ((bRunning && PS) ? PS->GetBottleCount() * AudibleRadiusPerBottle : 0.f);
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

void AManhuntCharacter::InputMove(const FVector2D& Axis)
{
	if (!Controller || ActiveQueue)
	{
		return; // in der Kassenschlange laeuft die Figur automatisch
	}
	const FRotator YawRotation(0.f, Controller->GetControlRotation().Yaw, 0.f);
	AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::X), Axis.Y);
	AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y), Axis.X);
}

void AManhuntCharacter::InputLook(const FVector2D& Axis)
{
	AddControllerYawInput(Axis.X);
	AddControllerPitchInput(-Axis.Y);
}

void AManhuntCharacter::InputJump()
{
	if (GrabbedBy)
	{
		Server_StruggleInput(); // Losreissen: Leertaste haemmern
		return;
	}
	Jump();
}

void AManhuntCharacter::InputStopJump()
{
	StopJumping();
}

void AManhuntCharacter::InputSprint(bool bPressed)
{
	if (ManhuntMovement)
	{
		ManhuntMovement->bWantsToSprint = bPressed;
	}
}

void AManhuntCharacter::InputInteract()
{
	if (GrabbedBy)
	{
		Server_StruggleInput();
		return;
	}
	Server_Interact();
}

void AManhuntCharacter::InputAbility()
{
	if (IsRunner())
	{
		Server_RunnerAbility(); // Tuer verriegeln/entriegeln
		return;
	}
	switch (GetHunterClass())
	{
	case EHunterClass::Hacker:  if (Hacker)  { Hacker->RequestToggleCCTV(); }  break;
	case EHunterClass::Tracker: if (Tracker) { Tracker->RequestActivate(); }   break;
	default: break; // Kampfsportler: rein passive Staerken
	}
}

void AManhuntCharacter::InputTackle()
{
	if (GrabbedBy)
	{
		Server_StruggleInput();
		return;
	}
	if (IsHunter())
	{
		Server_Tackle();
	}
}

void AManhuntCharacter::InputCycleCamera(int32 Direction)
{
	if (Hacker && Hacker->IsViewingCCTV())
	{
		Hacker->RequestCycleCamera(Direction);
	}
}

void AManhuntCharacter::InputUseItem(EManhuntItem Item)
{
	Server_UseItem(Item);
}

// ---------------------------------------------------------------------------
// Stamina (laeuft deterministisch in der Movement-Komponente)
// ---------------------------------------------------------------------------

void AManhuntCharacter::SimulateStamina(float DeltaSeconds, bool bSprinting)
{
	float Drain = 0.f;
	if (bSprinting)
	{
		Drain = ClassStats.SprintStaminaPerSecond;
	}
	else if (MountedVehicle && CachedVehicleStaminaCost > 0.f && GetVelocity().SizeSquared2D() > FMath::Square(250.f))
	{
		Drain = CachedVehicleStaminaCost; // Fahrrad: schnelles Treten
	}

	if (Drain > 0.f)
	{
		Stamina = FMath::Max(0.f, Stamina - Drain * DeltaSeconds);
	}
	else if (!GrabbedBy)
	{
		Stamina = FMath::Min(ClassStats.MaxStamina, Stamina + ClassStats.StaminaRegenPerSecond * DeltaSeconds);
	}

	if (Stamina <= 0.f)
	{
		bExhausted = true;
	}
	else if (bExhausted && Stamina >= ClassStats.MaxStamina * 0.15f)
	{
		bExhausted = false;
	}
}

void AManhuntCharacter::OnRep_ServerStamina()
{
	// Nur bei echtem Auseinanderlaufen korrigieren (z.B. Energy-Drink, Struggle).
	if (FMath::Abs(ServerStamina - Stamina) > 5.f)
	{
		Stamina = ServerStamina;
	}
}

void AManhuntCharacter::AddStamina(float Amount)
{
	Stamina = FMath::Clamp(Stamina + Amount, 0.f, ClassStats.MaxStamina);
	ServerStamina = Stamina;
	if (Stamina > ClassStats.MaxStamina * 0.15f)
	{
		bExhausted = false;
	}
}

// ---------------------------------------------------------------------------
// Fokus, Kassenschlange, Fussspuren
// ---------------------------------------------------------------------------

AActor* AManhuntCharacter::FindInteractable(const FVector& ViewLocation, const FRotator& ViewRotation) const
{
	FCollisionQueryParams Params(SCENE_QUERY_STAT(ManhuntInteract), false, this);
	if (MountedVehicle)
	{
		Params.AddIgnoredActor(MountedVehicle);
	}
	const FVector End = ViewLocation + ViewRotation.Vector() * InteractRange;

	FHitResult Hit;
	if (GetWorld()->SweepSingleByChannel(Hit, ViewLocation, End, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(20.f), Params))
	{
		AActor* HitActor = Hit.GetActor();
		if (HitActor && HitActor->Implements<UManhuntInteractable>())
		{
			return HitActor;
		}
	}
	return nullptr;
}

void AManhuntCharacter::UpdateFocus()
{
	FocusPrompt = FText::GetEmpty();
	FocusedActor = nullptr;

	if (GrabbedBy)
	{
		FocusPrompt = NSLOCTEXT("Manhunt", "Struggle", "LOSREISSEN! [Leertaste] haemmern");
		return;
	}
	if (MountedVehicle)
	{
		FocusPrompt = NSLOCTEXT("Manhunt", "Dismount", "Absteigen");
		return;
	}
	if (ActiveQueue)
	{
		FocusPrompt = NSLOCTEXT("Manhunt", "LeaveQueue", "Schlange verlassen");
		return;
	}

	AActor* Target = FindInteractable(GetPawnViewLocation(), GetControlRotation());
	if (Target && IManhuntInteractable::Execute_CanInteract(Target, this))
	{
		FocusedActor = Target;
		FocusPrompt = IManhuntInteractable::Execute_GetInteractionPrompt(Target, this);
	}
}

void AManhuntCharacter::UpdateQueueAutoWalk()
{
	if (!ActiveQueue)
	{
		return;
	}
	FVector Target;
	if (ActiveQueue->GetSlotLocationFor(this, Target))
	{
		FVector Delta = Target - GetActorLocation();
		Delta.Z = 0.f;
		if (Delta.SizeSquared() > FMath::Square(15.f))
		{
			AddMovementInput(Delta.GetSafeNormal(), 1.f);
		}
	}
}

void AManhuntCharacter::RecordFootprints()
{
	if (!IsRunner() || !GetCharacterMovement()->IsMovingOnGround())
	{
		return;
	}
	const FVector Location = GetActorLocation();
	const float StepLength = MountedVehicle ? 160.f : 110.f;
	if (FVector::DistSquared2D(Location, LastFootprintLocation) < FMath::Square(StepLength))
	{
		return;
	}
	LastFootprintLocation = Location;

	FVector Ground = Location - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	if (!MountedVehicle)
	{
		bLeftFoot = !bLeftFoot;
		Ground += GetActorRightVector() * (bLeftFoot ? -12.f : 12.f);
	}

	if (UManhuntTrackingSubsystem* Tracking = GetWorld()->GetSubsystem<UManhuntTrackingSubsystem>())
	{
		Tracking->RecordStep(Ground, GetVelocity().Rotation().Yaw, MountedVehicle != nullptr);
	}
}

// ---------------------------------------------------------------------------
// Anti-Cheat: Runner-Positionen nur bei Sichtkontakt / Hacker-Kamera / Hoerweite
// ---------------------------------------------------------------------------

bool AManhuntCharacter::HasLineOfSightFrom(const FVector& From, const AActor* IgnoredViewer) const
{
	FCollisionQueryParams Params(SCENE_QUERY_STAT(ManhuntRelevancyLOS), false, this);
	Params.AddIgnoredActor(IgnoredViewer);
	if (MountedVehicle)
	{
		Params.AddIgnoredActor(MountedVehicle);
	}

	const FVector Targets[] = { GetPawnViewLocation(), GetActorLocation() };
	for (const FVector& To : Targets)
	{
		FHitResult Hit;
		if (!GetWorld()->LineTraceSingleByChannel(Hit, From, To, ECC_Visibility, Params))
		{
			return true;
		}
	}
	return false;
}

bool AManhuntCharacter::IsNetRelevantFor(const AActor* RealViewer, const AActor* ViewTarget, const FVector& SrcLocation) const
{
	const APlayerController* ViewerPC = Cast<APlayerController>(RealViewer);
	const AManhuntPlayerState* ViewerPS = ViewerPC ? ViewerPC->GetPlayerState<AManhuntPlayerState>() : nullptr;

	// Gilt nur: Runner-Figur -> Hunter-Client. Alles andere normal.
	if (!IsRunner() || !ViewerPS || ViewerPS->GetTeam() != EManhuntTeam::Hunter || IsOwnedBy(RealViewer))
	{
		return Super::IsNetRelevantFor(RealViewer, ViewTarget, SrcLocation);
	}

	const AManhuntCharacter* ViewerChar = Cast<AManhuntCharacter>(ViewerPC->GetPawn());
	if (ViewerChar && (GrabbedBy.Get() == ViewerChar || ViewerChar->GetGrabbedRunner() == this))
	{
		return true;
	}

	const FVector MyLocation = GetActorLocation();
	const FVector ViewerLocation = ViewerChar ? ViewerChar->GetActorLocation() : SrcLocation;

	// 1) In Hoerweite (Schritte, klappernde Pfandflaschen)
	if (FVector::DistSquared(MyLocation, ViewerLocation) < FMath::Square(GetAudibleRadius()))
	{
		return true;
	}

	// 2) Direkter Sichtkontakt
	if (ViewerChar && FVector::DistSquared(MyLocation, ViewerLocation) < FMath::Square(MaxSightDistance)
		&& HasLineOfSightFrom(ViewerChar->GetPawnViewLocation(), ViewerChar))
	{
		return true;
	}

	// 3) Aktive Hacker-Ueberwachungskamera
	if (ViewerChar && ViewerChar->Hacker)
	{
		if (const AManhuntCCTVCamera* Cam = ViewerChar->Hacker->GetActiveCamera())
		{
			const FVector CamLocation = Cam->GetViewLocation();
			if (FVector::DistSquared(MyLocation, CamLocation) < FMath::Square(Cam->ViewDistance)
				&& HasLineOfSightFrom(CamLocation, Cam))
			{
				return true;
			}
		}
	}
	return false;
}
