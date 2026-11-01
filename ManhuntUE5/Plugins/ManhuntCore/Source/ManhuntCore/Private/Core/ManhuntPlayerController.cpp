#include "Core/ManhuntPlayerController.h"
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntGameMode.h"
#include "Core/ManhuntGameState.h"
#include "Core/ManhuntPlayerState.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputMappingContext.h"
#include "InputAction.h"
#include "InputModifiers.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"

// ---------------------------------------------------------------------------
// Input – wird zur Laufzeit gebaut, damit das Plugin ohne .uasset-Dateien sofort spielbar ist.
//
//  WASD Laufen | Maus Umsehen | Shift Sprinten | Leertaste Springen/Losreissen
//  E Interagieren | Q Faehigkeit (Hacker: CCTV, Faehrtenleser: Spuren, Runner: Tuer verriegeln)
//  Linke Maustaste Tackle (Hunter) | Mausrad Kamera wechseln (Hacker)
//  1/2/3 vor dem Start: Hunter-Klasse, im Spiel: Energy-Drink / Ping-Blocker / Fake-Ping
//  J/H Speedhunt-Ziel waehlen/aktivieren (Taskforce-Leader) | Tab Taktik-Tablet
// ---------------------------------------------------------------------------

UInputAction* AManhuntPlayerController::MakeAction(const TCHAR* Name, EInputActionValueType Type)
{
	UInputAction* Action = NewObject<UInputAction>(this, FName(Name));
	Action->ValueType = Type;
	Actions.Add(Action);
	return Action;
}

void AManhuntPlayerController::MapKey(UInputAction* Action, const FKey& Key, bool bSwizzle, bool bNegate)
{
	FEnhancedActionKeyMapping& Mapping = MappingContext->MapKey(Action, Key);
	if (bSwizzle)
	{
		Mapping.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(MappingContext)); // Standard: YXZ
	}
	if (bNegate)
	{
		Mapping.Modifiers.Add(NewObject<UInputModifierNegate>(MappingContext));
	}
}

void AManhuntPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();

	UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(InputComponent);
	if (!EIC)
	{
		UE_LOG(LogManhunt, Error, TEXT("Projekt-Einstellungen -> Input -> Default Input Component Class muss 'EnhancedInputComponent' sein."));
		return;
	}

	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_ManhuntDefault"));

	UInputAction* Move = MakeAction(TEXT("IA_Move"), EInputActionValueType::Axis2D);
	MapKey(Move, EKeys::W, true, false);
	MapKey(Move, EKeys::S, true, true);
	MapKey(Move, EKeys::D);
	MapKey(Move, EKeys::A, false, true);

	UInputAction* Look = MakeAction(TEXT("IA_Look"), EInputActionValueType::Axis2D);
	MapKey(Look, EKeys::Mouse2D);

	UInputAction* Jump = MakeAction(TEXT("IA_Jump"), EInputActionValueType::Boolean);
	MapKey(Jump, EKeys::SpaceBar);
	UInputAction* Sprint = MakeAction(TEXT("IA_Sprint"), EInputActionValueType::Boolean);
	MapKey(Sprint, EKeys::LeftShift);
	UInputAction* Interact = MakeAction(TEXT("IA_Interact"), EInputActionValueType::Boolean);
	MapKey(Interact, EKeys::E);
	UInputAction* Ability = MakeAction(TEXT("IA_Ability"), EInputActionValueType::Boolean);
	MapKey(Ability, EKeys::Q);
	UInputAction* Tackle = MakeAction(TEXT("IA_Tackle"), EInputActionValueType::Boolean);
	MapKey(Tackle, EKeys::LeftMouseButton);
	UInputAction* CycleCam = MakeAction(TEXT("IA_CycleCamera"), EInputActionValueType::Axis1D);
	MapKey(CycleCam, EKeys::MouseWheelAxis);
	UInputAction* Slot1 = MakeAction(TEXT("IA_Slot1"), EInputActionValueType::Boolean);
	MapKey(Slot1, EKeys::One);
	UInputAction* Slot2 = MakeAction(TEXT("IA_Slot2"), EInputActionValueType::Boolean);
	MapKey(Slot2, EKeys::Two);
	UInputAction* Slot3 = MakeAction(TEXT("IA_Slot3"), EInputActionValueType::Boolean);
	MapKey(Slot3, EKeys::Three);
	UInputAction* ShCycle = MakeAction(TEXT("IA_SpeedhuntCycle"), EInputActionValueType::Boolean);
	MapKey(ShCycle, EKeys::J);
	UInputAction* ShGo = MakeAction(TEXT("IA_SpeedhuntConfirm"), EInputActionValueType::Boolean);
	MapKey(ShGo, EKeys::H);
	UInputAction* Tablet = MakeAction(TEXT("IA_Tablet"), EInputActionValueType::Boolean);
	MapKey(Tablet, EKeys::Tab);

	EIC->BindAction(Move, ETriggerEvent::Triggered, this, &AManhuntPlayerController::OnMove);
	EIC->BindAction(Look, ETriggerEvent::Triggered, this, &AManhuntPlayerController::OnLook);
	EIC->BindAction(Jump, ETriggerEvent::Started, this, &AManhuntPlayerController::OnJump);
	EIC->BindAction(Jump, ETriggerEvent::Completed, this, &AManhuntPlayerController::OnStopJump);
	EIC->BindAction(Sprint, ETriggerEvent::Started, this, &AManhuntPlayerController::OnSprintStart);
	EIC->BindAction(Sprint, ETriggerEvent::Completed, this, &AManhuntPlayerController::OnSprintStop);
	EIC->BindAction(Interact, ETriggerEvent::Started, this, &AManhuntPlayerController::OnInteract);
	EIC->BindAction(Ability, ETriggerEvent::Started, this, &AManhuntPlayerController::OnAbility);
	EIC->BindAction(Tackle, ETriggerEvent::Started, this, &AManhuntPlayerController::OnTackle);
	EIC->BindAction(CycleCam, ETriggerEvent::Triggered, this, &AManhuntPlayerController::OnCycleCamera);
	EIC->BindAction(Slot1, ETriggerEvent::Started, this, &AManhuntPlayerController::OnSlot1);
	EIC->BindAction(Slot2, ETriggerEvent::Started, this, &AManhuntPlayerController::OnSlot2);
	EIC->BindAction(Slot3, ETriggerEvent::Started, this, &AManhuntPlayerController::OnSlot3);
	EIC->BindAction(ShCycle, ETriggerEvent::Started, this, &AManhuntPlayerController::OnSpeedhuntCycle);
	EIC->BindAction(ShGo, ETriggerEvent::Started, this, &AManhuntPlayerController::OnSpeedhuntConfirm);
	EIC->BindAction(Tablet, ETriggerEvent::Started, this, &AManhuntPlayerController::OnToggleTablet);

	if (ULocalPlayer* LP = GetLocalPlayer())
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
		{
			Subsystem->AddMappingContext(MappingContext, 0);
		}
	}
}

