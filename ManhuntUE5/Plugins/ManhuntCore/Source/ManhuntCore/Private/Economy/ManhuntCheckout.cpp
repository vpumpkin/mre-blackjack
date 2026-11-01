#include "Economy/ManhuntCheckout.h"
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntPlayerState.h"
#include "Components/ArrowComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

AManhuntCheckout::AManhuntCheckout()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	CounterMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CounterMesh"));
	CounterMesh->SetupAttachment(Root);
	CounterMesh->SetCollisionProfileName(TEXT("BlockAll"));

	QueueStart = CreateDefaultSubobject<UArrowComponent>(TEXT("QueueStart"));
	QueueStart->SetupAttachment(Root);
	QueueStart->SetRelativeLocation(FVector(-120.f, 0.f, 0.f));
	QueueStart->ArrowColor = FColor::Green;
}

void AManhuntCheckout::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AManhuntCheckout, Queue);
}

bool AManhuntCheckout::IsNetRelevantFor(const AActor* RealViewer, const AActor* ViewTarget, const FVector& SrcLocation) const
{
	// Nur nahe Clients (oder ein Hacker, dessen Kamera in der Naehe haengt) kennen die Schlange.
	const APlayerController* PC = Cast<APlayerController>(RealViewer);
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	const float RadiusSq = FMath::Square(ReplicationRadius);
	return FVector::DistSquared(SrcLocation, GetActorLocation()) < RadiusSq
		|| (Pawn && FVector::DistSquared(Pawn->GetActorLocation(), GetActorLocation()) < RadiusSq);
}

FVector AManhuntCheckout::GetSlotLocation(int32 Index) const
{
	return QueueStart->GetComponentLocation() - QueueStart->GetForwardVector() * (SlotSpacing * Index);
}

int32 AManhuntCheckout::GetQueueIndex(const AActor* Who) const
{
	return Queue.IndexOfByPredicate([Who](const FManhuntQueueEntry& Entry) { return Entry.Actor.Get() == Who; });
}

bool AManhuntCheckout::GetSlotLocationFor(const AActor* Who, FVector& OutLocation) const
{
	const int32 Index = GetQueueIndex(Who);
	if (Index == INDEX_NONE)
	{
		return false;
	}
	OutLocation = GetSlotLocation(Index);
	return true;
}

void AManhuntCheckout::BeginPlay()
{
	Super::BeginPlay();
	if (HasAuthority())
	{
		for (int32 i = 0; i < InitialNpcCount; ++i)
		{
			SpawnNpc();
		}
		ScheduleArrival();
		ScheduleService();
	}
}

void AManhuntCheckout::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (HasAuthority())
	{
		for (const FManhuntQueueEntry& Entry : Queue)
		{
			if (!Entry.bIsPlayer && Entry.Actor)
			{
				Entry.Actor->Destroy();
			}
		}
	}
	Super::EndPlay(EndPlayReason);
}

void AManhuntCheckout::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	MoveNpcs(DeltaSeconds); // laeuft auf Server UND Clients (keine Bewegungs-Replikation noetig)
	if (HasAuthority())
	{
		CheckPlayersInLine();
	}
}

// ---------------------------------------------------------------------------
// NPC-Kunden
// ---------------------------------------------------------------------------

void AManhuntCheckout::ScheduleArrival()
{
	const float Delay = FMath::FRandRange(NpcArrivalIntervalRange.X, FMath::Max(NpcArrivalIntervalRange.X, NpcArrivalIntervalRange.Y));
	GetWorldTimerManager().SetTimer(ArrivalTimer, FTimerDelegate::CreateWeakLambda(this, [this]()
	{
		SpawnNpc();
		ScheduleArrival();
	}), FMath::Max(0.5f, Delay), false);
}

