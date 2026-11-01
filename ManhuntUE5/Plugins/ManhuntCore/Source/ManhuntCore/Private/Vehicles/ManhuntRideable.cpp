#include "Vehicles/ManhuntRideable.h"
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntPlayerState.h"
#include "Components/StaticMeshComponent.h"
#include "Net/UnrealNetwork.h"
#include "Engine/World.h"

AManhuntRideable::AManhuntRideable()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.25f;
	bReplicates = true;
	SetReplicatingMovement(true); // Anhaengen an den Fahrer wird ueber AttachmentReplication synchronisiert

	VehicleMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("VehicleMesh"));
	VehicleMesh->SetCollisionProfileName(TEXT("BlockAll"));
	RootComponent = VehicleMesh;

	Config.DisplayName = NSLOCTEXT("Manhunt", "Vehicle", "Fahrzeug");
}

void AManhuntRideable::BeginPlay()
{
	Super::BeginPlay();
	BatterySeconds = GetConfig().BatteryCapacitySeconds;
	SetActorTickEnabled(HasAuthority() && GetConfig().bUsesBattery);
}

void AManhuntRideable::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AManhuntRideable, bLocked);
	DOREPLIFETIME(AManhuntRideable, Rider);
	DOREPLIFETIME(AManhuntRideable, BatterySeconds);
}

void AManhuntRideable::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// Akku leert sich nur bei Fahrt (Server).
	if (Rider && Rider->GetVelocity().SizeSquared2D() > FMath::Square(100.f))
	{
		BatterySeconds = FMath::Max(0.f, BatterySeconds - DeltaSeconds);
	}
}

float AManhuntRideable::GetBatteryRatio() const
{
	const FManhuntVehicleConfig& Cfg = GetConfig();
	return (Cfg.bUsesBattery && Cfg.BatteryCapacitySeconds > 0.f) ? BatterySeconds / Cfg.BatteryCapacitySeconds : 1.f;
}

// ---------------------------------------------------------------------------
// IManhuntMountableVehicle
// ---------------------------------------------------------------------------

bool AManhuntRideable::CanMount_Implementation(AManhuntCharacter* NewRider)
{
	const FManhuntVehicleConfig& Cfg = GetConfig();
	return NewRider && !Rider && !NewRider->GetMountedVehicle() && !NewRider->IsMovementLocked() && !NewRider->GetActiveQueue()
		&& (!Cfg.bUsesBattery || BatterySeconds > 1.f);
}

void AManhuntRideable::Mount_Implementation(AManhuntCharacter* NewRider)
{
	if (!HasAuthority() || !CanMount_Implementation(NewRider))
	{
		return;
	}
	const FManhuntVehicleConfig& Cfg = GetConfig();
	AManhuntPlayerState* PS = NewRider->GetManhuntPlayerState();

	// Hunter: Taskforce-Flatrate. Runner: per App bezahlen – oder unverschlossene Fahrzeuge klauen.
	const bool bFree = !bLocked || (NewRider->IsHunter() && Cfg.bFreeForHunters);
	if (!bFree)
	{
		if (!PS || !PS->SpendMoney(Cfg.UnlockPriceCents))
		{
			NewRider->ShowMessage(FText::Format(NSLOCTEXT("Manhunt", "NoMoney", "Freischalten kostet {0} - zu wenig Geld!"),
				FText::FromString(ManhuntMoney::Format(Cfg.UnlockPriceCents))));
			return;
		}
		NewRider->ShowMessage(FText::Format(NSLOCTEXT("Manhunt", "Unlocked", "{0} per App freigeschaltet (-{1})"),
			Cfg.DisplayName, FText::FromString(ManhuntMoney::Format(Cfg.UnlockPriceCents))));
	}

	NewRider->InterruptEverything();
	Rider = NewRider;
	AttachToActor(NewRider, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
	SetActorRelativeLocation(Cfg.MountOffset);
	SetActorRelativeRotation(Cfg.MountRotation);
	NewRider->SetMountedVehicle(this);
	OnRep_Rider();
}

void AManhuntRideable::Dismount_Implementation(AManhuntCharacter* OldRider)
{
	if (!HasAuthority() || !Rider || Rider != OldRider)
	{
		return;
	}
	DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);

	// Neben dem Fahrer auf den Boden stellen.
	const FVector Side = OldRider->GetActorLocation() + OldRider->GetActorRightVector() * 90.f;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(ManhuntDismount), false, this);
	Params.AddIgnoredActor(OldRider);
	FHitResult Hit;
	const bool bGround = GetWorld()->LineTraceSingleByChannel(Hit, Side + FVector(0.f, 0.f, 50.f), Side - FVector(0.f, 0.f, 400.f), ECC_Visibility, Params);
	SetActorLocationAndRotation(bGround ? Hit.ImpactPoint : Side, FRotator(0.f, OldRider->GetActorRotation().Yaw, 0.f));

	Rider = nullptr;
	OldRider->SetMountedVehicle(nullptr);
	OnRep_Rider();
}