AManhuntPlayerState* AManhuntPlayerController::GetSpeedhuntSelection() const
{
	return SpeedhuntSelection.Get();
}

AManhuntCharacter* AManhuntPlayerController::GetManhuntCharacter() const
{
	return GetPawn<AManhuntCharacter>();
}

bool AManhuntPlayerController::IsPreMatch() const
{
	const AManhuntGameState* GS = GetWorld()->GetGameState<AManhuntGameState>();
	return !GS || GS->GetPhase() == EManhuntPhase::WaitingForPlayers || GS->GetPhase() == EManhuntPhase::ClassSelection;
}

void AManhuntPlayerController::OnMove(const FInputActionValue& Value)
{
	if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputMove(Value.Get<FVector2D>()); }
}

void AManhuntPlayerController::OnLook(const FInputActionValue& Value)
{
	if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputLook(Value.Get<FVector2D>()); }
}

void AManhuntPlayerController::OnJump()        { if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputJump(); } }
void AManhuntPlayerController::OnStopJump()    { if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputStopJump(); } }
void AManhuntPlayerController::OnSprintStart() { if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputSprint(true); } }
void AManhuntPlayerController::OnSprintStop()  { if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputSprint(false); } }
void AManhuntPlayerController::OnInteract()    { if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputInteract(); } }
void AManhuntPlayerController::OnAbility()     { if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputAbility(); } }
void AManhuntPlayerController::OnTackle()      { if (AManhuntCharacter* C = GetManhuntCharacter()) { C->InputTackle(); } }

void AManhuntPlayerController::OnCycleCamera(const FInputActionValue& Value)
{
	const float Now = GetWorld()->GetTimeSeconds();
	const float Axis = Value.Get<float>();
	if (FMath::Abs(Axis) < 0.1f || Now - LastCameraCycleTime < 0.2f)
	{
		return;
	}
	LastCameraCycleTime = Now;
	if (AManhuntCharacter* C = GetManhuntCharacter())
	{
		C->InputCycleCamera(Axis > 0.f ? 1 : -1);
	}
}

void AManhuntPlayerController::OnSlot1() { OnSlot(1); }
void AManhuntPlayerController::OnSlot2() { OnSlot(2); }
void AManhuntPlayerController::OnSlot3() { OnSlot(3); }

void AManhuntPlayerController::OnSlot(int32 Index)
{
	if (IsPreMatch())
	{
		Server_SelectHunterClass(static_cast<EHunterClass>(FMath::Clamp(Index, 1, 3)));
		return;
	}
	if (AManhuntCharacter* C = GetManhuntCharacter())
	{
		static const EManhuntItem SlotItems[] = { EManhuntItem::EnergyDrink, EManhuntItem::PingBlocker, EManhuntItem::FakePing };
		C->InputUseItem(SlotItems[FMath::Clamp(Index, 1, 3) - 1]);
	}
}