void AManhuntCheckout::SpawnNpc()
{
	if (NpcCustomerClasses.Num() == 0 || Queue.Num() >= MaxQueueLength)
	{
		return;
	}
	const TSubclassOf<AActor> NpcClass = NpcCustomerClasses[FMath::RandRange(0, NpcCustomerClasses.Num() - 1)];
	if (!NpcClass)
	{
		return;
	}

	const FTransform SpawnTransform(FRotator(0.f, QueueStart->GetComponentRotation().Yaw, 0.f),
		GetSlotLocation(Queue.Num() + 2) + FVector(0.f, 0.f, 100.f));
	AActor* Npc = GetWorld()->SpawnActorDeferred<AActor>(NpcClass, SpawnTransform, this, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (!Npc)
	{
		return;
	}
	Npc->SetReplicates(true);
	Npc->SetReplicateMovement(false); // Position ergibt sich auf jedem Rechner aus dem Schlangenplatz
	Npc->FinishSpawning(SpawnTransform);

	if (ACharacter* NpcChar = Cast<ACharacter>(Npc))
	{
		NpcChar->GetCharacterMovement()->SetMovementMode(MOVE_None);
	}

	FManhuntQueueEntry& Entry = Queue.AddDefaulted_GetRef();
	Entry.Actor = Npc;
	Entry.bIsPlayer = false;
	ScheduleService();
}

void AManhuntCheckout::MoveNpcs(float DeltaSeconds)
{
	const float FacingYaw = QueueStart->GetComponentRotation().Yaw;

	for (int32 i = 0; i < Queue.Num(); ++i)
	{
		AActor* Actor = Queue[i].Actor;
		if (!Actor || Actor->IsA<AManhuntCharacter>())
		{
			continue; // Spieler laufen selbst (Auto-Walk im Charakter)
		}

		FVector Target = GetSlotLocation(i);
		if (ACharacter* NpcChar = Cast<ACharacter>(Actor))
		{
			UCapsuleComponent* Capsule = NpcChar->GetCapsuleComponent();
			Target.Z += Capsule->GetScaledCapsuleHalfHeight();
			if (Capsule->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Ignore)
			{
				Capsule->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore); // Spieler in der Schlange nicht blockieren
			}
		}
		const FVector NewLocation = FMath::VInterpConstantTo(Actor->GetActorLocation(), Target, DeltaSeconds, NpcMoveSpeed);
		Actor->SetActorLocationAndRotation(NewLocation, FRotator(0.f, FacingYaw, 0.f));
	}
}

// ---------------------------------------------------------------------------
// Kasse
// ---------------------------------------------------------------------------

void AManhuntCheckout::ScheduleService()
{
	if (Queue.Num() > 0 && !GetWorldTimerManager().IsTimerActive(ServiceTimer))
	{
		const float Delay = FMath::FRandRange(ServiceTimeRange.X, FMath::Max(ServiceTimeRange.X, ServiceTimeRange.Y));
		GetWorldTimerManager().SetTimer(ServiceTimer, this, &AManhuntCheckout::ServeFront, FMath::Max(0.5f, Delay), false);
	}
}

void AManhuntCheckout::ServeFront()
{
	if (Queue.Num() == 0)
	{
		return;
	}
	AActor* Front = Queue[0].Actor;
	if (!Front)
	{
		RemoveEntryAt(0, false);
		ScheduleService();
		return;
	}
	// Erst bedienen, wenn der Kunde wirklich vorne steht.
	if (FVector::DistSquared2D(Front->GetActorLocation(), GetSlotLocation(0)) > FMath::Square(120.f))
	{
		GetWorldTimerManager().SetTimer(ServiceTimer, this, &AManhuntCheckout::ServeFront, 1.f, false);
		return;
	}

	int32 Paid = 0;
	if (Queue[0].bIsPlayer)
	{
		if (AManhuntCharacter* Char = Cast<AManhuntCharacter>(Front))
		{
			if (AManhuntPlayerState* PS = Char->GetManhuntPlayerState())
			{
				Paid = PS->CashOutPfandbon();
			}
			Char->ShowMessage(Paid > 0
				? FText::Format(NSLOCTEXT("Manhunt", "CashOut", "Der Kassierer zahlt dir {0} aus."), FText::FromString(ManhuntMoney::Format(Paid)))
				: NSLOCTEXT("Manhunt", "NextPlease", "\"Naechster bitte!\" (kein Pfandbon)"));
		}
	}
	OnCustomerServed(Front, Paid);
	RemoveEntryAt(0, true);
	LastAdvanceTime = GetWorld()->GetTimeSeconds();
	ScheduleService();
}

