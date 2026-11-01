// Teil 2: serverautoritative Aktionen – Interaktion, Tackle & Struggle,
// Zeitaktionen, Fahrzeuge und Items.
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntPlayerState.h"
#include "Core/ManhuntPlayerController.h"
#include "Core/ManhuntGameMode.h"
#include "Hunters/ManhuntHackerComponent.h"
#include "World/ManhuntDoor.h"
#include "Interfaces/ManhuntInteractable.h"
#include "Interfaces/ManhuntMountableVehicle.h"
#include "GameFramework/GameStateBase.h"
#include "EngineUtils.h"
#include "TimerManager.h"

// ---------------------------------------------------------------------------
// Allgemein
// ---------------------------------------------------------------------------

void AManhuntCharacter::SetMovementLock(uint8 Flag, bool bLocked)
{
	if (bLocked)
	{
		MovementLockFlags |= Flag;
	}
	else
	{
		MovementLockFlags &= static_cast<uint8>(~Flag);
	}
}

bool AManhuntCharacter::CanJumpInternal_Implementation() const
{
	return !IsMovementLocked() && !MountedVehicle && !ActiveQueue && Super::CanJumpInternal_Implementation();
}

void AManhuntCharacter::ShowMessage(const FText& Message)
{
	if (AManhuntPlayerController* PC = Cast<AManhuntPlayerController>(GetController()))
	{
		PC->Client_ShowMessage(Message);
	}
}

void AManhuntCharacter::ClearCurrentInteraction(AActor* Interactable)
{
	if (CurrentInteraction.Get() == Interactable)
	{
		CurrentInteraction = nullptr;
	}
}

void AManhuntCharacter::InterruptEverything()
{
	CancelTimedAction();

	if (AActor* Current = CurrentInteraction.Get())
	{
		CurrentInteraction = nullptr;
		IManhuntInteractable::Execute_CancelInteraction(Current, this);
	}
	ActiveQueue = nullptr;

	if (MountedVehicle)
	{
		IManhuntMountableVehicle::Execute_Dismount(MountedVehicle, this);
	}
	if (Hacker)
	{
		Hacker->StopViewing();
	}
}

void AManhuntCharacter::TickServerChecks(float DeltaSeconds)
{
	// Fahrzeug auf unbrauchbarem Untergrund (Treppe, Matsch) oder leerer Akku -> absteigen.
	if (MountedVehicle && CachedVehicleSpeed <= 1.f)
	{
		UnusableSurfaceTime += DeltaSeconds;
		if (UnusableSurfaceTime > 0.75f)
		{
			UnusableSurfaceTime = 0.f;
			ShowMessage(NSLOCTEXT("Manhunt", "VehicleUnusable", "Fahrzeug hier unbrauchbar (Untergrund/Akku) - abgestiegen"));
			IManhuntMountableVehicle::Execute_Dismount(MountedVehicle, this);
		}
	}
	else
	{
		UnusableSurfaceTime = 0.f;
	}
}

// ---------------------------------------------------------------------------
// Interaktion
// ---------------------------------------------------------------------------

void AManhuntCharacter::Server_Interact_Implementation()
{
	if (MovementLockFlags & (EManhuntLock::Grabbed | EManhuntLock::Caught))
	{
		return;
	}
	// Laufende Interaktion (Pfandautomat, Kassenschlange): erneutes [E] beendet sie.
	if (AActor* Current = CurrentInteraction.Get())
	{
		IManhuntInteractable::Execute_Interact(Current, this);
		return;
	}
	if (MountedVehicle)
	{
		IManhuntMountableVehicle::Execute_Dismount(MountedVehicle, this);
		return;
	}
	if (IsBusy() || (Hacker && Hacker->IsViewingCCTV()))
	{
		return;
	}

	// Serverseitiger Trace – der Client schickt KEIN Ziel (Anti-Cheat, funktioniert auch mit PCG-Actors).
	AActor* Target = FindInteractable(GetPawnViewLocation(), GetControlRotation());
	if (Target && IManhuntInteractable::Execute_CanInteract(Target, this))
	{
		IManhuntInteractable::Execute_Interact(Target, this);
	}
}

