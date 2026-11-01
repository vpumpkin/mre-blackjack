#include "Economy/ManhuntLootSpot.h"
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntPlayerState.h"
#include "Components/StaticMeshComponent.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

AManhuntLootSpot::AManhuntLootSpot()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	NetDormancy = DORM_Initial; // tausende Muelleimer kosten keine Bandbreite, bis sich etwas aendert

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetCollisionProfileName(TEXT("BlockAll"));
	RootComponent = Mesh;

	PromptText = NSLOCTEXT("Manhunt", "Search", "Durchsuchen");
	FailText = NSLOCTEXT("Manhunt", "Nothing", "Nichts gefunden.");
}

void AManhuntLootSpot::BeginPlay()
{
	Super::BeginPlay();
	// Zur Laufzeit gespawnte Drops (Blitz-Challenge) muessen sofort repliziert werden.
	if (HasAuthority() && !IsNetStartupActor())
	{
		SetNetDormancy(DORM_Awake);
	}
}

void AManhuntLootSpot::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AManhuntLootSpot, bEmpty);
}

bool AManhuntLootSpot::CanInteract_Implementation(AManhuntCharacter* Interactor)
{
	return Interactor && !bEmpty && (!bRunnersOnly || Interactor->IsRunner());
}

FText AManhuntLootSpot::GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor)
{
	return PromptText;
}

void AManhuntLootSpot::Interact_Implementation(AManhuntCharacter* Interactor)
{
	if (!Interactor || !CanInteract_Implementation(Interactor))
	{
		return;
	}
	if (Searcher.IsValid())
	{
		if (Searcher.Get() != Interactor)
		{
			Interactor->ShowMessage(NSLOCTEXT("Manhunt", "Occupied", "Wird gerade schon durchsucht."));
		}
		return; // erneutes [E] waehrend der Suche ignorieren
	}

	if (SearchDuration <= 0.f)
	{
		FinishSearch(Interactor);
		return;
	}

	Searcher = Interactor;
	Interactor->SetCurrentInteraction(this);

	TWeakObjectPtr<AManhuntLootSpot> WeakThis(this);
	TWeakObjectPtr<AManhuntCharacter> WeakChar(Interactor);
	Interactor->StartTimedAction(SearchDuration, PromptText, [WeakThis, WeakChar]()
	{
		if (WeakThis.IsValid() && WeakChar.IsValid())
		{
			WeakThis->FinishSearch(WeakChar.Get());
		}
	});
}

void AManhuntLootSpot::CancelInteraction_Implementation(AManhuntCharacter* Interactor)
{
	if (Searcher.Get() == Interactor)
	{
		Searcher = nullptr;
	}
}

void AManhuntLootSpot::FinishSearch(AManhuntCharacter* ByCharacter)
{
	Searcher = nullptr;
	ByCharacter->ClearCurrentInteraction(this);

	AManhuntPlayerState* PS = ByCharacter->GetManhuntPlayerState();
	if (!PS || bEmpty)
	{
		return;
	}

	const bool bSuccess = FMath::FRand() <= FindChance;
	const int32 Amount = bSuccess ? FMath::RandRange(MinAmount, FMath::Max(MinAmount, MaxAmount)) : 0;

	if (Amount > 0)
	{
		PS->AddItem(LootItem, Amount);
		const UEnum* Enum = StaticEnum<EManhuntItem>();
		const FText ItemName = Enum ? Enum->GetDisplayNameTextByValue(static_cast<int64>(LootItem)) : FText::GetEmpty();
		ByCharacter->ShowMessage(LootItem == EManhuntItem::Cash
			? FText::Format(NSLOCTEXT("Manhunt", "GotCash", "+{0}"), FText::FromString(ManhuntMoney::Format(Amount)))
			: FText::Format(NSLOCTEXT("Manhunt", "GotItem", "+{0} {1}"), FText::AsNumber(Amount), ItemName));
		OnLooted(ByCharacter, Amount);
	}
	else
	{
		ByCharacter->ShowMessage(FailText);
	}

	// Auch eine Absage "leert" den Spot (der Passant laesst sich nicht sofort wieder anbetteln).
	if (bDestroyWhenLooted && Amount > 0)
	{
		Destroy();
		return;
	}
	SetEmpty(true);
	if (RespawnSeconds > 0.f)
	{
		GetWorldTimerManager().SetTimer(RefillTimer, this, &AManhuntLootSpot::Refill, RespawnSeconds, false);
	}
}

void AManhuntLootSpot::Refill()
{
	SetEmpty(false);
}

void AManhuntLootSpot::SetEmpty(bool bNewEmpty)
{
	if (bEmpty == bNewEmpty)
	{
		return;
	}
	FlushNetDormancy();
	bEmpty = bNewEmpty;
	OnRep_Empty();
}

void AManhuntLootSpot::OnRep_Empty()
{
	OnEmptyChanged(bEmpty);
}
