// AManhuntCharacter – gemeinsame Spielfigur fuer Runner und Hunter.
// Die Fab-Charakter-Meshes kommen in Blueprint-Childs (BP_Runner / BP_Hunter):
// Mesh + AnimBlueprint tauschen, die Spiellogik bleibt unveraendert.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Chaos/ChaosEngineInterface.h"
#include "ManhuntTypes.h"
#include "ManhuntCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UManhuntCharacterMovement;
class UManhuntHackerComponent;
class UManhuntTrackerComponent;
class UWorldPartitionStreamingSourceComponent;
class AManhuntPlayerState;
class AManhuntCheckout;
class AManhuntBuildingVolume;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AManhuntCharacter(const FObjectInitializer& ObjectInitializer);

	// ---------------- Komponenten ----------------
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Manhunt") TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Manhunt") TObjectPtr<UCameraComponent> FollowCamera;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Manhunt") TObjectPtr<UManhuntHackerComponent> Hacker;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Manhunt") TObjectPtr<UManhuntTrackerComponent> Tracker;
	/** Haelt die Welt um die eigene Figur geladen, auch wenn der Hacker durch eine ferne Kamera schaut. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Manhunt") TObjectPtr<UWorldPartitionStreamingSourceComponent> StreamingSource;

	// ---------------- Tuning ----------------
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Interaction") float InteractRange = 250.f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Tackle") float TackleRange = 180.f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Tackle") float TackleCooldown = 1.5f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Tackle") float StruggleDuration = 4.f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Tackle") float EscapePerPress = 0.06f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Tackle") float HunterStunAfterEscape = 1.5f;
	/** Anti-Cheat-Relevanz: Hunter empfangen Runner nur bei Sichtkontakt, Hacker-Kamera oder in Hoerweite. */
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Net") float BaseAudibleRadius = 900.f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Net") float AudibleRadiusPerBottle = 120.f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Net") float MaxSightDistance = 30000.f;

	// ---------------- Input (vom PlayerController weitergereicht) ----------------
	void InputMove(const FVector2D& Axis);
	void InputLook(const FVector2D& Axis);
	void InputJump();
	void InputStopJump();
	void InputSprint(bool bPressed);
	void InputInteract();
	void InputAbility();
	void InputTackle();
	void InputCycleCamera(int32 Direction);
	void InputUseItem(EManhuntItem Item);

	// ---------------- Abfragen ----------------
	UFUNCTION(BlueprintPure, Category = "Manhunt") AManhuntPlayerState* GetManhuntPlayerState() const;
	UFUNCTION(BlueprintPure, Category = "Manhunt") EManhuntTeam GetTeam() const;
	UFUNCTION(BlueprintPure, Category = "Manhunt") EHunterClass GetHunterClass() const;
	UFUNCTION(BlueprintPure, Category = "Manhunt") bool IsRunner() const { return GetTeam() == EManhuntTeam::Runner; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") bool IsHunter() const { return GetTeam() == EManhuntTeam::Hunter; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") bool IsMovementLocked() const { return MovementLockFlags != 0; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") float GetStamina() const { return Stamina; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") float GetStaminaRatio() const;
	UFUNCTION(BlueprintPure, Category = "Manhunt") AActor* GetMountedVehicle() const { return MountedVehicle; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") AManhuntCharacter* GetGrabbedBy() const { return GrabbedBy; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") AManhuntCharacter* GetGrabbedRunner() const { return GrabbedRunner; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") float GetStruggleProgress() const { return StruggleProgress; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") float GetTimedActionProgress() const;
	UFUNCTION(BlueprintPure, Category = "Manhunt") FText GetTimedActionLabel() const { return TimedActionLabel; }
	UFUNCTION(BlueprintPure, Category = "Manhunt") AManhuntCheckout* GetActiveQueue() const { return ActiveQueue; }
	/** Lokaler UI-Hinweis fuer das Objekt unter dem Fadenkreuz (leer = nichts). */
	UFUNCTION(BlueprintPure, Category = "Manhunt") FText GetFocusPrompt() const { return FocusPrompt; }

	const FManhuntClassStats& GetClassStats() const { return ClassStats; }
	bool CanSprint() const;
	float GetSpeedMultiplier() const;
	float GetCachedVehicleSpeed() const { return CachedVehicleSpeed; }
	float GetAudibleRadius() const;
	AManhuntBuildingVolume* GetCurrentBuilding() const { return CurrentBuilding.Get(); }

	// ---------------- Von der Movement-Komponente ----------------
	void SimulateStamina(float DeltaSeconds, bool bSprinting);
	void RefreshVehicleSpeed(TEnumAsByte<EPhysicalSurface> Surface);

	// ---------------- Nur Server ----------------
	void ApplyClassStats(const FManhuntClassStats& NewStats);
	void SetMovementLock(uint8 Flag, bool bLocked);
	void AddStamina(float Amount);
	/** Zeitaktion mit Fortschrittsbalken (Muelleimer durchsuchen, Tuer aufbrechen ...). Sperrt die Bewegung. */
	void StartTimedAction(float Duration, const FText& Label, TFunction<void()> OnComplete);
	void CancelTimedAction();
	bool IsBusy() const { return TimedActionDuration > 0.f; }
	void SetCurrentInteraction(AActor* Interactable) { CurrentInteraction = Interactable; }
	void ClearCurrentInteraction(AActor* Interactable);
	AActor* GetCurrentInteraction() const { return CurrentInteraction.Get(); }
	void SetMountedVehicle(AActor* Vehicle);
	void SetActiveQueue(AManhuntCheckout* Queue) { ActiveQueue = Queue; }
	void SetCurrentBuilding(AManhuntBuildingVolume* Building) { CurrentBuilding = Building; }
	/** Text-Nachricht an den besitzenden Client. */
	void ShowMessage(const FText& Message);
	/** Alles abbrechen: Interaktion, Zeitaktion, Warteschlange, Fahrzeug. */
	void InterruptEverything();

	// ---------------- Blueprint-Hooks (Animation, Sound, VFX) ----------------
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnGrabStateChanged(bool bIsGrabbed);
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnMountedVehicleChanged(AActor* Vehicle);
	UFUNCTION(BlueprintImplementableEvent, Category = "Manhunt") void OnTackle();

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void NotifyControllerChanged() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual bool IsNetRelevantFor(const AActor* RealViewer, const AActor* ViewTarget, const FVector& SrcLocation) const override;
	virtual bool CanJumpInternal_Implementation() const override;

	UFUNCTION(Server, Reliable) void Server_Interact();
	UFUNCTION(Server, Reliable) void Server_RunnerAbility();
	UFUNCTION(Server, Reliable) void Server_Tackle();
	UFUNCTION(Server, Unreliable) void Server_StruggleInput();
	UFUNCTION(Server, Reliable) void Server_UseItem(EManhuntItem Item);
	UFUNCTION(NetMulticast, Unreliable) void Multicast_PlayTackle();

	UFUNCTION() void OnRep_ServerStamina();
	UFUNCTION() void OnRep_GrabbedBy();
	UFUNCTION() void OnRep_GrabbedRunner();
	UFUNCTION() void OnRep_MountedVehicle();

	AActor* FindInteractable(const FVector& ViewLocation, const FRotator& ViewRotation) const;
	void UpdateFocus();
	void UpdateQueueAutoWalk();
	void RecordFootprints();
	void TickServerChecks(float DeltaSeconds);
	bool HasLineOfSightFrom(const FVector& From, const AActor* IgnoredViewer) const;
	void TryLoadFallbackMesh();

	// Struggle (laeuft auf dem Runner)
	void BeginStruggle(AManhuntCharacter* Hunter);
	void EndStruggle(bool bEscaped);
	void OnStruggleTimeout();
	void FinishTimedAction();

	// ---------------- Repliziert ----------------
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Manhunt") FManhuntClassStats ClassStats;
	UPROPERTY(Replicated) uint8 MovementLockFlags = 0;
	UPROPERTY(ReplicatedUsing = OnRep_ServerStamina) float ServerStamina = 100.f;
	UPROPERTY(ReplicatedUsing = OnRep_MountedVehicle) TObjectPtr<AActor> MountedVehicle;
	UPROPERTY(Replicated) TObjectPtr<AManhuntCheckout> ActiveQueue;
	UPROPERTY(ReplicatedUsing = OnRep_GrabbedBy) TObjectPtr<AManhuntCharacter> GrabbedBy;
	UPROPERTY(ReplicatedUsing = OnRep_GrabbedRunner) TObjectPtr<AManhuntCharacter> GrabbedRunner;
	UPROPERTY(Replicated) float StruggleProgress = 0.f;
	UPROPERTY(Replicated) float TimedActionEndTime = 0.f;
	UPROPERTY(Replicated) float TimedActionDuration = 0.f;
	UPROPERTY(Replicated) FText TimedActionLabel;

	// ---------------- Lokal ----------------
	UPROPERTY(Transient) TObjectPtr<UManhuntCharacterMovement> ManhuntMovement;
	float Stamina = 100.f;
	/** Nach komplettem Leerlaufen erst ab 15 % wieder sprinten (Hysterese, auf Client und Server gleich). */
	bool bExhausted = false;
	float CachedVehicleSpeed = 0.f;
	float CachedVehicleStaminaCost = 0.f;
	FText FocusPrompt;
	TWeakObjectPtr<AActor> FocusedActor;

	// ---------------- Nur Server ----------------
	TWeakObjectPtr<AActor> CurrentInteraction;
	TWeakObjectPtr<AManhuntBuildingVolume> CurrentBuilding;
	TFunction<void()> TimedActionCallback;
	FTimerHandle TimedActionTimer;
	FTimerHandle StruggleTimer;
	FTimerHandle StunTimer;
	float LastTackleTime = -100.f;
	float LastStrugglePressTime = 0.f;
	float UnusableSurfaceTime = 0.f;
	FVector LastFootprintLocation = FVector::ZeroVector;
	bool bLeftFoot = false;
};