void AManhuntCharacter::Server_RunnerAbility_Implementation()
{
	if (!IsRunner() || IsMovementLocked())
	{
		return;
	}
	if (AManhuntDoor* Door = Cast<AManhuntDoor>(FindInteractable(GetPawnViewLocation(), GetControlRotation())))
	{
		if (Door->TryToggleLock(this))
		{
			ShowMessage(Door->GetDoorState() == EManhuntDoorState::Locked
				? NSLOCTEXT("Manhunt", "Locked", "Verriegelt")
				: NSLOCTEXT("Manhunt", "Unlocked", "Entriegelt"));
		}
	}
}

// ---------------------------------------------------------------------------
// Zeitaktionen
// ---------------------------------------------------------------------------

void AManhuntCharacter::StartTimedAction(float Duration, const FText& Label, TFunction<void()> OnComplete)
{
	if (!HasAuthority() || IsBusy() || Duration <= 0.f)
	{
		return;
	}
	const AGameStateBase* GS = GetWorld()->GetGameState();
	const float Now = GS ? static_cast<float>(GS->GetServerWorldTimeSeconds()) : GetWorld()->GetTimeSeconds();

	TimedActionCallback = MoveTemp(OnComplete);
	TimedActionDuration = Duration;
	TimedActionEndTime = Now + Duration;
	TimedActionLabel = Label;
	SetMovementLock(EManhuntLock::Busy, true);
	GetWorldTimerManager().SetTimer(TimedActionTimer, this, &AManhuntCharacter::FinishTimedAction, Duration, false);
}

void AManhuntCharacter::FinishTimedAction()
{
	TFunction<void()> Callback = MoveTemp(TimedActionCallback);
	TimedActionCallback = nullptr;
	TimedActionDuration = 0.f;
	TimedActionEndTime = 0.f;
	TimedActionLabel = FText::GetEmpty();
	SetMovementLock(EManhuntLock::Busy, false);

	if (Callback)
	{
		Callback();
	}
}

void AManhuntCharacter::CancelTimedAction()
{
	if (!IsBusy())
	{
		return;
	}
	GetWorldTimerManager().ClearTimer(TimedActionTimer);
	TimedActionCallback = nullptr;
	TimedActionDuration = 0.f;
	TimedActionEndTime = 0.f;
	TimedActionLabel = FText::GetEmpty();
	SetMovementLock(EManhuntLock::Busy, false);
}

// ---------------------------------------------------------------------------
// Tackle & Struggle
// ---------------------------------------------------------------------------

void AManhuntCharacter::Server_Tackle_Implementation()
{
	// Regel: Auf Fahrzeugen kann kein Tackle ausgefuehrt werden.
	if (!IsHunter() || MountedVehicle || IsMovementLocked() || GrabbedRunner)
	{
		return;
	}
	const float Now = GetWorld()->GetTimeSeconds();
	if (Now - LastTackleTime < TackleCooldown)
	{
		return;
	}
	LastTackleTime = Now;
	Multicast_PlayTackle();

	const FVector AimDir = FRotator(0.f, GetControlRotation().Yaw, 0.f).Vector();
	AManhuntCharacter* Best = nullptr;
	float BestDistSq = FMath::Square(TackleRange);

	for (TActorIterator<AManhuntCharacter> It(GetWorld()); It; ++It)
	{
		AManhuntCharacter* Other = *It;
		const AManhuntPlayerState* OtherPS = Other ? Other->GetManhuntPlayerState() : nullptr;
		if (Other == this || !OtherPS || !OtherPS->IsFreeRunner() || Other->GrabbedBy)
		{
			continue;
		}
		const FVector ToOther = Other->GetActorLocation() - GetActorLocation();
		const float DistSq = ToOther.SizeSquared();
		if (DistSq > BestDistSq || FVector::DotProduct(AimDir, ToOther.GetSafeNormal2D()) < 0.4f)
		{
			continue;
		}
		if (!Other->HasLineOfSightFrom(GetPawnViewLocation(), this))
		{
			continue;
		}
		Best = Other;
		BestDistSq = DistSq;
	}

	if (Best)
	{
		Best->BeginStruggle(this);
	}
}