void AManhuntCheckout::RemoveEntryAt(int32 Index, bool bDestroyNpc)
{
	if (!Queue.IsValidIndex(Index))
	{
		return;
	}
	const FManhuntQueueEntry Entry = Queue[Index];
	Queue.RemoveAt(Index);

	if (Entry.bIsPlayer)
	{
		if (AManhuntCharacter* Char = Cast<AManhuntCharacter>(Entry.Actor))
		{
			Char->ClearCurrentInteraction(this);
			Char->SetActiveQueue(nullptr);
		}
	}
	else if (bDestroyNpc && Entry.Actor)
	{
		Entry.Actor->Destroy();
	}
}

void AManhuntCheckout::CheckPlayersInLine()
{
	const float Now = GetWorld()->GetTimeSeconds();

	for (int32 i = Queue.Num() - 1; i >= 0; --i)
	{
		FManhuntQueueEntry& Entry = Queue[i];
		if (!Entry.bIsPlayer)
		{
			continue;
		}
		AManhuntCharacter* Char = Cast<AManhuntCharacter>(Entry.Actor);
		if (!Char)
		{
			RemoveEntryAt(i, false);
			continue;
		}

		const float DistSq = FVector::DistSquared2D(Char->GetActorLocation(), GetSlotLocation(i));
		if (!Entry.bArrived)
		{
			if (DistSq < FMath::Square(60.f))
			{
				Entry.bArrived = true;
			}
			else if (Now - Entry.JoinTime > 20.f)
			{
				Char->ShowMessage(NSLOCTEXT("Manhunt", "QueueTimeout", "Du bist nicht in der Schlange angekommen."));
				RemoveEntryAt(i, false);
			}
			continue;
		}
		if (Now - LastAdvanceTime > 3.f && DistSq > FMath::Square(LeaveDistance))
		{
			Char->ShowMessage(NSLOCTEXT("Manhunt", "QueueLost", "Platz in der Schlange verloren!"));
			RemoveEntryAt(i, false);
		}
	}
}

// ---------------------------------------------------------------------------
// IManhuntInteractable
// ---------------------------------------------------------------------------

bool AManhuntCheckout::CanInteract_Implementation(AManhuntCharacter* Interactor)
{
	return Interactor && Interactor->IsRunner() && (GetQueueIndex(Interactor) != INDEX_NONE || Queue.Num() < MaxQueueLength);
}

FText AManhuntCheckout::GetInteractionPrompt_Implementation(AManhuntCharacter* Interactor)
{
	return GetQueueIndex(Interactor) != INDEX_NONE
		? NSLOCTEXT("Manhunt", "LeaveLine", "Schlange verlassen")
		: NSLOCTEXT("Manhunt", "JoinLine", "An der Kasse anstellen (Pfandbon einloesen)");
}

void AManhuntCheckout::Interact_Implementation(AManhuntCharacter* Interactor)
{
	if (!Interactor)
	{
		return;
	}
	const int32 Existing = GetQueueIndex(Interactor);
	if (Existing != INDEX_NONE)
	{
		RemoveEntryAt(Existing, false);
		Interactor->ShowMessage(NSLOCTEXT("Manhunt", "LeftLine", "Schlange verlassen."));
		return;
	}
	if (!CanInteract_Implementation(Interactor))
	{
		Interactor->ShowMessage(NSLOCTEXT("Manhunt", "LineFull", "Die Schlange ist zu lang."));
		return;
	}

	FManhuntQueueEntry& Entry = Queue.AddDefaulted_GetRef();
	Entry.Actor = Interactor;
	Entry.bIsPlayer = true;
	Entry.JoinTime = GetWorld()->GetTimeSeconds();
	Interactor->SetCurrentInteraction(this);
	Interactor->SetActiveQueue(this);

	const AManhuntPlayerState* PS = Interactor->GetManhuntPlayerState();
	Interactor->ShowMessage(FText::Format(NSLOCTEXT("Manhunt", "Joined", "Angestellt auf Platz {0}. Unauffaellig bleiben!{1}"),
		FText::AsNumber(Queue.Num()),
		(PS && PS->GetPfandbonCents() > 0) ? FText::GetEmpty() : NSLOCTEXT("Manhunt", "NoBon", " (Kein Pfandbon - nur zum Verstecken?)")));
	ScheduleService();
}

void AManhuntCheckout::CancelInteraction_Implementation(AManhuntCharacter* Interactor)
{
	const int32 Index = GetQueueIndex(Interactor);
	if (Index != INDEX_NONE)
	{
		RemoveEntryAt(Index, false);
	}
}