void AManhuntPlayerController::OnSpeedhuntCycle()
{
	// Naechsten freien Runner als Ziel vormerken (nur lokal, der Server prueft beim Aktivieren).
	const AManhuntGameState* GS = GetWorld()->GetGameState<AManhuntGameState>();
	if (!GS)
	{
		return;
	}
	TArray<AManhuntPlayerState*> Runners;
	for (APlayerState* P : GS->PlayerArray)
	{
		AManhuntPlayerState* PS = Cast<AManhuntPlayerState>(P);
		if (PS && PS->IsFreeRunner())
		{
			Runners.Add(PS);
		}
	}
	if (Runners.Num() == 0)
	{
		SpeedhuntSelection = nullptr;
		return;
	}
	const int32 Current = Runners.IndexOfByKey(SpeedhuntSelection.Get());
	SpeedhuntSelection = Runners[(Current + 1) % Runners.Num()];
}

void AManhuntPlayerController::OnSpeedhuntConfirm()
{
	if (AManhuntPlayerState* Target = SpeedhuntSelection.Get())
	{
		Server_RequestSpeedhunt(Target);
	}
	else
	{
		Client_ShowMessage(NSLOCTEXT("Manhunt", "NoTarget", "Erst mit [J] ein Speedhunt-Ziel waehlen."));
	}
}

void AManhuntPlayerController::OnToggleTablet()
{
	bTabletOpen = !bTabletOpen;
}

// ---------------------------------------------------------------------------
// RPCs
// ---------------------------------------------------------------------------

void AManhuntPlayerController::Server_SelectHunterClass_Implementation(EHunterClass NewClass)
{
	AManhuntGameMode* GM = GetWorld()->GetAuthGameMode<AManhuntGameMode>();
	AManhuntPlayerState* PS = GetPlayerState<AManhuntPlayerState>();
	if (GM && PS && GM->TrySelectHunterClass(PS, NewClass))
	{
		const UEnum* Enum = StaticEnum<EHunterClass>();
		Client_ShowMessage(FText::Format(NSLOCTEXT("Manhunt", "ClassChosen", "Klasse gewaehlt: {0}"),
			Enum ? Enum->GetDisplayNameTextByValue(static_cast<int64>(NewClass)) : FText::GetEmpty()));
	}
}

void AManhuntPlayerController::Server_RequestSpeedhunt_Implementation(AManhuntPlayerState* Target)
{
	AManhuntGameMode* GM = GetWorld()->GetAuthGameMode<AManhuntGameMode>();
	AManhuntPlayerState* PS = GetPlayerState<AManhuntPlayerState>();
	if (!GM || !GM->TryStartSpeedhunt(PS, Target))
	{
		Client_ShowMessage(NSLOCTEXT("Manhunt", "SpeedhuntDenied", "Speedhunt nicht moeglich (nur Taskforce-Leader, max. 2x, nicht parallel)."));
	}
}

void AManhuntPlayerController::Server_DebugGive_Implementation(EManhuntItem Item, int32 Amount)
{
#if !UE_BUILD_SHIPPING
	if (AManhuntPlayerState* PS = GetPlayerState<AManhuntPlayerState>())
	{
		PS->AddItem(Item, Amount);
	}
#endif
}

void AManhuntPlayerController::Client_ReceivePings_Implementation(const TArray<FManhuntRunnerPing>& Pings)
{
	LastPings = Pings;
	LastPingTime = GetWorld()->GetTimeSeconds();
	OnPingsReceived(Pings);
}

void AManhuntPlayerController::Client_ShowMessage_Implementation(const FText& Message)
{
	FManhuntHudMessage& Entry = Messages.AddDefaulted_GetRef();
	Entry.Text = Message;
	Entry.ExpireTime = GetWorld()->GetTimeSeconds() + 6.f;
	while (Messages.Num() > 6)
	{
		Messages.RemoveAt(0);
	}
	Messages.RemoveAll([Now = GetWorld()->GetTimeSeconds()](const FManhuntHudMessage& M) { return M.ExpireTime < Now; });
	OnManhuntMessage(Message);
}

void AManhuntPlayerController::MH_Class(int32 ClassIndex)
{
	Server_SelectHunterClass(static_cast<EHunterClass>(FMath::Clamp(ClassIndex, 1, 3)));
}

void AManhuntPlayerController::MH_Give(int32 ItemIndex, int32 Amount)
{
	Server_DebugGive(static_cast<EManhuntItem>(FMath::Clamp(ItemIndex, 0, 4)), Amount);
}
