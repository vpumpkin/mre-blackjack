#include "Core/ManhuntPlayerState.h"
#include "Net/UnrealNetwork.h"

void AManhuntPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AManhuntPlayerState, Team);
	DOREPLIFETIME(AManhuntPlayerState, HunterClass);
	DOREPLIFETIME(AManhuntPlayerState, bTaskforceLeader);
	DOREPLIFETIME(AManhuntPlayerState, RunnerStatus);
	DOREPLIFETIME(AManhuntPlayerState, BottleCount);

	DOREPLIFETIME_CONDITION(AManhuntPlayerState, MoneyCents, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(AManhuntPlayerState, PfandbonCents, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(AManhuntPlayerState, PingBlockers, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(AManhuntPlayerState, FakePings, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(AManhuntPlayerState, EnergyDrinks, COND_OwnerOnly);
}

void AManhuntPlayerState::OnRep_Changed()
{
	OnManhuntStateChanged.Broadcast();
}

void AManhuntPlayerState::NotifyChanged()
{
	// Auf dem Server (Listen-Host) feuern keine OnReps -> manuell benachrichtigen.
	OnManhuntStateChanged.Broadcast();
}

int32 AManhuntPlayerState::GetItemCount(EManhuntItem Item) const
{
	switch (Item)
	{
	case EManhuntItem::PfandBottle: return BottleCount;
	case EManhuntItem::PingBlocker: return PingBlockers;
	case EManhuntItem::FakePing:    return FakePings;
	case EManhuntItem::EnergyDrink: return EnergyDrinks;
	case EManhuntItem::Cash:        return MoneyCents;
	default:                        return 0;
	}
}

void AManhuntPlayerState::SetTeam(EManhuntTeam NewTeam)
{
	Team = NewTeam;
	NotifyChanged();
}

void AManhuntPlayerState::SetHunterClass(EHunterClass NewClass)
{
	HunterClass = NewClass;
	NotifyChanged();
}

void AManhuntPlayerState::SetTaskforceLeader(bool bLeader)
{
	bTaskforceLeader = bLeader;
	NotifyChanged();
}

void AManhuntPlayerState::SetRunnerStatus(ERunnerStatus NewStatus)
{
	RunnerStatus = NewStatus;
	NotifyChanged();
}

void AManhuntPlayerState::AddItem(EManhuntItem Item, int32 Amount)
{
	switch (Item)
	{
	case EManhuntItem::PfandBottle: BottleCount = FMath::Max(0, BottleCount + Amount); break;
	case EManhuntItem::PingBlocker: PingBlockers = FMath::Max(0, PingBlockers + Amount); break;
	case EManhuntItem::FakePing:    FakePings = FMath::Max(0, FakePings + Amount); break;
	case EManhuntItem::EnergyDrink: EnergyDrinks = FMath::Max(0, EnergyDrinks + Amount); break;
	case EManhuntItem::Cash:        MoneyCents = FMath::Max(0, MoneyCents + Amount); break;
	}
	NotifyChanged();
}

bool AManhuntPlayerState::ConsumeItem(EManhuntItem Item)
{
	if (GetItemCount(Item) <= 0)
	{
		return false;
	}
	AddItem(Item, -1);
	return true;
}

bool AManhuntPlayerState::SpendMoney(int32 Cents)
{
	if (Cents < 0 || MoneyCents < Cents)
	{
		return false;
	}
	MoneyCents -= Cents;
	NotifyChanged();
	return true;
}

void AManhuntPlayerState::AddPfandbon(int32 Cents)
{
	PfandbonCents += FMath::Max(0, Cents);
	NotifyChanged();
}

int32 AManhuntPlayerState::CashOutPfandbon()
{
	const int32 Paid = PfandbonCents;
	MoneyCents += Paid;
	PfandbonCents = 0;
	NotifyChanged();
	return Paid;
}
