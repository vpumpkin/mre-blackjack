#include "Economy/ManhuntPfandMachine.h"
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntPlayerState.h"
#include "Components/StaticMeshComponent.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

AManhuntPfandMachine::AManhuntPfandMachine()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetCollisionProfileName(TEXT("BlockAll"));
	RootComponent = Mesh;
}

void AManhuntPfandMachine::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AManhuntPfandMachine, CurrentUser);
	DOREPLIFETIME(AManhuntPfandMachine, InsertedCount);
}

bool AManhuntPfandMachine::CanInteract_Implementation(AManhuntCharacter* Interactor)
{
	if (!Interactor || !Interactor->IsRunner())
	{
		return false;
	}
	if (CurrentUser)
	{
		return CurrentUser == Interactor;
	}
	const AManhuntPlayerState* PS = Interactor->GetManhuntPlayerState();
	return PS && PS->GetBottleCount() > 0;
}

FText AManhuntPfandMachine::GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor)
{
	return (CurrentUser && CurrentUser == Interactor)
		? NSLOCTEXT("Manhunt", "PrintBon", "Pfandbon drucken")
		: NSLOCTEXT("Manhunt", "InsertBottles", "Pfandflaschen einwerfen");
}

void AManhuntPfandMachine::Interact_Implementation(AManhuntCharacter* Interactor)
{
	if (!Interactor)
	{
		return;
	}
	if (CurrentUser == Interactor)
	{
		PrintBon(); // Bon-Taste
		return;
	}
	if (CurrentUser)
	{
		Interactor->ShowMessage(NSLOCTEXT("Manhunt", "MachineBusy", "Automat ist besetzt."));
		return;
	}
	if (!CanInteract_Implementation(Interactor))
	{
		return;
	}

	CurrentUser = Interactor;
	InsertedCount = 0;
	Interactor->SetCurrentInteraction(this);
	GetWorldTimerManager().SetTimer(InsertTimer, this, &AManhuntPfandMachine::InsertNextBottle, SecondsPerBottle, true);
}

void AManhuntPfandMachine::InsertNextBottle()
{
	AManhuntCharacter* User = CurrentUser;
	AManhuntPlayerState* PS = User ? User->GetManhuntPlayerState() : nullptr;

	// Weggelaufen, gepackt oder kein Runner mehr -> Bon fuer das bisher Eingeworfene.
	if (!PS || !PS->IsFreeRunner() || User->GetGrabbedBy()
		|| FVector::DistSquared(User->GetActorLocation(), GetActorLocation()) > FMath::Square(MaxUseDistance))
	{
		PrintBon();
		return;
	}
	if (!PS->ConsumeItem(EManhuntItem::PfandBottle))
	{
		PrintBon(); // Rucksack leer
		return;
	}
	++InsertedCount;
	OnRep_InsertedCount();

	if (PS->GetBottleCount() <= 0)
	{
		PrintBon();
	}
}

void AManhuntPfandMachine::PrintBon()
{
	GetWorldTimerManager().ClearTimer(InsertTimer);

	AManhuntCharacter* User = CurrentUser;
	const int32 Value = InsertedCount * BottleValueCents;

	if (User)
	{
		User->ClearCurrentInteraction(this);
		if (Value > 0)
		{
			if (AManhuntPlayerState* PS = User->GetManhuntPlayerState())
			{
				PS->AddPfandbon(Value);
			}
			User->ShowMessage(FText::Format(NSLOCTEXT("Manhunt", "BonPrinted", "Pfandbon gedruckt: {0} - an der Kasse einloesen!"),
				FText::FromString(ManhuntMoney::Format(Value))));
		}
	}
	if (Value > 0)
	{
		OnBonPrinted(Value);
	}
	CurrentUser = nullptr;
	InsertedCount = 0;
}

void AManhuntPfandMachine::CancelInteraction_Implementation(AManhuntCharacter* Interactor)
{
	if (CurrentUser == Interactor)
	{
		PrintBon();
	}
}

void AManhuntPfandMachine::OnRep_InsertedCount()
{
	OnBottleAccepted(InsertedCount);
}
