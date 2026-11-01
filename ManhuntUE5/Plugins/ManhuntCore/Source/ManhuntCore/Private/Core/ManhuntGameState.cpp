#include "Core/ManhuntGameState.h"
#include "World/ManhuntDoor.h"
#include "Net/UnrealNetwork.h"

// ---------------- FastArray-Callbacks (laufen auf Clients) ----------------

void FManhuntDoorItem::PostReplicatedAdd(const FManhuntDoorArray& InArray)
{
	if (AManhuntGameState* GS = InArray.OwnerState.Get())
	{
		GS->HandleDoorReplicated(DoorKey, State, false);
	}
}

void FManhuntDoorItem::PostReplicatedChange(const FManhuntDoorArray& InArray)
{
	if (AManhuntGameState* GS = InArray.OwnerState.Get())
	{
		GS->HandleDoorReplicated(DoorKey, State, false);
	}
}

void FManhuntDoorItem::PreReplicatedRemove(const FManhuntDoorArray& InArray)
{
	if (AManhuntGameState* GS = InArray.OwnerState.Get())
	{
		GS->HandleDoorReplicated(DoorKey, State, true);
	}
}

// ---------------- GameState ----------------

void AManhuntGameState::PostInitializeComponents()
{
	Super::PostInitializeComponents();
	DoorStates.OwnerState = this;
}

void AManhuntGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AManhuntGameState, Phase);
	DOREPLIFETIME(AManhuntGameState, ElapsedSeconds);
	DOREPLIFETIME(AManhuntGameState, MatchDurationSeconds);
	DOREPLIFETIME(AManhuntGameState, ClassSelectionEndServerTime);
	DOREPLIFETIME(AManhuntGameState, bSpeedhuntActive);
	DOREPLIFETIME(AManhuntGameState, SpeedhuntsRemaining);
	DOREPLIFETIME(AManhuntGameState, WinningTeam);
	DOREPLIFETIME(AManhuntGameState, DoorStates);
}

float AManhuntGameState::GetClassSelectionRemaining() const
{
	return FMath::Max(0.f, ClassSelectionEndServerTime - static_cast<float>(GetServerWorldTimeSeconds()));
}

float AManhuntGameState::GetTimeOfDayHours() const
{
	const float Alpha = MatchDurationSeconds > 0 ? FMath::Clamp(static_cast<float>(ElapsedSeconds) / MatchDurationSeconds, 0.f, 1.f) : 0.f;
	return FMath::Lerp(DayCycleStartHour, DayCycleEndHour, Alpha);
}

void AManhuntGameState::SetPhase(EManhuntPhase NewPhase)
{
	if (Phase != NewPhase)
	{
		Phase = NewPhase;
		OnRep_Phase(); // Listen-Server
	}
}

void AManhuntGameState::SetSpeedhunt(bool bActive, int32 Remaining)
{
	SpeedhuntsRemaining = Remaining;
	if (bSpeedhuntActive != bActive)
	{
		bSpeedhuntActive = bActive;
		OnRep_Speedhunt();
	}
}

void AManhuntGameState::OnRep_Phase()
{
	OnPhaseChanged.Broadcast(Phase);
}

void AManhuntGameState::OnRep_Speedhunt()
{
	OnSpeedhuntChanged.Broadcast(bSpeedhuntActive);
}

// ---------------- Tueren ----------------

void AManhuntGameState::SetDoorState(uint64 DoorKey, EManhuntDoorState NewState, EManhuntDoorState DefaultState)
{
	const int32 Index = DoorStates.Items.IndexOfByPredicate([DoorKey](const FManhuntDoorItem& Item) { return Item.DoorKey == DoorKey; });

	if (NewState == DefaultState)
	{
		if (Index != INDEX_NONE)
		{
			DoorStates.Items.RemoveAtSwap(Index);
			DoorStates.MarkArrayDirty();
		}
	}
	else if (Index != INDEX_NONE)
	{
		DoorStates.Items[Index].State = NewState;
		DoorStates.MarkItemDirty(DoorStates.Items[Index]);
	}
	else
	{
		FManhuntDoorItem& Item = DoorStates.Items.AddDefaulted_GetRef();
		Item.DoorKey = DoorKey;
		Item.State = NewState;
		DoorStates.MarkItemDirty(Item);
	}

	// Server / Listen-Host wendet direkt an.
	if (const TWeakObjectPtr<AManhuntDoor>* Found = DoorRegistry.Find(DoorKey))
	{
		if (AManhuntDoor* Door = Found->Get())
		{
			Door->ApplyDoorState(NewState);
		}
	}
}

bool AManhuntGameState::FindDoorState(uint64 DoorKey, EManhuntDoorState& OutState) const
{
	for (const FManhuntDoorItem& Item : DoorStates.Items)
	{
		if (Item.DoorKey == DoorKey)
		{
			OutState = Item.State;
			return true;
		}
	}
	return false;
}

void AManhuntGameState::RegisterDoor(AManhuntDoor* Door)
{
	if (!Door)
	{
		return;
	}
	DoorRegistry.Add(Door->GetDoorKey(), Door);

	// Nachtraeglich gestreamte Tuer: aktuellen Zustand sofort uebernehmen.
	EManhuntDoorState Current;
	Door->ApplyDoorState(FindDoorState(Door->GetDoorKey(), Current) ? Current : Door->GetDefaultState());
}

void AManhuntGameState::UnregisterDoor(AManhuntDoor* Door)
{
	if (Door)
	{
		DoorRegistry.Remove(Door->GetDoorKey());
	}
}

void AManhuntGameState::HandleDoorReplicated(uint64 DoorKey, EManhuntDoorState State, bool bRemoved)
{
	if (const TWeakObjectPtr<AManhuntDoor>* Found = DoorRegistry.Find(DoorKey))
	{
		if (AManhuntDoor* Door = Found->Get())
		{
			Door->ApplyDoorState(bRemoved ? Door->GetDefaultState() : State);
		}
	}
}
