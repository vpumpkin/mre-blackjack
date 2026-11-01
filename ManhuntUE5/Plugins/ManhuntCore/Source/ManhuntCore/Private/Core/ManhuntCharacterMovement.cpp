#include "Core/ManhuntCharacterMovement.h"
#include "Core/ManhuntCharacter.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "Engine/World.h"

// ---------------------------------------------------------------------------
// SavedMove: Sprint-Wunsch als Custom-Flag mitschicken (Client-Prediction)
// ---------------------------------------------------------------------------
class FSavedMove_Manhunt : public FSavedMove_Character
{
public:
	typedef FSavedMove_Character Super;

	uint8 bSavedWantsToSprint : 1;

	FSavedMove_Manhunt() : bSavedWantsToSprint(0) {}

	virtual void Clear() override
	{
		Super::Clear();
		bSavedWantsToSprint = 0;
	}

	virtual uint8 GetCompressedFlags() const override
	{
		uint8 Result = Super::GetCompressedFlags();
		if (bSavedWantsToSprint)
		{
			Result |= FLAG_Custom_0;
		}
		return Result;
	}

	virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InCharacter, float MaxDelta) const override
	{
		if (bSavedWantsToSprint != static_cast<FSavedMove_Manhunt*>(NewMove.Get())->bSavedWantsToSprint)
		{
			return false;
		}
		return Super::CanCombineWith(NewMove, InCharacter, MaxDelta);
	}

	virtual void SetMoveFor(ACharacter* C, float InDeltaTime, FVector const& NewAccel, FNetworkPredictionData_Client_Character& ClientData) override
	{
		Super::SetMoveFor(C, InDeltaTime, NewAccel, ClientData);
		if (const UManhuntCharacterMovement* Move = Cast<UManhuntCharacterMovement>(C->GetCharacterMovement()))
		{
			bSavedWantsToSprint = Move->bWantsToSprint;
		}
	}

	virtual void PrepMoveFor(ACharacter* C) override
	{
		Super::PrepMoveFor(C);
		if (UManhuntCharacterMovement* Move = Cast<UManhuntCharacterMovement>(C->GetCharacterMovement()))
		{
			Move->bWantsToSprint = bSavedWantsToSprint;
		}
	}
};

class FNetworkPredictionData_Client_Manhunt : public FNetworkPredictionData_Client_Character
{
public:
	typedef FNetworkPredictionData_Client_Character Super;

	explicit FNetworkPredictionData_Client_Manhunt(const UCharacterMovementComponent& ClientMovement)
		: Super(ClientMovement)
	{
	}

	virtual FSavedMovePtr AllocateNewMove() override
	{
		return FSavedMovePtr(new FSavedMove_Manhunt());
	}
};

// ---------------------------------------------------------------------------

UManhuntCharacterMovement::UManhuntCharacterMovement()
{
	bWantsToSprint = 0;
	MaxWalkSpeed = 600.f;
	NavAgentProps.bCanCrouch = true;
}

FNetworkPredictionData_Client* UManhuntCharacterMovement::GetPredictionData_Client() const
{
	if (ClientPredictionData == nullptr)
	{
		UManhuntCharacterMovement* MutableThis = const_cast<UManhuntCharacterMovement*>(this);
		MutableThis->ClientPredictionData = new FNetworkPredictionData_Client_Manhunt(*this);
		MutableThis->ClientPredictionData->MaxSmoothNetUpdateDist = 92.f;
		MutableThis->ClientPredictionData->NoSmoothNetUpdateDist = 140.f;
	}
	return ClientPredictionData;
}

void UManhuntCharacterMovement::UpdateFromCompressedFlags(uint8 Flags)
{
	Super::UpdateFromCompressedFlags(Flags);
	bWantsToSprint = (Flags & FSavedMove_Character::FLAG_Custom_0) != 0;
}

bool UManhuntCharacterMovement::IsSprinting() const
{
	const AManhuntCharacter* Char = Cast<AManhuntCharacter>(CharacterOwner);
	return Char && bWantsToSprint && Char->CanSprint() && IsMovingOnGround()
		&& Velocity.SizeSquared2D() > FMath::Square(Char->GetClassStats().WalkSpeed + 10.f);
}

float UManhuntCharacterMovement::GetMaxSpeed() const
{
	const AManhuntCharacter* Char = Cast<AManhuntCharacter>(CharacterOwner);
	if (!Char)
	{
		return Super::GetMaxSpeed();
	}
	if (Char->IsMovementLocked())
	{
		return 0.f;
	}
	if (!IsMovingOnGround() || IsCrouching())
	{
		return Super::GetMaxSpeed();
	}
	if (Char->GetMountedVehicle())
	{
		return Char->GetCachedVehicleSpeed();
	}

	const FManhuntClassStats& Stats = Char->GetClassStats();
	const float Base = (bWantsToSprint && Char->CanSprint()) ? Stats.SprintSpeed : Stats.WalkSpeed;
	return Base * Char->GetSpeedMultiplier();
}

void UManhuntCharacterMovement::UpdateSurface()
{
	AManhuntCharacter* Char = Cast<AManhuntCharacter>(CharacterOwner);
	if (!Char || !UpdatedComponent)
	{
		return;
	}

	// Nur fuer Fahrzeuge relevant -> spart Traces beim Laufen.
	if (!Char->GetMountedVehicle())
	{
		CurrentSurface = SurfaceType_Default;
		return;
	}

	FCollisionQueryParams Params(SCENE_QUERY_STAT(ManhuntSurface), false, Char);
	Params.bReturnPhysicalMaterial = true;
	Params.AddIgnoredActor(Char->GetMountedVehicle());

	const FVector Start = UpdatedComponent->GetComponentLocation();
	const FVector End = Start - FVector(0.f, 0.f, Char->GetDefaultHalfHeight() + 60.f);

	FHitResult Hit;
	if (GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
	{
		CurrentSurface = UPhysicalMaterial::DetermineSurfaceType(Hit.PhysMaterial.Get());
	}
	Char->RefreshVehicleSpeed(CurrentSurface);
}

void UManhuntCharacterMovement::UpdateCharacterStateBeforeMovement(float DeltaSeconds)
{
	Super::UpdateCharacterStateBeforeMovement(DeltaSeconds);

	AManhuntCharacter* Char = Cast<AManhuntCharacter>(CharacterOwner);
	if (!Char)
	{
		return;
	}

	UpdateSurface();

	// Bei Client-Replays (Korrektur) keine Stamina doppelt abziehen.
	if (!Char->bClientUpdating)
	{
		Char->SimulateStamina(DeltaSeconds, IsSprinting());
	}
}
