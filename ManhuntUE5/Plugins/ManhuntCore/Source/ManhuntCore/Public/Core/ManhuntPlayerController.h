// Steuerung (Enhanced Input, zur Laufzeit erzeugt -> funktioniert ohne Input-Assets),
// Klassenwahl, Speedhunt-Befehl, Taktik-Tablet-Pings und HUD-Nachrichten.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "ManhuntTypes.h"
#include "ManhuntPlayerController.generated.h"

class UInputAction;
class UInputMappingContext;
class AManhuntCharacter;
class AManhuntPlayerState;

struct FManhuntHudMessage
{
	FText Text;
	float ExpireTime = 0.f;
};

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	// ---------------- Server-RPCs ----------------
	UFUNCTION(BlueprintCallable, Server, Reliable, Category = "Manhunt") void Server_SelectHunterClass(EHunterClass NewClass);
	UFUNCTION(BlueprintCallable, Server, Reliable, Category = "Manhunt") void Server_RequestSpeedhunt(AManhuntPlayerState* Target);
	UFUNCTION(Server, Reliable) void Server_DebugGive(EManhuntItem Item, int32 Amount);

	// ---------------- Client-RPCs ----------------
	/** Statische Radar-Pings (nur Hunter erhalten sie). */
	UFUNCTION(Client, Reliable) void Client_ReceivePings(const TArray<FManhuntRunnerPing>& Pings);
	UFUNCTION(Client, Reliable) void Client_ShowMessage(const FText& Message);

	// ---------------- Blueprint-Hooks (UMG-Taktik-Tablet etc.) ----------------
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnPingsReceived(const TArray<FManhuntRunnerPing>& Pings);
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnManhuntMessage(const FText& Message);

	// ---------------- Fuer das HUD ----------------
	const TArray<FManhuntRunnerPing>& GetLastPings() const { return LastPings; }
	float GetLastPingTime() const { return LastPingTime; }
	const TArray<FManhuntHudMessage>& GetMessages() const { return Messages; }
	bool IsTabletOpen() const { return bTabletOpen; }
	AManhuntPlayerState* GetSpeedhuntSelection() const;

	// ---------------- Konsolen-Befehle zum Testen ----------------
	/** MH_Class 1|2|3 */
	UFUNCTION(Exec) void MH_Class(int32 ClassIndex);
	/** MH_Give <0=Flasche 1=PingBlocker 2=FakePing 3=EnergyDrink 4=Cent> <Menge> (nicht in Shipping) */
	UFUNCTION(Exec) void MH_Give(int32 ItemIndex, int32 Amount);

protected:
	virtual void SetupInputComponent() override;

	UInputAction* MakeAction(const TCHAR* Name, EInputActionValueType Type);
	void MapKey(UInputAction* Action, const FKey& Key, bool bSwizzle = false, bool bNegate = false);
	AManhuntCharacter* GetManhuntCharacter() const;
	bool IsPreMatch() const;

	void OnMove(const FInputActionValue& Value);
	void OnLook(const FInputActionValue& Value);
	void OnJump();
	void OnStopJump();
	void OnSprintStart();
	void OnSprintStop();
	void OnInteract();
	void OnAbility();
	void OnTackle();
	void OnCycleCamera(const FInputActionValue& Value);
	void OnSlot1();
	void OnSlot2();
	void OnSlot3();
	void OnSlot(int32 Index);
	void OnSpeedhuntCycle();
	void OnSpeedhuntConfirm();
	void OnToggleTablet();

	UPROPERTY(Transient) TObjectPtr<UInputMappingContext> MappingContext;
	UPROPERTY(Transient) TArray<TObjectPtr<UInputAction>> Actions;

	UPROPERTY(Transient) TArray<FManhuntRunnerPing> LastPings;
	float LastPingTime = -1000.f;
	TArray<FManhuntHudMessage> Messages;
	TWeakObjectPtr<AManhuntPlayerState> SpeedhuntSelection;
	bool bTabletOpen = false;
	float LastCameraCycleTime = 0.f;
};