void AManhuntCharacter::Multicast_PlayTackle_Implementation()
{
	OnTackle();
}

void AManhuntCharacter::BeginStruggle(AManhuntCharacter* Hunter)
{
	if (!Hunter)
	{
		return;
	}
	InterruptEverything(); // Schlange, Automat, Fahrzeug (Runner wird vom Scooter gerissen)

	GrabbedBy = Hunter;
	Hunter->GrabbedRunner = this;
	StruggleProgress = 0.f;
	SetMovementLock(EManhuntLock::Grabbed, true);
	Hunter->SetMovementLock(EManhuntLock::Grabbed, true);
	OnGrabStateChanged(true);
	Hunter->OnGrabStateChanged(true);

	// Kampfsportler: bei niedriger Runner-Stamina sofortiger Catch.
	const FManhuntClassStats& HunterStats = Hunter->GetClassStats();
	if (HunterStats.InstantCatchStaminaRatio > 0.f && GetStaminaRatio() < HunterStats.InstantCatchStaminaRatio)
	{
		EndStruggle(false);
		return;
	}

	GetWorldTimerManager().SetTimer(StruggleTimer, this, &AManhuntCharacter::OnStruggleTimeout, StruggleDuration, false);
	ShowMessage(NSLOCTEXT("Manhunt", "Grabbed", "GEPACKT! Haemmere [Leertaste], um dich loszureissen!"));
	Hunter->ShowMessage(NSLOCTEXT("Manhunt", "GotHim", "Gepackt - festhalten!"));
}

void AManhuntCharacter::Server_StruggleInput_Implementation()
{
	if (!GrabbedBy)
	{
		return;
	}
	const float Now = GetWorld()->GetTimeSeconds();
	if (Now - LastStrugglePressTime < 0.07f)
	{
		return; // max. ~14 Eingaben/s (Makro-Schutz)
	}
	LastStrugglePressTime = Now;

	// Weniger Stamina = schwaecheres Losreissen. Hohe Griffstaerke (Kampfsportler) = massiv schwerer.
	const float Grip = FMath::Max(0.1f, GrabbedBy->GetClassStats().GripStrength);
	StruggleProgress += EscapePerPress * (0.5f + 0.5f * GetStaminaRatio()) / Grip;
	AddStamina(-2.f);

	if (StruggleProgress >= 1.f)
	{
		EndStruggle(true);
	}
}

void AManhuntCharacter::OnStruggleTimeout()
{
	EndStruggle(false);
}

void AManhuntCharacter::EndStruggle(bool bEscaped)
{
	GetWorldTimerManager().ClearTimer(StruggleTimer);

	AManhuntCharacter* Hunter = GrabbedBy;
	GrabbedBy = nullptr;
	StruggleProgress = 0.f;
	SetMovementLock(EManhuntLock::Grabbed, false);
	OnGrabStateChanged(false);

	if (Hunter)
	{
		Hunter->GrabbedRunner = nullptr;
		Hunter->SetMovementLock(EManhuntLock::Grabbed, false);
		Hunter->OnGrabStateChanged(false);
	}

	if (bEscaped)
	{
		ShowMessage(NSLOCTEXT("Manhunt", "Escaped", "Losgerissen - LAUF!"));
		if (Hunter)
		{
			Hunter->ShowMessage(NSLOCTEXT("Manhunt", "Lost", "Der Runner hat sich losgerissen!"));
			Hunter->SetMovementLock(EManhuntLock::Stunned, true);
			Hunter->GetWorldTimerManager().SetTimer(Hunter->StunTimer,
				FTimerDelegate::CreateWeakLambda(Hunter, [Hunter]() { Hunter->SetMovementLock(EManhuntLock::Stunned, false); }),
				HunterStunAfterEscape, false);
		}
		return;
	}

	SetMovementLock(EManhuntLock::Caught, true);
	if (AManhuntGameMode* GM = GetWorld()->GetAuthGameMode<AManhuntGameMode>())
	{
		GM->HandleRunnerCaught(this, Hunter);
	}
}