void AManhuntRideable::OnRep_Rider()
{
	// Auf allen Rechnern gleich, sonst kollidiert die Kapsel des Fahrers mit dem Fahrzeug (Prediction).
	VehicleMesh->SetCollisionEnabled(Rider ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryAndPhysics);
	OnRiderChanged(Rider);
}

float AManhuntRideable::GetMaxSpeedOnSurface_Implementation(TEnumAsByte<EPhysicalSurface> Surface)
{
	const FManhuntVehicleConfig& Cfg = GetConfig();
	if (Cfg.bUsesBattery && BatterySeconds <= 0.f)
	{
		return 0.f; // Akku leer
	}
	const float* Multiplier = Cfg.SurfaceMultipliers.Find(Surface);
	constexpr float KmhToCmPerSecond = 100000.f / 3600.f;
	return Cfg.MaxSpeedKmh * KmhToCmPerSecond * (Multiplier ? *Multiplier : Cfg.DefaultSurfaceMultiplier);
}

float AManhuntRideable::GetRiderStaminaCostPerSecond_Implementation()
{
	return GetConfig().RiderStaminaPerSecond;
}

// ---------------------------------------------------------------------------
// IManhuntInteractable
// ---------------------------------------------------------------------------

bool AManhuntRideable::CanInteract_Implementation(AManhuntCharacter* Interactor)
{
	return CanMount_Implementation(Interactor);
}

void AManhuntRideable::Interact_Implementation(AManhuntCharacter* Interactor)
{
	IManhuntMountableVehicle::Execute_Mount(this, Interactor);
}

FText AManhuntRideable::GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor)
{
	const FManhuntVehicleConfig& Cfg = GetConfig();
	const bool bFree = !bLocked || (Interactor && Interactor->IsHunter() && Cfg.bFreeForHunters);
	return bFree
		? FText::Format(NSLOCTEXT("Manhunt", "Ride", "{0} fahren"), Cfg.DisplayName)
		: FText::Format(NSLOCTEXT("Manhunt", "RidePay", "{0} per App freischalten ({1})"), Cfg.DisplayName, FText::FromString(ManhuntMoney::Format(Cfg.UnlockPriceCents)));
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

AManhuntEScooter::AManhuntEScooter()
{
	Config.DisplayName = NSLOCTEXT("Manhunt", "EScooter", "E-Scooter");
	Config.MaxSpeedKmh = 30.f;
	Config.bUsesBattery = true;
	Config.BatteryCapacitySeconds = 300.f;
	Config.RiderStaminaPerSecond = 0.f;
	Config.UnlockPriceCents = 300;
	Config.SurfaceMultipliers.Add(SurfaceType1, 1.0f);  // Asphalt: volles Tempo
	Config.SurfaceMultipliers.Add(SurfaceType2, 0.5f);  // Kopfsteinpflaster: 15 km/h
	Config.SurfaceMultipliers.Add(SurfaceType3, 0.0f);  // Waldboden/Matsch: unbrauchbar
	Config.SurfaceMultipliers.Add(SurfaceType4, 0.5f);  // Schotter
	Config.SurfaceMultipliers.Add(SurfaceType5, 0.0f);  // Treppe: unbrauchbar
	Config.SurfaceMultipliers.Add(SurfaceType6, 0.25f); // Gras
}

AManhuntBike::AManhuntBike()
{
	Config.DisplayName = NSLOCTEXT("Manhunt", "Bike", "Fahrrad");
	Config.MaxSpeedKmh = 25.f;
	Config.bUsesBattery = false;
	Config.RiderStaminaPerSecond = 4.f;
	Config.UnlockPriceCents = 400;
	Config.SurfaceMultipliers.Add(SurfaceType1, 1.0f);  // Asphalt
	Config.SurfaceMultipliers.Add(SurfaceType2, 1.0f);  // Kopfsteinpflaster
	Config.SurfaceMultipliers.Add(SurfaceType3, 0.6f);  // Waldboden
	Config.SurfaceMultipliers.Add(SurfaceType4, 1.0f);  // Schotter / Forstweg: haelt das Tempo
	Config.SurfaceMultipliers.Add(SurfaceType5, 0.0f);  // Treppe
	Config.SurfaceMultipliers.Add(SurfaceType6, 0.8f);  // Gras
}
