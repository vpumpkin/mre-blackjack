// Hunter-Klasse 3: Der Faehrtenleser (Spuren-Tracker).
// Faehigkeit mit festem Cooldown: zeigt Fussabdruecke & Reifenspuren der Runner,
// die mit dem Alter verblassen (Opazitaet + Farbe) -> er kann ablesen, wie viele Sekunden
// der Runner voraus ist. Waehrend des Lesens: halbes Tempo, kein Sprint.
//
// Decal-Material (Fab-Fussabdruck-Textur): Material Domain = Deferred Decal, Blend = Translucent,
// Parameter "Opacity" (Scalar) und "Color" (Vector). Ohne Material: Debug-Anzeige.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "ManhuntTypes.h"
#include "ManhuntTrackerComponent.generated.h"

class UMaterialInterface;
class UMaterialInstanceDynamic;
class UDecalComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnManhuntTracksRevealed, int32, Count, float, NewestAgeSeconds);

UCLASS(ClassGroup = (Manhunt), meta = (BlueprintSpawnableComponent))
class MANHUNTCORE_API UManhuntTrackerComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UManhuntTrackerComponent();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") TObjectPtr<UMaterialInterface> FootprintDecalMaterial;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") TObjectPtr<UMaterialInterface> TireTrackDecalMaterial;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") FVector FootprintDecalSize = FVector(10.f, 12.f, 24.f);
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") FVector TireDecalSize = FVector(10.f, 8.f, 60.f);
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") float RevealRadius = 4500.f;
	/** Ab diesem Alter (s) ist eine Spur komplett verblasst. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") float MaxTrackAge = 120.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") int32 MaxFootprintsPerReveal = 400;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") float RefreshInterval = 2.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") FLinearColor FreshColor = FLinearColor(1.f, 0.1f, 0.05f);
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tracker") FLinearColor OldColor = FLinearColor(0.35f, 0.35f, 0.35f);

	UPROPERTY(BlueprintAssignable, Category = "Tracker") FOnManhuntTracksRevealed OnTracksRevealed;

	UFUNCTION(BlueprintPure, Category = "Tracker") bool IsReadingTracks() const { return bReadingTracks; }
	UFUNCTION(BlueprintPure, Category = "Tracker") float GetCooldownRemaining() const;
	/** Alter der frischesten sichtbaren Spur in Sekunden (-1 = keine). */
	UFUNCTION(BlueprintPure, Category = "Tracker") float GetNewestTrackAge() const { return NewestAge; }

	/** Lokal aufrufen (Input). */
	void RequestActivate();

protected:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UFUNCTION(Server, Reliable) void Server_Activate();
	UFUNCTION(Client, Reliable) void Client_RevealFootprints(const TArray<FManhuntFootprint>& Prints);

	void SendFootprints();
	void EndReading();
	void ClearShown();

	UPROPERTY(Replicated) bool bReadingTracks = false;
	UPROPERTY(Replicated) float CooldownEndServerTime = 0.f;

	FTimerHandle ReadingTimer;
	FTimerHandle RefreshTimer;

	struct FShownPrint
	{
		TWeakObjectPtr<UDecalComponent> Decal;
		TWeakObjectPtr<UMaterialInstanceDynamic> MID;
		FVector Location = FVector::ZeroVector;
		float Yaw = 0.f;
		float Age = 0.f;
		bool bTire = false;
	};
	TArray<FShownPrint> Shown;
	float ShowTimeRemaining = 0.f;
	float NewestAge = -1.f;
};