void AManhuntCharacter::OnRep_GrabbedBy()
{
	OnGrabStateChanged(GrabbedBy != nullptr);
}

void AManhuntCharacter::OnRep_GrabbedRunner()
{
	OnGrabStateChanged(GrabbedRunner != nullptr);
}

// ---------------------------------------------------------------------------
// Fahrzeuge
// ---------------------------------------------------------------------------

void AManhuntCharacter::SetMountedVehicle(AActor* Vehicle)
{
	MountedVehicle = Vehicle;
	UnusableSurfaceTime = 0.f;
	if (Vehicle)
	{
		CancelTimedAction();
	}
	OnRep_MountedVehicle();
}

void AManhuntCharacter::OnRep_MountedVehicle()
{
	RefreshVehicleSpeed(SurfaceType_Default);
	OnMountedVehicleChanged(MountedVehicle);
}

void AManhuntCharacter::RefreshVehicleSpeed(EPhysicalSurface Surface)
{
	if (MountedVehicle && MountedVehicle->Implements<UManhuntMountableVehicle>())
	{
		float Speed = IManhuntMountableVehicle::Execute_GetMaxSpeedOnSurface(MountedVehicle, Surface);
		CachedVehicleStaminaCost = IManhuntMountableVehicle::Execute_GetRiderStaminaCostPerSecond(MountedVehicle);
		if (CachedVehicleStaminaCost > 0.f && bExhausted)
		{
			Speed *= 0.6f; // erschoepft: nur noch langsam treten
		}
		CachedVehicleSpeed = Speed;
	}
	else
	{
		CachedVehicleSpeed = 0.f;
		CachedVehicleStaminaCost = 0.f;
	}
}

// ---------------------------------------------------------------------------
// Items (Energy-Drink, Smartphone-Joker)
// ---------------------------------------------------------------------------

void AManhuntCharacter::Server_UseItem_Implementation(EManhuntItem Item)
{
	AManhuntPlayerState* PS = GetManhuntPlayerState();
	if (!PS || (MovementLockFlags & EManhuntLock::Caught))
	{
		return;
	}

	switch (Item)
	{
	case EManhuntItem::EnergyDrink:
		if (PS->ConsumeItem(Item))
		{
			AddStamina(ClassStats.MaxStamina);
			ShowMessage(NSLOCTEXT("Manhunt", "Drink", "Energy-Drink: Stamina 100 %"));
		}
		break;

	case EManhuntItem::PingBlocker:
		if (IsRunner() && !PS->bPingBlockerArmed && PS->ConsumeItem(Item))
		{
			PS->bPingBlockerArmed = true;
			ShowMessage(NSLOCTEXT("Manhunt", "Blocker", "Ping-Blocker aktiv: dein naechster Ping wird blockiert"));
		}
		break;

	case EManhuntItem::FakePing:
		if (IsRunner() && !PS->bFakePingArmed && PS->ConsumeItem(Item))
		{
			PS->bFakePingArmed = true;
			ShowMessage(NSLOCTEXT("Manhunt", "Fake", "Fake-Ping aktiv: die Hunter sehen beim naechsten Ping eine falsche Position"));
		}
		break;

	default:
		break;
	}
}
