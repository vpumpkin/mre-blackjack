#include "Hunters/ManhuntTrackerComponent.h"
#include "Hunters/ManhuntTrackingSubsystem.h"
#include "Core/ManhuntCharacter.h"
#include "Components/DecalComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/GameStateBase.h"
#include "DrawDebugHelpers.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

UManhuntTrackerComponent::UManhuntTrackerComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false; // nur waehrend Spuren sichtbar sind
	SetIsReplicatedByDefault(true);
}

void UManhuntTrackerComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UManhuntTrackerComponent, bReadingTracks); // alle: "knien und lesen"-Animation
	DOREPLIFETIME_CONDITION(UManhuntTrackerComponent, CooldownEndServerTime, COND_OwnerOnly);
}

float UManhuntTrackerComponent::GetCooldownRemaining() const
{
	const AGameStateBase* GS = GetWorld() ? GetWorld()->GetGameState() : nullptr;
	return GS ? FMath::Max(0.f, CooldownEndServerTime - static_cast<float>(GS->GetServerWorldTimeSeconds())) : 0.f;
}

void UManhuntTrackerComponent::RequestActivate()
{
	Server_Activate();
}

void UManhuntTrackerComponent::Server_Activate_Implementation()
{
	AManhuntCharacter* Char = Cast<AManhuntCharacter>(GetOwner());
	if (!Char || Char->GetHunterClass() != EHunterClass::Tracker || bReadingTracks)
	{
		return;
	}
	if (GetCooldownRemaining() > 0.f || Char->IsMovementLocked() || Char->GetMountedVehicle())
	{
		return;
	}

	const FManhuntClassStats& Stats = Char->GetClassStats();
	const float Duration = Stats.AbilityDuration > 0.f ? Stats.AbilityDuration : 12.f;
	const float Cooldown = Stats.AbilityCooldown > 0.f ? Stats.AbilityCooldown : 45.f;
	const AGameStateBase* GS = GetWorld()->GetGameState();
	const float Now = GS ? static_cast<float>(GS->GetServerWorldTimeSeconds()) : GetWorld()->GetTimeSeconds();

	bReadingTracks = true;
	CooldownEndServerTime = Now + Duration + Cooldown; // Cooldown laeuft nach dem Lesen

	FTimerManager& Timers = GetWorld()->GetTimerManager();
	Timers.SetTimer(ReadingTimer, this, &UManhuntTrackerComponent::EndReading, Duration, false);
	Timers.SetTimer(RefreshTimer, this, &UManhuntTrackerComponent::SendFootprints, RefreshInterval, true);
	SendFootprints();
}

void UManhuntTrackerComponent::SendFootprints()
{
	const AActor* Owner = GetOwner();
	UManhuntTrackingSubsystem* Tracking = GetWorld()->GetSubsystem<UManhuntTrackingSubsystem>();
	if (!Owner || !Tracking)
	{
		return;
	}
	TArray<FManhuntFootprint> Prints;
	Tracking->GatherFootprints(Owner->GetActorLocation(), RevealRadius, MaxTrackAge, MaxFootprintsPerReveal, Prints);
	Client_RevealFootprints(Prints); // nur der Faehrtenleser selbst bekommt die Daten
}

void UManhuntTrackerComponent::EndReading()
{
	bReadingTracks = false;
	GetWorld()->GetTimerManager().ClearTimer(RefreshTimer);
}

void UManhuntTrackerComponent::Client_RevealFootprints_Implementation(const TArray<FManhuntFootprint>& Prints)
{
	ClearShown();
	NewestAge = -1.f;

	for (const FManhuntFootprint& Print : Prints)
	{
		FShownPrint& Entry = Shown.AddDefaulted_GetRef();
		Entry.Location = Print.Location;
		Entry.Yaw = Print.Yaw;
		Entry.Age = Print.Age;
		Entry.bTire = Print.bTireTrack;

		UMaterialInterface* Material = Print.bTireTrack ? TireTrackDecalMaterial : FootprintDecalMaterial;
		if (Material)
		{
			// Decals projizieren entlang X -> Pitch -90 = senkrecht auf den Boden.
			UDecalComponent* Decal = UGameplayStatics::SpawnDecalAtLocation(this, Material,
				Print.bTireTrack ? TireDecalSize : FootprintDecalSize, Print.Location, FRotator(-90.f, Print.Yaw, 0.f), 0.f);
			if (Decal)
			{
				Entry.Decal = Decal;
				Entry.MID = Decal->CreateDynamicMaterialInstance();
			}
		}
		NewestAge = NewestAge < 0.f ? Print.Age : FMath::Min(NewestAge, Print.Age);
	}

	ShowTimeRemaining = RefreshInterval + 2.f;
	SetComponentTickEnabled(Shown.Num() > 0);
	OnTracksRevealed.Broadcast(Prints.Num(), NewestAge);
}

void UManhuntTrackerComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	ShowTimeRemaining -= DeltaTime;
	if (ShowTimeRemaining <= 0.f)
	{
		ClearShown();
		return;
	}
	if (NewestAge >= 0.f)
	{
		NewestAge += DeltaTime;
	}

	const float FadeOut = FMath::Clamp(ShowTimeRemaining, 0.f, 1.f);
	for (FShownPrint& Entry : Shown)
	{
		Entry.Age += DeltaTime;
		const float Freshness = 1.f - FMath::Clamp(Entry.Age / MaxTrackAge, 0.f, 1.f);
		const FLinearColor Color = FLinearColor::LerpUsingHSV(OldColor, FreshColor, Freshness);

		if (UMaterialInstanceDynamic* MID = Entry.MID.Get())
		{
			MID->SetScalarParameterValue(TEXT("Opacity"), Freshness * FadeOut);
			MID->SetVectorParameterValue(TEXT("Color"), Color);
		}
		else if (!Entry.Decal.IsValid())
		{
			// Fallback ohne Decal-Material (Entwicklung): farbige Debug-Pfeile.
			const FVector Dir = FRotator(0.f, Entry.Yaw, 0.f).Vector();
			DrawDebugDirectionalArrow(GetWorld(), Entry.Location + FVector(0.f, 0.f, 3.f), Entry.Location + FVector(0.f, 0.f, 3.f) + Dir * (Entry.bTire ? 40.f : 18.f),
				12.f, Color.ToFColor(true), false, -1.f, 0, 2.f);
		}
	}
}

void UManhuntTrackerComponent::ClearShown()
{
	for (FShownPrint& Entry : Shown)
	{
		if (UDecalComponent* Decal = Entry.Decal.Get())
		{
			Decal->DestroyComponent();
		}
	}
	Shown.Reset();
	SetComponentTickEnabled(false);
}

void UManhuntTrackerComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	ClearShown();
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(ReadingTimer);
		World->GetTimerManager().ClearTimer(RefreshTimer);
	}
	Super::EndPlay(EndPlayReason);
}
